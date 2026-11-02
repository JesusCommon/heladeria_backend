"""Casos de uso de Orders: creación transaccional, transiciones, expiración."""

from dataclasses import dataclass, field
from datetime import timedelta

import structlog

from heladeria_backend.catalog.domain.catalog import (
    CustomizationValidator,
    Product,
    SelectionInput,
)
from heladeria_backend.catalog.domain.ports import (
    CatalogItemRepository,
    ProductRepository,
)
from heladeria_backend.inventory.domain.inventory import (
    Reservation,
    ReservationLine,
    ReservationState,
)
from heladeria_backend.inventory.domain.ports import (
    InventoryAtomicPort,
    ReservationRepository,
)
from heladeria_backend.orders.application.transactional import run_transaction
from heladeria_backend.orders.domain.order import (
    IdempotencyRecord,
    Order,
    OrderItem,
    OrderStatus,
    SelectionSnapshot,
)
from heladeria_backend.orders.domain.ports import (
    IdempotencyRepository,
    OrderNumberPort,
    OrderRepository,
)
from heladeria_backend.pricing.domain.service import LinePrice, price_line
from heladeria_backend.shared.adapters.outbound.persistence.mongo.unit_of_work import (
    MongoUnitOfWork,
)
from heladeria_backend.shared.domain.clock import ClockPort
from heladeria_backend.shared.domain.errors import (
    ConflictError,
    DomainValidationError,
    NotFoundError,
    UnavailableError,
)

logger = structlog.get_logger()


@dataclass
class LineInput:
    product_id: str
    quantity: int
    selections: list[SelectionInput] = field(default_factory=list)


@dataclass
class OrdersDeps:
    uow_factory: type[MongoUnitOfWork]
    orders: OrderRepository
    idempotency: IdempotencyRepository
    numbers: OrderNumberPort
    inv_atomic: InventoryAtomicPort
    reservations: ReservationRepository
    products: ProductRepository
    catalog_items: CatalogItemRepository
    clock: ClockPort
    reservation_ttl: int
    idempotency_ttl: int


# ---------------------------------------------------------------------------
#  Creación: validación + precio + reserva en UNA sola transacción (§ 3.6)
# ---------------------------------------------------------------------------

def _body(deps: OrdersDeps, **kwargs):
    async def body(session) -> Order:
        return await _create_order_tx(session, deps, **kwargs)
    return body


async def create_order(
    deps: OrdersDeps,
    *,
    customer_session_id: str,
    table_session_id: str,
    table_id: str,
    idempotency_key: str,
    lines: list[LineInput],
) -> Order:
    if not lines:
        raise DomainValidationError("El pedido no puede estar vacío")
    for line in lines:
        if line.quantity < 1:
            raise DomainValidationError("quantity debe ser >= 1")
    if not idempotency_key or len(idempotency_key) > 128:
        raise DomainValidationError("idempotency_key requerido (máx 128)")
    return await run_transaction(
        deps.uow_factory,
        _body(
            deps,
            customer_session_id=customer_session_id,
            table_session_id=table_session_id,
            table_id=table_id,
            idempotency_key=idempotency_key,
            lines=lines,
        ),
    )


async def _create_order_tx(
    session,
    deps: OrdersDeps,
    *,
    customer_session_id: str,
    table_session_id: str,
    table_id: str,
    idempotency_key: str,
    lines: list[LineInput],
) -> Order:
    now = deps.clock.now()

    # ---- 1. Idempotencia (D4: vigencia LÓGICA de 24h, no solo el índice TTL)
    record = await deps.idempotency.find(idempotency_key, customer_session_id, session=session)
    if record is None:
        from pymongo.errors import DuplicateKeyError

        try:
            await deps.idempotency.insert(
                IdempotencyRecord(
                    key=idempotency_key,
                    customer_session_id=customer_session_id,
                    order_id=None,
                    expires_at=now + timedelta(seconds=deps.idempotency_ttl),
                ),
                session=session,
            )
        except DuplicateKeyError:
            # otra tx simultánea reservó la clave primero
            raise ConflictError("Clave de idempotencia en proceso")
    elif record.expires_at > now:
        # clave vigente: misma (key, sesión) devuelve el resultado anterior
        if record.order_id:
            order = await deps.orders.get(record.order_id, session=session)
            if order is not None:
                logger.info("orders.idempotent_hit", order_number=order.order_number)
                return order
            raise ConflictError("Clave de idempotencia en proceso")
        # sin order_id aún (tx simultánea en vuelo): no crear duplicado
        raise ConflictError("Clave de idempotencia en proceso")
    else:
        # expirada lógicamente: la clave se reutiliza (D4)
        await deps.idempotency.renew(
            idempotency_key,
            customer_session_id,
            now + timedelta(seconds=deps.idempotency_ttl),
            session=session,
        )

    # ---- 2. Instantánea de productos + consumos agregados por elemento
    items: list[OrderItem] = []
    consumptions: dict[str, int] = {}
    option_names: dict[str, str] = {}
    for line in lines:
        product = await _load_product(deps, line.product_id, session)
        CustomizationValidator.validate(product, line.selections)
        priced = price_line(product, line.selections, line.quantity)
        for snap in priced.selections:
            if snap.catalog_item_id not in option_names:
                ci = await deps.catalog_items.get(snap.catalog_item_id, session=session)
                if ci is not None:
                    option_names[snap.catalog_item_id] = ci.name
        for item_id, qty in product.consumptions_for(line.selections, line.quantity).items():
            consumptions[item_id] = consumptions.get(item_id, 0) + qty
        items.append(_to_order_item(product, priced, line.quantity, option_names))

    total = sum(i.subtotal for i in items)

    order_number = await deps.numbers.next_number(session)
    order = Order(
        order_number=order_number,
        customer_session_id=customer_session_id,
        table_session_id=table_session_id,
        table_id=table_id,
        status=OrderStatus.PENDING,
        total=total,
        items=items,
        idempotency_key=idempotency_key,
    )
    order.created_at = now
    order.updated_at = now

    # ---- 3. Reserva: condición de disponible vive en el FILTRO atómico
    if consumptions:
        await deps.inv_atomic.reserve(consumptions, order.id, actor="order-create", session=session)
        reservation = Reservation(
            order_id=order.id,
            lines=[
                ReservationLine(
                    inventory_item_id=item_id,
                    quantity=qty,
                    unit="unit",
                )
                for item_id, qty in sorted(consumptions.items())
            ],
            expires_at=now + timedelta(seconds=deps.reservation_ttl),
        )
        await deps.reservations.create(reservation, session=session)
        order.reservation_id = reservation.id

    # ---- 4. Persistir pedido y saturar la idempotencia con su resultado (§ 5.4)
    await deps.orders.save(order, session=session)
    idem_doc = await deps.idempotency.find(idempotency_key, customer_session_id, session=session)
    if idem_doc is not None:
        idem_doc.order_id = order.id
        await deps.idempotency.update_order_id(
            idempotency_key, customer_session_id, order.id, session=session
        )
    logger.info("orders.created", order_number=order.order_number, total=order.total,
                order_id=order.id)
    return order


async def _load_product(deps: OrdersDeps, product_id: str, session) -> Product:
    product = await deps.products.get(product_id, session=session)
    if product is None:
        raise NotFoundError(f"Producto '{product_id}' no existe")
    if not product.is_active:
        raise UnavailableError(f"Producto '{product.name}' no está disponible")
    return product


def _to_order_item(product: Product, priced: LinePrice, quantity: int,
                   names: dict[str, str]) -> OrderItem:
    return OrderItem(
        product_id=product.id,
        product_name=product.name,
        base_price=priced.base_price,
        quantity=quantity,
        selections=[
            SelectionSnapshot(
                group_id=s.group_id,
                group_name=s.group_name,
                catalog_item_id=s.catalog_item_id,
                option_name=names.get(s.catalog_item_id, s.catalog_item_id),
                quantity=s.quantity,
                unit_price=s.unit_price,
            )
            for s in priced.selections
        ],
        options_price=priced.options_price,
        unit_final_price=priced.unit_final_price,
        subtotal=priced.subtotal,
    )


# ---------------------------------------------------------------------------
#  Transiciones de estado (§ 5.3), con consumo/liberación idempotente
# ---------------------------------------------------------------------------

def _action_body(deps: OrdersDeps, order_id: str, new_status: OrderStatus, reason: str | None):
    async def body(session) -> Order:
        return await _transition_tx(session, deps, order_id, new_status, reason)
    return body


async def transition_order(deps: OrdersDeps, order_id: str, new_status: OrderStatus,
                           reason: str | None = None) -> Order:
    return await run_transaction(
        deps.uow_factory,
        _action_body(deps, order_id, new_status, reason),
    )


async def accept_order(deps: OrdersDeps, order_id: str) -> Order:
    return await transition_order(deps, order_id, OrderStatus.ACCEPTED)


async def start_preparing(deps: OrdersDeps, order_id: str) -> Order:
    """PREPARING consume definitivamente el stock reservado (competencia)."""
    return await transition_order(deps, order_id, OrderStatus.PREPARING)


async def mark_ready(deps: OrdersDeps, order_id: str) -> Order:
    return await transition_order(deps, order_id, OrderStatus.READY)


async def mark_delivered(deps: OrdersDeps, order_id: str) -> Order:
    return await transition_order(deps, order_id, OrderStatus.DELIVERED)


async def cancel_order(deps: OrdersDeps, order_id: str, reason: str) -> Order:
    return await transition_order(deps, order_id, OrderStatus.CANCELLED, reason=reason)


async def expire_order(deps: OrdersDeps, order_id: str) -> Order:
    return await transition_order(deps, order_id, OrderStatus.EXPIRED)


async def _transition_tx(session, deps: OrdersDeps, order_id: str,
                         new_status: OrderStatus, reason: str | None) -> Order:
    order = await deps.orders.get(order_id, session=session)
    if order is None:
        raise NotFoundError(f"Pedido {order_id} no existe")
    if new_status == order.status:
        return order  # idempotente
    before = order.status

    if new_status is OrderStatus.PREPARING and order.reservation_id:
        reservation = await deps.reservations.get(order.reservation_id, session=session)
        if reservation is None:
            raise ConflictError("Pedido sin reserva activa para consumir")
        if reservation.status is ReservationState.ACTIVE:
            lines = {ln.inventory_item_id: ln.quantity for ln in reservation.lines}
            await deps.inv_atomic.consume(lines, order.id, actor="order-preparing", session=session)
            reservation.status = ReservationState.CONSUMED
            reservation.consumed_at = deps.clock.now()
            await deps.reservations.update(reservation, session=session)

    if new_status in (OrderStatus.CANCELLED, OrderStatus.EXPIRED) and order.reservation_id:
        reservation = await deps.reservations.get(order.reservation_id, session=session)
        if reservation is not None and reservation.status is ReservationState.ACTIVE:
            lines = {ln.inventory_item_id: ln.quantity for ln in reservation.lines}
            await deps.inv_atomic.release(lines, order.id, actor=f"order-{new_status.value}", session=session)
            reservation.status = (
                ReservationState.EXPIRED if new_status is OrderStatus.EXPIRED else ReservationState.RELEASED
            )
            reservation.released_at = deps.clock.now()
            await deps.reservations.update(reservation, session=session)

    if reason is not None and not reason.strip():
        reason = None

    order.transition(new_status)
    order.cancel_reason = reason
    await deps.orders.save(order, session=session)
    logger.info("orders.transition", order_number=order.order_number,
                from_status=before.value, to_status=new_status.value)
    return order


# ---------------------------------------------------------------------------
#  Expiración: barrido de pedidos aún PENDING con reserva vencida (§ 3.6)
# ---------------------------------------------------------------------------

async def expire_stale_orders(deps: OrdersDeps) -> list[str]:
    out: list[str] = []
    cutoff = deps.clock.now()
    stale_reservations = await deps.reservations.find_active_expired(cutoff)
    for reservation in stale_reservations:
        order = await deps.orders.get(reservation.order_id)
        if order is None or order.status is not OrderStatus.PENDING:
            # solo expira si sigue PENDING (requisito § 3.6)
            continue
        await expire_order(deps, order.id)
        out.append(order.id)
    return out


# ---------------------------------------------------------------------------
#  Consultas
# ---------------------------------------------------------------------------

async def get_order(deps: OrdersDeps, order_id: str) -> Order:
    order = await deps.orders.get(order_id)
    if order is None:
        raise NotFoundError(f"Pedido {order_id} no existe")
    return order


async def list_orders(deps: OrdersDeps, status: OrderStatus | None = None,
                      table_id: str | None = None,
                      customer_session_id: str | None = None) -> list[Order]:
    return await deps.orders.list(status=status, table_id=table_id,
                                  customer_session_id=customer_session_id)
