"""Contenedor de dependencias: cablea puertos a adaptadores Mongo."""

from dataclasses import dataclass

from pymongo import AsyncMongoClient

from heladeria_backend.catalog.adapters.mongo_adapter import (
    MongoCatalogItemRepository,
    MongoProductRepository,
)
from heladeria_backend.catalog.domain.ports import (
    CatalogItemRepository,
    ProductRepository,
)
from heladeria_backend.config.settings import settings
from heladeria_backend.identity.adapters.mongo_adapter import MongoAdminUserRepository
from heladeria_backend.identity.adapters.security import (
    Argon2PasswordHasher,
    JwtTokenService,
)
from heladeria_backend.identity.application.use_cases import IdentityContext
from heladeria_backend.identity.domain.ports import (
    AdminUserRepository,
    PasswordHasher,
    TokenIssuer,
)
from heladeria_backend.inventory.adapters.mongo_adapter import (
    MongoInventoryAtomicOps,
    MongoInventoryItemRepository,
    MongoMovementRepository,
    MongoReservationRepository,
)
from heladeria_backend.inventory.domain.ports import (
    InventoryAtomicPort,
    InventoryItemRepository,
    MovementRepository,
    ReservationRepository,
)
from heladeria_backend.orders.adapters.mongo_adapter import (
    MongoIdempotencyRepository,
    MongoOrderNumberPort,
    MongoOrderRepository,
)
from heladeria_backend.orders.application.use_cases import OrdersDeps
from heladeria_backend.orders.domain.ports import (
    IdempotencyRepository,
    OrderNumberPort,
    OrderRepository,
)
from heladeria_backend.shared.adapters.outbound.persistence.mongo.unit_of_work import (
    MongoUnitOfWork,
)
from heladeria_backend.shared.domain.clock import ClockPort, SystemClock
from heladeria_backend.tables.adapters.mongo_adapter import (
    MongoCustomerSessionRepository,
    MongoDeviceRepository,
    MongoTableRepository,
    MongoTableSessionRepository,
)
from heladeria_backend.tables.application.use_cases import TablesContext


@dataclass
class Container:
    client: AsyncMongoClient
    db_name: str
    clock: ClockPort
    uow_factory: type[MongoUnitOfWork]
    users: AdminUserRepository
    hasher: PasswordHasher
    tokens: TokenIssuer
    identity: IdentityContext
    tables_ctx: TablesContext
    products: ProductRepository
    catalog_items: CatalogItemRepository
    inventory_items: InventoryItemRepository
    movements: MovementRepository
    reservations: ReservationRepository
    inv_atomic: InventoryAtomicPort
    orders: OrderRepository
    idempotency: IdempotencyRepository
    numbers: OrderNumberPort
    orders_deps: OrdersDeps


def build_container(client: AsyncMongoClient, database_name: str | None = None) -> Container:
    db = database_name or settings.mongo.database
    uow_factory = lambda: MongoUnitOfWork(client, db)  # noqa: E731
    clock = SystemClock()
    users = MongoAdminUserRepository(client, db)
    hasher = Argon2PasswordHasher()
    tokens = JwtTokenService()
    identity = IdentityContext(users=users, hasher=hasher, tokens=tokens)
    tables_ctx = TablesContext(
        tables=MongoTableRepository(client, db),
        devices=MongoDeviceRepository(client, db),
        table_sessions=MongoTableSessionRepository(client, db),
        customer_sessions=MongoCustomerSessionRepository(client, db),
        clock=clock,
    )
    products = MongoProductRepository(client, db)
    catalog_items = MongoCatalogItemRepository(client, db)
    inventory_items = MongoInventoryItemRepository(client, db)
    movements = MongoMovementRepository(client, db)
    reservations = MongoReservationRepository(client, db)
    inv_atomic = MongoInventoryAtomicOps(client, db)
    orders = MongoOrderRepository(client, db)
    idempotency = MongoIdempotencyRepository(client, db)
    numbers = MongoOrderNumberPort(client, db)
    orders_deps = OrdersDeps(
        uow_factory=uow_factory,
        orders=orders,
        idempotency=idempotency,
        numbers=numbers,
        inv_atomic=inv_atomic,
        reservations=reservations,
        products=products,
        catalog_items=catalog_items,
        clock=clock,
        reservation_ttl=settings.business.reservation_ttl_seconds,
        idempotency_ttl=settings.business.idempotency_ttl_seconds,
    )
    return Container(
        client=client,
        db_name=db,
        clock=clock,
        uow_factory=uow_factory,
        users=users,
        hasher=hasher,
        tokens=tokens,
        identity=identity,
        tables_ctx=tables_ctx,
        products=products,
        catalog_items=catalog_items,
        inventory_items=inventory_items,
        movements=movements,
        reservations=reservations,
        inv_atomic=inv_atomic,
        orders=orders,
        idempotency=idempotency,
        numbers=numbers,
        orders_deps=orders_deps,
    )
