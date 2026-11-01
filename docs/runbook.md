# Runbook: Heladeria Backend

## Arquitectura de Base de Datos

### Desarrollo Local
- **Instancia**: `mongod.exe` como replica set de un solo nodo (`rs0`), puerto 27018, datos en `.mongodb-data/`
- **Transacciones**: Disponibles (requisito del dominio: reservas de inventario)
- **URI**: `mongodb://localhost:27018` (definida en `.env`)

**Arranque** (idempotente): `powershell -File scripts/start_dev_mongo.ps1`

**Razón**: MongoDB standalone no soporta transacciones multi-documento. El dominio las necesita para reservas atómicas de inventario y pruebas de concurrencia reales. En vez de convertir el servicio Windows de MongoDB (27017, requiere admin) en replica set, se ejecuta una instancia dedicada de desarrollo sin afectar al servicio instalado.

### Producción
- **MongoDB**: Atlas (M0+ tier)
- **Replica Set**: Habilitado por defecto
- **Transacciones**: Disponibles
- **URI**: `mongodb+srv://...` (conectada vía)

**Razón**: Atlas provee replica set nativo, backups automáticos, monitoring y escalabilidad.

## Configuración del Cliente PyMongo

El archivo `shared/adapters/outbound/persistence/mongo/client.py` configura:

```python
AsyncMongoClient(
    ...,
    retryWrites=True,
    retryReads=True,
    writeConcern={"w": 1},
)