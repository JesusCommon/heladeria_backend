# Runbook: Heladeria Backend

## Arranque desde cero (desarrollo)

```powershell
uv sync                                            # dependencias
powershell -File scripts/start_dev_mongo.ps1       # replica set rs0 @ 27018 (idempotente)
uv run uvicorn heladeria_backend.bootstrap.app_factory:create_app --factory --port 8000
```

Al arrancar, el `lifespan` conecta Mongo, crea los índices, siembra el OWNER
inicial y lanza el barrido de expiración de pedidos (cada
`BUSINESS_EXPIRATION_SWEEP_SECONDS`).

## Base de datos (desarrollo)

- **Instancia**: `mongod.exe` como replica set de un solo nodo (`rs0`), puerto
  27018, datos en `.mongodb-data/` del proyecto.
- **URI**: `mongodb://localhost:27018/?replicaSet=rs0` (en `.env`).
  ⚠️ Sin `?replicaSet=rs0` el driver ve una topología "standalone" y DESACTIVA
  transacciones — el dominio las necesita para reservas.
- **Razón**: MongoDB standalone no soporta transacciones multi-documento. Se
  usa instancia dedicada de desarrollo sin tocar el servicio Windows instalado
  en 27017 (que no se usa).

**Producción**: MongoDB Atlas (replica set nativo) vía `mongodb+srv://...`.

## Variables de entorno (`.env`)

| Variable | Ejemplo | Uso |
|---|---|---|
| `APP_NAME` / `APP_SLUG` / `APP_VERSION` / `APP_TIMEZONE` / `APP_LOCALE` / `APP_ENVIRONMENT` / `APP_DEBUG` | … | identidad/diagnóstico de la app |
| `MONGODB_URL` | `mongodb://localhost:27018/?replicaSet=rs0` | conexión |
| `MONGODB_DATABASE` | `heladeria_db` | base de datos |
| `MONGODB_POOL_MIN_SIZE` / `MONGODB_POOL_MAX_SIZE` | `5` / `50` | pool del driver |
| `MONGODB_SERVER_SELECTION_TIMEOUT_MS` / `MONGODB_CONNECT_TIMEOUT_MS` / `MONGODB_SOCKET_TIMEOUT_MS` | … | timeouts |
| `SECURITY_JWT_SECRET` | ≥16 caracteres (validado) | firma JWT HS256 |
| `SECURITY_JWT_TTL_MINUTES` | `720` | vigencia del token admin |
| `SECURITY_DEVICE_LINK_TTL_MINUTES` | `10` | expiración del código de vinculación de dispositivos |
| `BUSINESS_RESERVATION_TTL_SECONDS` | `600` | expiración de reserva de pedido aún PENDING |
| `BUSINESS_IDEMPOTENCY_TTL_SECONDS` | `86400` | vigencia lógica de claves de idempotencia (D4: 24h) |
| `BUSINESS_EXPIRATION_SWEEP_SECONDS` | `30` | intervalo del barrido en segundo plano |
| `BUSINESS_CURRENCY` | `COP` | moneda |
| `ADMIN_SEED_ENABLED` | `true` | sembrar OWNER si no hay usuarios |
| `ADMIN_SEED_OWNER_USERNAME` / `ADMIN_SEED_OWNER_PASSWORD` | `owner` / … | credenciales del seed |

## Endpoints principales (todos bajo `/api/v1`)

**Autenticación**
- `POST /admin/auth/login` — JWT para OWNER/STAFF
- `POST /admin/users` — crear usuarios admin (solo OWNER)

**Catálogo (admin)**
- `POST/GET /admin/products`, `GET/PUT/DELETE /admin/products/{id}` — solo OWNER escribe
- `POST/PATCH/GET /admin/catalog-items` — sabores/salsas/toppings/extras

**Catálogo público** (para tablets)
- `GET /public/catalog` — con `is_selectable` por producto/opción (stock y vigencia)
- `POST /public/price-quote` — cotización server-side en COP (ignora precios del cliente)

**Inventario (admin)**
- `POST /admin/inventory/items` (OWNER), `GET /admin/inventory/items` (STAFF)
- `PATCH /admin/inventory/items/{id}` — mínimo, activo, track_stock
- `POST /admin/inventory/items/{id}/entries` — entradas
- `POST /admin/inventory/items/{id}/adjustments` — ajustes con motivo obligatorio
- `GET /admin/inventory/items/{id}/movements` — trazabilidad append-only
- `GET /admin/inventory/reservations` — por estado

**Mesas / dispositivos / sesiones**
- `POST/GET /admin/tables`, `PATCH /admin/tables/{id}` (renumeración)
- `POST /admin/tables/{id}/sessions/open`, `POST /admin/tables/sessions/{id}/close`
- `POST /admin/tables/devices` (OWNER emite código), `DELETE /admin/tables/devices/{id}`
- `POST /device/claim` — tablet reclama el código de un solo uso
- `POST /device/customer-session` (header `X-Device-Token`) — sesión de cliente
- `POST /device/customer-session/close` (header `X-Customer-Token`)

**Pedidos**
- `POST /orders` (header `X-Customer-Token`, body con `idempotency_key`) — creación transaccional
- `GET /orders/{id}`, `GET /orders` — solo del propio cliente
- `GET /admin/orders?status=&table_id=` — staff consulta
- `POST /admin/orders/{id}/accept|preparing|ready|delivered|cancel`
- `POST /admin/orders/maintenance/expire` — fuerza el barrido de expiración

**Estados de pedidos**: `pending → accepted → preparing → ready → delivered`
(o `cancelled` / `expired`). Nada de saltos; API devuelve `409 conflict`.

## Errores HTTP

Errores de dominio mapeados a JSON `{detail, code}`:
`401 auth_error`, `403 permission_denied`, `404 not_found`,
`409 conflict` / `not_enough_stock`, `422 validation_error` / `unavailable`.

## Índices críticos

- `tables.number` único (renumerable, id interno inmutable)
- `table_sessions (table_id, status)` único parcial `status="open"` → P1
- `idempotency_keys (key, customer_session_id)` único + TTL en `expires_at`
- `orders.order_number` único (`counters` atómico al crear)
- `devices.token_hash` y `customer_sessions.token_hash` únicos sparse
- `reservations (status, expires_at)` para el barrido

## Pruebas

```powershell
make test              # unitarias (41)
make test-integration  # 38, contra el replica set real
uv run pytest tests/api # 38, app FastAPI completa vía httpx ASGITransport
uv run pytest          # 118 total
uv run ruff check src tests --select E,F,I,W --line-length 120
```
