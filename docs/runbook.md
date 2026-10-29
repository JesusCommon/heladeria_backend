# Runbook: Heladeria Backend

## Arquitectura de Base de Datos

### Desarrollo Local
- **MongoDB**: Instalado localmente (Community Server)
- **Replica Set**: No configurado
- **Transacciones**: No disponibles
- **URI**: `mongodb://localhost:27017`

**Razón**: Evita overhead de Docker para infraestructura de datos y problemas de compatibilidad de CPU (AVX).

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