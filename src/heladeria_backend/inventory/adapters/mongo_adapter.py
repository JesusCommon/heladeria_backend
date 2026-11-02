"""Repositorios Mongo del módulo Inventory."""

from datetime import UTC, datetime
from typing import Any

import structlog
from pymongo.errors import DuplicateKeyError

from heladeria_backend.inventory.domain.ports import (
    InventoryAtomicPort,
    InventoryItemRepository,
    MovementRepository,
    ReservationRepository,
)
from heladeria_backend.inventory.domain.inventory import (
    InventoryItem,
    InventoryMovement,
    Reservation,
    ReservationState,
)
from heladeria_backend.shared.domain.errors import (
    ConflictError,
    NotFoundError,
    NotEnoughStockError,
    UnavailableError,
)
from heladeria_backend.shared.adapters.outbound.persistence.mongo.repo_mixins import (
    dump_bson,
    load,
)

logger = structlog.get_logger()

COLL_ITEMS = "inventory_items"
COLL_MOVEMENTS = "inventory_movements"
COLL_RESERVATIONS = "reservations"


class _Base:
    def __init__(self, client, database_name: str):
        self._client = client
        self._db = client[database_name]

    @property
    def db(self):
        return self._db


class MongoInventoryItemRepository(InventoryItemRepository, _Base):
    async def create(self, item: InventoryItem, session: Any | None = None) -> InventoryItem:
        doc = dump_bson(item)
        doc["_id"] = doc.pop("id")
        try:
            await self.db[COLL_ITEMS].insert_one(doc, session=session)
        except DuplicateKeyError:
            raise ConflictError(f"Ya existe un elemento de inventario con id {item.id}")
        return item

    async def get(self, item_id: str, session: Any | None = None) -> InventoryItem | None:
        doc = await self.db[COLL_ITEMS].find_one({"_id": item_id}, session=session)
        return load(InventoryItem, doc) if doc else None

    async def update(self, item: InventoryItem, session: Any | None = None) -> InventoryItem:
        item.updated_at = datetime.now(UTC)
        doc = dump_bson(item)
        doc["_id"] = doc.pop("id")
        doc.pop("created_at", None)
        res = await self.db[COLL_ITEMS].replace_one({"_id": item.id}, doc, session=session)
        if res.matched_count == 0:
            raise NotFoundError(f"Inventario {item.id} no existe")
        return item

    async def list(self, active_only: bool = False, session: Any | None = None) -> list[InventoryItem]:
        q = {"is_active": True} if active_only else {}
        docs = await self.db[COLL_ITEMS].find(q, session=session).to_list(1000)
        return [load(InventoryItem, d) for d in docs]


class MongoMovementRepository(MovementRepository, _Base):
    async def append(self, movement: InventoryMovement, session: Any | None = None) -> InventoryMovement:
        doc = dump_bson(movement)
        doc["_id"] = doc.pop("id")
        await self.db[COLL_MOVEMENTS].insert_one(doc, session=session)
        return movement

    async def list_by_item(
        self,
        item_id: str,
        limit: int = 100,
        session: Any | None = None,
    ) -> list[InventoryMovement]:
        docs = (
            await self.db[COLL_MOVEMENTS]
            .find({"inventory_item_id": item_id}, session=session)
            .sort("occurred_at", -1)
            .to_list(limit)
        )
        return [load(InventoryMovement, d) for d in docs]


class MongoReservationRepository(ReservationRepository, _Base):
    async def create(self, reservation: Reservation, session: Any | None = None) -> Reservation:
        doc = dump_bson(reservation)
        doc["_id"] = doc.pop("id")
        try:
            await self.db[COLL_RESERVATIONS].insert_one(doc, session=session)
        except DuplicateKeyError:
            raise ConflictError(f"Reserva duplicada {reservation.id}")
        return reservation

    async def get(self, reservation_id: str, session: Any | None = None) -> Reservation | None:
        doc = await self.db[COLL_RESERVATIONS].find_one({"_id": reservation_id}, session=session)
        return load(Reservation, doc) if doc else None

    async def get_by_order(self, order_id: str, session: Any | None = None) -> Reservation | None:
        doc = await self.db[COLL_RESERVATIONS].find_one({"order_id": order_id}, session=session)
        return load(Reservation, doc) if doc else None

    async def update(self, reservation: Reservation, session: Any | None = None) -> Reservation:
        doc = dump_bson(reservation)
        doc["_id"] = doc.pop("id")
        await self.db[COLL_RESERVATIONS].replace_one(
            {"_id": reservation.id}, doc, session=session
        )
        return reservation

    async def find_active_expired(
        self,
        now: datetime,
        session: Any | None = None,
    ) -> list[Reservation]:
        docs = (
            await self.db[COLL_RESERVATIONS]
            .find({"status": "active", "expires_at": {"$lt": now}}, session=session)
            .to_list(200)
        )
        return [load(Reservation, d) for d in docs]

    async def list_statuses(
        self,
        statuses: list[ReservationState] | None = None,
        session: Any | None = None,
    ) -> list[Reservation]:
        q = {"status": {"$in": [s.value for s in statuses]}} if statuses else {}
        docs = (
            await self.db[COLL_RESERVATIONS]
            .find(q, session=session)
            .sort("created_at", -1)
            .to_list(500)
        )
        return [load(Reservation, d) for d in docs]


class MongoInventoryAtomicOps(InventoryAtomicPort, _Base):
    """Implementa las operaciones críticas con updates condicionales.

    Disponibilidad vive en el FILTRO del update atómico: si un competidor
    consume la última unidad, este findOneAndUpdate no matchea yMongo
    resuelve la carrera sin doble reserva (WriteConflict aborta la tx perdedora).
    """

    async def reserve(
        self,
        lines: dict[str, int],
        order_id: str,
        actor: str | None,
        session: Any,
    ) -> None:
        for item_id, qty in sorted(lines.items()):
            doc = await self.db[COLL_ITEMS].find_one({"_id": item_id}, session=session)
            if doc is None:
                raise NotFoundError(f"Elemento de inventario '{item_id}' no existe")
            item = load(InventoryItem, doc)
            if not item.is_active:
                raise UnavailableError(f"'{item.name}' está desactivado en inventario")
            if not item.track_stock:
                continue

            matched = await self.db[COLL_ITEMS].find_one_and_update(
                {
                    "_id": item_id,
                    "track_stock": True,
                    "$expr": {
                        "$gte": [
                            {"$subtract": ["$stock_quantity", "$reserved_quantity"]},
                            qty,
                        ]
                    },
                },
                {"$inc": {"reserved_quantity": qty, "version": 1}},
                session=session,
            )
            if matched is None:
                raise NotEnoughStockError(
                    f"Stock insuficiente de '{item.name}' (disponible {item.available}, requerido {qty})"
                )

            await self._append_movement(item_id, qty, "reserve", order_id, actor, session)

    async def consume(self, lines: dict[str, int], order_id: str, actor: str | None, session: Any) -> None:
        for item_id, qty in sorted(lines.items()):
            doc = await self.db[COLL_ITEMS].find_one({"_id": item_id}, session=session)
            if doc is None:
                raise NotFoundError(f"Elemento de inventario '{item_id}' no existe")
            item = load(InventoryItem, doc)
            if not item.track_stock:
                continue
            matched = await self.db[COLL_ITEMS].find_one_and_update(
                {
                    "_id": item_id,
                    "$expr": {"$gte": ["$reserved_quantity", qty]},
                },
                {"$inc": {"stock_quantity": -qty, "reserved_quantity": -qty, "version": 1}},
                session=session,
            )
            if matched is None:
                raise ConflictError(f"No se está reservado '{item.name}' ({item.available}) suficiente")
            await self._append_movement(item_id, -qty, "consumption", order_id, actor, session)

    async def release(self, lines: dict[str, int], order_id: str, actor: str | None, session: Any) -> None:
        for item_id, qty in sorted(lines.items()):
            doc = await self.db[COLL_ITEMS].find_one({"_id": item_id}, session=session)
            if doc is None:
                raise NotFoundError(f"Elemento de inventario '{item_id}' no existe")
            item = load(InventoryItem, doc)
            if not item.track_stock:
                continue
            matched = await self.db[COLL_ITEMS].find_one_and_update(
                {
                    "_id": item_id,
                    "$expr": {"$gte": ["$reserved_quantity", qty]},
                },
                {"$inc": {"reserved_quantity": -qty, "version": 1}},
                session=session,
            )
            if matched is None:
                raise ConflictError(f"'{item.name}' no tiene reserva activa de {qty}; libera desde el caso de uso idempotente")
            await self._append_movement(item_id, -qty, "release", order_id, actor, session)

    async def _append_movement(self, item_id, qty, mtype, order_id, actor, session):
        movement = InventoryMovement(
            inventory_item_id=item_id,
            quantity=qty,
            type=mtype,
            order_id=order_id,
            actor=actor,
            reason=f"{mtype} por pedido {order_id}",
        )
        doc = dump_bson(movement)
        doc["_id"] = doc.pop("id")
        await self.db[COLL_MOVEMENTS].insert_one(doc, session=session)
