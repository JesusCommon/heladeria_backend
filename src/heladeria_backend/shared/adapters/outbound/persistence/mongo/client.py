from pymongo import AsyncMongoClient
from heladeria_backend.config.settings import settings

def create_mongo_client() -> AsyncMongoClient:
    return AsyncMongoClient(
        settings.mongo.url,
        appName=settings.app.slug,
        minPoolSize=settings.mongo.pool_min_size,
        maxPoolSize=settings.mongo.pool_max_size,
        serverSelectionTimeoutMS=settings.mongo.server_selection_timeout_ms,
        connectTimeoutMS=settings.mongo.connect_timeout_ms,
        socketTimeoutMS=settings.mongo.socket_timeout_ms,
        waitQueueTimeoutMS=settings.mongo.wait_queue_timeout_ms,
        retryWrites=True,
        retryReads=True,
    )