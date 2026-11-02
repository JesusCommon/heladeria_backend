# Heladeria Backend

Backend para un sistema de pedidos de heladería: mesas con dispositivos,
pedidos por cliente, catálogo personalizable por producto, inventario con
reservas seguras ante concurrencia, precios en COP y administración con
JWT + roles.

**Stack**: Python 3.13 · FastAPI · MongoDB (replica set local) · Pydantic · uv.

## Arquitectura (hexagonal, monolito modular)

```
src/heladeria_backend/
├── bootstrap/        Arranque: wiring de dependencias, índices, seed, sweep de expiración, app FastAPI
├── config/           Settings Fuw por variables de entorno
├── observability/    Logging estructurado (structlog)
└── shared/           Errores de dominio, reloj, dinero (COP entero), UoW Mongo, middleware
├── identity/         Usuarios admin, Argon2id, JWT HS256, roles OWNER/STAFF
├── catalog/          Productos, ítems de catálogo, GRUPOS de personalización por producto
├── pricing/          Cálculo puro de precios (sin TOC con el cliente)
├── inventory/        Elementos, movimientos append-only, reservas atómicas ($expr)
├── tables/           Mesas, dispositivos, sesiones de mesa y de cliente
└── orders/           Máquina de estados, creación transaccional, idempotencia, expiración
```

Cada módulo respeta `domain/` (puro, sin Mongo ni HTTP) → `ports/` (interfaces)
→ `adapters/` (Mongo, API HTTP) → `application/` (casos de uso).
El dominio NUNCA depende de frameworks.

## Cómo arrancar

```powershell
# 1. Dependencias
uv sync

# 2. MongoDB de desarrollo: replica set rs0 en puerto 27018 (idempotente)
powershell -File scripts/start_dev_mongo.ps1

# 3. Config (o copiar y ajustar)
copy .env .env

# 4. Servidor
uv run uvicorn heladeria_backend.bootstrap.app_factory:create_app --factory --reload --port 8000
```

Swagger: `http://localhost:8000/docs` · OpenAPI: `http://localhost:8000/openapi.json`.

## Pruebas

```powershell
make test                 # unitarias (41)
make test-integration     # integración contra Mongo real (replica set) (38)
uv run pytest tests/api   # suite HTTP end-to-end (38)
uv run pytest             # todo (118)
uv run pytest -W error::RuntimeWarning   # sin advertencias silenciadas
```

Las pruebas de integración y API usan el replica set de desarrollo (`27018`)
crean y borran una base de datos aleatoria por prueba. Incluyen una prueba
critical de concurrencia real: dos clientes compiten por la última unidad de
stock y exactamente uno gana.

## Reglas de negocio clave

- **Precios**: enteros en COP, siempre calculados en el servidor; instantáneas
  históricas inmutables por línea de pedido.
- **Inventario**: `disponible = físico − reservado`. La verificación de
  disponibilidad vive DENTRO del filtro de la operación atómica de Mongo, en
  la misma transacción de la creación del pedido.
- **Reservas**: `ACTIVE → CONSUMED` (al pasar a PREPARING) / `RELEASED`
  (cancelación antes de PREPARING) / `EXPIRED` (sweeper en segundo plano);
  cancelar tras consumo NO devuelve stock.
- **Idempotencia**: clave `(Idempotency-Key, customer_session)` con vigencia
  LÓGICA de 24h (D4), no dependiente del TTL index.
- **Mesas**: id interno inmutable, número visible único pero renumeritable;
  el `table_id` del pedido SIEMPRE se deduce de la cadena de sesiones del
  servidor, jamás del cliente.

## Documentación adicional

- [`docs/domain-model.md`](docs/domain-model.md) — modelo de dominio y decisiones (D1…D8, P1…P8).
- [`docs/runbook.md`](docs/runbook.md) — variables de entorno, endpoints y despliegue.
