from typing import Self
import structlog
from pymongo import AsyncMongoClient
from pymongo.errors import InvalidOperation, OperationFailure
from heladeria_backend.shared.application.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger()

_TRANSACTIONAL_TOPOLOGIES = frozenset(
    {
        "ReplicaSetWithPrimary",
        "ReplicaSetNoPrimary",
        "Sharded",
        "LoadBalanced",
    }
)

class MongoUnitOfWork(UnitOfWork):
    def __init__(self, client: AsyncMongoClient, database_name: str) -> None:
        self._client = client
        self._database_name = database_name
        self._session = None
        self._supports_transactions = self._detect_transaction_support()
        self._transaction_active = False

    def _detect_transaction_support(self) -> bool:
        try:
            topology_name = self._client.topology_description.topology_type_name
            return topology_name in _TRANSACTIONAL_TOPOLOGIES
        except Exception:
            return False

    @property
    def database(self):
        return self._client[self._database_name]

    @property
    def session(self):
        return self._session

    async def __aenter__(self) -> Self:
        self._session = self._client.start_session()

        if self._supports_transactions:
            try:
                self._session.start_transaction()
                self._transaction_active = True
            except (InvalidOperation, OperationFailure) as e:
                logger.warning(
                    "unit_of_work.transaction.start.failed",
                    error=str(e),
                )
                self._transaction_active = False
        else:
            logger.debug(
                "unit_of_work.transactions.unavailable",
                reason="standalone topology",
            )

        return self

    async def commit(self) -> None:
        if not self._transaction_active or self._session is None:
            return

        try:
            await self._session.commit_transaction()
        except (InvalidOperation, OperationFailure) as e:
            logger.exception("unit_of_work.commit.failed", error=str(e))
            raise
        finally:
            self._transaction_active = False

    async def rollback(self) -> None:
        if not self._transaction_active or self._session is None:
            return

        try:
            await self._session.abort_transaction()
        except (InvalidOperation, OperationFailure) as e:
            logger.exception("unit_of_work.rollback.failed", error=str(e))
        finally:
            self._transaction_active = False

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            if exc_type is not None:
                await self.rollback()
            else:
                await self.commit()
        finally:
            if self._session is not None:
                await self._session.end_session()
                self._session = None