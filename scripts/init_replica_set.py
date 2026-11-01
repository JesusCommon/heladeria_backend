"""Inicializa el replica set rs0 si aún no está iniciado.

Se ejecuta tras levantar mongod (scripts/start_dev_mongo.ps1).
Idempotente: si el replica set ya está iniciado, no hace nada.
"""

import asyncio

from pymongo import AsyncMongoClient

URI = "mongodb://localhost:27018/?directConnection=true"

CONFIG = {"_id": "rs0", "members": [{"_id": 0, "host": "localhost:27018"}]}


async def main() -> None:
    client = AsyncMongoClient(URI, serverSelectionTimeoutMS=5000)
    try:
        hello = await client.admin.command("hello")
        if hello.get("setName"):
            print(f"Replica set ya iniciado: {hello['setName']}")
            return
        await client.admin.command("replSetInitiate", CONFIG)
        print("Replica set rs0 iniciado")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
