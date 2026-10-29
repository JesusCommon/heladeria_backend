import asyncio
from pymongo import AsyncMongoClient

async def ping_mongo(client: AsyncMongoClient, timeout_ms: int = 2000) -> None:

    await asyncio.wait_for(
        client.admin.command("ping"),
        timeout=timeout_ms / 1000,
    )