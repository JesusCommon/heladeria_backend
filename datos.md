# datos.md — Datos de prueba para todas las rutas y/o endpoints

> Base URL asumida: `http://localhost:8000` (ver `README.md` para arrancar).
> Credenciales de arranque provienen de `.env` (`ADMIN_SEED_OWNER_USERNAME/PASSWORD`).
> Copia y pega cada bloque en PowerShell. Los IDs `<ENTRE_ANGULARES>` se capturan
> de las respuestas previas.

## 0. Variables de sesión (ejecutar primero)

```powershell
$B   = "http://localhost:8000"
$CTM = "application/json"

# OWNER (seed automático)
$OWNER = (Invoke-RestMethod -Method Post -Uri "$B/api/v1/admin/auth/login" `
  -ContentType $CTM -Body '{"username":"owner","password":"heladeria-owner-123"}').access_token
$OH = @{ Authorization = "Bearer $OWNER" }
```

## 1. Health y raíz (públicas)

| Método | Ruta | Esperado |
|--------|------|----------|
| GET | `/` | 200 — app/version/entorno |
| GET | `/health/live` | 200 `{"status":"ok"}` |
| GET | `/health/ready` | 200 (Mongo conectado) |
| GET | `/health/status` | 200 con `database.status` |

```powershell
Invoke-RestMethod "$B/"
Invoke-RestMethod "$B/health/live"
Invoke-RestMethod "$B/health/ready"
Invoke-RestMethod "$B/health/status"
```

## 2. Identity / Admin auth

| Método | Ruta | Roles | Esperado |
|--------|------|-------|----------|
| POST | `/api/v1/admin/auth/login` | público | 200 (token JWT) |
| POST | `/api/v1/admin/users` | OWNER | 201 |

```powershell
# Crear STAFF (solo OWNER)
Invoke-RestMethod -Method Post -Uri "$B/api/v1/admin/users" -Headers $OH -ContentType $CTM `
  -Body '{"username":"staff01","password":"staff-password-123","role":"staff"}'

# Login del STAFF
$STAFF = (Invoke-RestMethod -Method Post -Uri "$B/api/v1/admin/auth/login" `
  -ContentType $CTM -Body '{"username":"staff01","password":"staff-password-123"}').access_token
$SH = @{ Authorization = "Bearer $STAFF" }
```

**Negativos**
- Login con contraseña errónea → 401. Repite el fallo **11 veces seguidas** con el mismo usuario → la 11ª responde **429** (rate limit anti fuerza bruta, ventana 60 s; por IP son 30 fallos/min).
- `POST /api/v1/admin/users` con username `"no valido!"` → 422 (formato `[A-Za-z0-9._-]{3,32}`).
- `POST /api/v1/admin/users` con STAFF (`-Headers $SH`) → 403.
- `GET /api/v1/admin/orders` sin token → 401; token basura (`Bearer abc`) → 401.

## 3. Inventario (admin)

| Método | Ruta | Roles | Esperado |
|--------|------|-------|----------|
| POST | `/api/v1/admin/inventory/items` | OWNER | 201 |
| GET | `/api/v1/admin/inventory/items` | STAFF+ | 200 |
| GET | `/api/v1/admin/inventory/items/{id}` | STAFF+ | 200 |
| PATCH | `/api/v1/admin/inventory/items/{id}` | OWNER | 200 |
| POST | `/api/v1/admin/inventory/items/{id}/entries` | OWNER | 200 |
| POST | `/api/v1/admin/inventory/items/{id}/adjustments` | OWNER | 200 |
| GET | `/api/v1/admin/inventory/items/{id}/movements` | STAFF+ | 200 |
| GET | `/api/v1/admin/inventory/reservations?statuses=active` | STAFF+ | 200 |

```powershell
# Item: fresas (ingredientes base y de topping)
$FRESA = (Invoke-RestMethod -Method Post -Uri "$B/api/v1/admin/inventory/items" -Headers $OH -ContentType $CTM `
  -Body '{"name":"Fresa fresca","unit":"g","stock_quantity":2000,"minimum_stock":200,"track_stock":true}').id
$CREMA = (Invoke-RestMethod -Method Post -Uri "$B/api/v1/admin/inventory/items" -Headers $OH -ContentType $CTM `
  -Body '{"name":"Crema de leche","unit":"ml","stock_quantity":5000,"minimum_stock":500,"track_stock":true}').id

# Entrada de mercancía (+300 g fresa)
Invoke-RestMethod -Method Post -Uri "$B/api/v1/admin/inventory/items/$FRESA/entries" -Headers $OH -ContentType $CTM `
  -Body '{"quantity":300,"reason":"recepción proveedor"}'

# Ajuste de inventario (-10 ml crema, conteo físico)
Invoke-RestMethod -Method Post -Uri "$B/api/v1/admin/inventory/items/$CREMA/adjustments" -Headers $OH -ContentType $CTM `
  -Body '{"delta":-10,"reason":"merma"}'

# Consultas
Invoke-RestMethod "$B/api/v1/admin/inventory/items/$FRESA" -Headers $SH
Invoke-RestMethod "$B/api/v1/admin/inventory/items/$FRESA/movements" -Headers $SH
Invoke-RestMethod "$B/api/v1/admin/inventory/reservations?statuses=active,released" -Headers $SH
```

**Negativos**
- `adjustment` sin `reason` → 422; `delta` que dejaría stock negativo → 409.
- PATCH con STAFF → 403; entrance con STAFF → 403.
- `/admin/inventory/reservations?statuses=xxx` → **422** con valores válidos listados (saneado: antes daba 500).

## 4. Catálogo (admin) — ítems y producto personalizable

| Método | Ruta | Roles | Esperado |
|--------|------|-------|----------|
| POST | `/api/v1/admin/catalog-items` | OWNER | 201 |
| PATCH | `/api/v1/admin/catalog-items/{id}` | OWNER | 200 |
| GET | `/api/v1/admin/catalog-items?active_only=true` | STAFF+ | 200 |
| POST | `/api/v1/admin/products` | OWNER | 201 |
| GET | `/api/v1/admin/products` | STAFF+ | 200 |
| GET | `/api/v1/admin/products/{id}` | STAFF+ | 200 |
| PUT | `/api/v1/admin/products/{id}` | OWNER | 200 |
| DELETE | `/api/v1/admin/products/{id}` | OWNER | 204 (baja lógica) |

```powershell
# Ítems de catálogo (opciones personalizables)
$TOP_FRESA = (Invoke-RestMethod -Method Post -Uri "$B/api/v1/admin/catalog-items" -Headers $OH -ContentType $CTM `
  -Body '{"name":"Cobertura de fresa","kind":"topping","description":"Cobertura artesanal"}').id
$NATA = (Invoke-RestMethod -Method Post -Uri "$B/api/v1/admin/catalog-items" -Headers $OH -ContentType $CTM `
  -Body '{"name":"Nata montada","kind":"extra"}').id

# Producto con grupo de personalizaciones (precios COP en enteros)
$BODY_PRODUCTO = @'
{
  "name": "Sundae del Manzano",
  "description": "Base de vainilla + un topping opcional",
  "kind": "sundae",
  "base_price": 8000,
  "base_consumption": [
    {"inventory_item_id": "REEMPLAZA_CREMA", "quantity": 200, "unit": "ml"}
  ],
  "customization": [
    {
      "name": "Toppings",
      "kind": "choice",
      "min_selections": 0,
      "max_selections": 2,
      "required": false,
      "allow_repeated": false,
      "allow_per_option_quantity": false,
      "options": [
        {
          "catalog_item_id": "REEMPLAZA_TOP",
          "additional_price": 1500,
          "is_active": true,
          "max_per_selection": 1,
          "consumption": [
            {"inventory_item_id": "REEMPLAZA_FRESA", "quantity": 50, "unit": "g"}
          ]
        },
        {
          "catalog_item_id": "REEMPLAZA_NATA",
          "additional_price": 2000,
          "is_active": true,
          "max_per_selection": 1,
          "consumption": []
        }
      ]
    }
  ]
}
'@
$BODY_PRODUCTO = $BODY_PRODUCTO.Replace("REEMPLAZA_CREMA", $CREMA).Replace("REEMPLAZA_TOP", $TOP_FRESA).Replace("REEMPLAZA_NATA", $NATA).Replace("REEMPLAZA_FRESA", $FRESA)
$PROD = Invoke-RestMethod -Method Post -Uri "$B/api/v1/admin/products" -Headers $OH -ContentType $CTM -Body $BODY_PRODUCTO
$PID    = $PROD.id
$GRUPO  = $PROD.customization[0].id        # group_id para las selecciones
$PROD2  = $PROD                            # clon para pedir "sin toppings"

# PUT: actualizar precio base (8500 COP)
$BODY_UPD = $BODY_PRODUCTO -replace '"base_price": 8000', '"base_price": 8500'
Invoke-RestMethod -Method Put -Uri "$B/api/v1/admin/products/$PID" -Headers $OH -ContentType $CTM -Body $BODY_UPD

# Baja lógica de un producto (crear uno temporal antes para no romper pedidos)
Invoke-RestMethod -Method Delete -Uri "$B/api/v1/admin/products/$PID" -Headers $OH   # 204 → is_active=false

# Ítems del catálogo
Invoke-RestMethod "$B/api/v1/admin/catalog-items?active_only=true" -Headers $SH
Invoke-RestMethod -Method Patch -Uri "$B/api/v1/admin/catalog-items/$NATA" -Headers $OH -ContentType $CTM `
  -Body '{"description":"Doble volumen lácteo"}'
```

**Negativos**
- `PUT /admin/products/{id}` con `customization.options` duplicadas respecto al mismo grupo → 422 (regla de dominio).
- GET de producto inexistente (`$PID + "-x"`) → 404.
- POST `/admin/products` con STAFF → 403.
- `DELETE` es baja lógica: el producto queda con `is_active=false` y vuelve 404/422 en futuros pedidos.

## 5. Catálogo público + cotizador (sin auth)

| Método | Ruta | Esperado |
|--------|------|----------|
| GET | `/api/v1/public/catalog` | 200 — solo productos activos con `is_selectable` y `is_selectable` por opción |
| POST | `/api/v1/public/price-quote` | 200 — precio calculado **en servidor** |

```powershell
Invoke-RestMethod "$B/api/v1/public/catalog"

# Cotización: base + 2 toppings de fresa (cantidad 2 de la selección NO permitida aquí)
$QUOTE = @'
{
  "product_id": "REEMPLAZA_PID",
  "quantity": 2,
  "selections": [
    {"group_id": "REEMPLAZA_GID", "catalog_item_id": "REEMPLAZA_TOP", "quantity": 1}
  ]
}
'@
$QUOTE = $QUOTE.Replace("REEMPLAZA_PID", $PID).Replace("REEMPLAZA_GID", $GRUPO).Replace("REEMPLAZA_TOP", $TOP_FRESA)
Invoke-RestMethod -Method Post -Uri "$B/api/v1/public/price-quote" -ContentType $CTM -Body $QUOTE
```

**Negativos**
- `selections` del grupo con `catalog_item_id` ajeno → 422.
- `quantity: 2` por opción cuando `allow_per_option_quantity=false` → 422.
- product_id inexistente → 404.

## 6. Mesas, dispositivos y sesiones

| Método | Ruta | Roles | Esperado |
|--------|------|-------|----------|
| POST | `/api/v1/admin/tables` | OWNER | 201 |
| GET | `/api/v1/admin/tables` | STAFF+ | 200 |
| PATCH | `/api/v1/admin/tables/{id}` | OWNER | 200 |
| POST | `/api/v1/admin/tables/{id}/sessions/open` | STAFF+ | 201 |
| POST | `/api/v1/admin/tables/sessions/{id}/close` | STAFF+ | 200 (cierra también customer sessions) |
| POST | `/api/v1/admin/tables/devices` | OWNER | 201 — `link_code` de un solo uso (TTL 10 min) |
| DELETE | `/api/v1/admin/tables/devices/{id}` | OWNER | 204 |
| POST | `/api/v1/device/claim` | público (código) | 200 — `device_token` |
| POST | `/api/v1/device/customer-session` | device token | 201 — `customer_token` |
| POST | `/api/v1/device/customer-session/close` | customer token | 200 |

```powershell
# Mesa 1
$T1 = (Invoke-RestMethod -Method Post -Uri "$B/api/v1/admin/tables" -Headers $OH -ContentType $CTM `
  -Body '{"number":1,"name":"Mesa junto a la ventana"}').id
Invoke-RestMethod "$B/api/v1/admin/tables" -Headers $SH

# Sesion de mesa abierta
$TS1 = (Invoke-RestMethod -Method Post -Uri "$B/api/v1/admin/tables/$T1/sessions/open" -Headers $SH).id

# Vinculación de dispositivo (12 caracteres hex, un solo uso)
$LINK = Invoke-RestMethod -Method Post -Uri "$B/api/v1/admin/tables/devices" -Headers $OH -ContentType $CTM `
  -Body ('{"table_id":"' + $T1 + '","device_name":"tablet-terrace-01"}')
$LINK_CODE = $LINK.link_code

# El tablet reclama el código (público, rate-limited)
$CLAIM = Invoke-RestMethod -Method Post -Uri "$B/api/v1/device/claim" -ContentType $CTM `
  -Body ('{"link_code":"' + $LINK_CODE + '"}')
$DT = $CLAIM.device_token

# El tablet abre la sesión del cliente en la mesa
$CS = Invoke-RestMethod -Method Post -Uri "$B/api/v1/device/customer-session" `
  -Headers @{ "X-Device-Token" = $DT } -ContentType $CTM -Body '{}'
$CT = $CS.customer_token
$CH = @{ "X-Customer-Token" = $CT }
$TSID = $CS.table_session_id
```

**Negativos**
- PATCH de mesa con STAFF → 403 (requerir OWNER).
- Abrir segunda sesión de mesa en `$T1` sin cerrar la primera → 409.
- **Rate limit en /device/claim**: envía 21 veces un código inválido (`"link_code":"000000000000"`) → la 21ª responde **429** (20 fallos/min por IP).
- `customer-session` con `X-Device-Token: no-existe` → 401.
- Reclamar el mismo `$LINK_CODE` de nuevo → **409** (código quemado tras el primer claim; también el endpoint lo renueva a `null`).

## 7. Pedidos (cliente de mesa)

| Método | Ruta | Auth | Esperado |
|--------|------|------|----------|
| POST | `/api/v1/orders` | `X-Customer-Token` | 201 |
| GET | `/api/v1/orders` | `X-Customer-Token` | 200 — lista propia |
| GET | `/api/v1/orders/{id}` | `X-Customer-Token` | 200 — aislado por sesión |

```powershell
$ORDER_BODY = @'
{
  "idempotency_key": "prueba-clave-0001",
  "lines": [
    {
      "product_id": "REEMPLAZA_PID",
      "quantity": 2,
      "selections": [
        {"group_id": "REEMPLAZA_GID", "catalog_item_id": "REEMPLAZA_TOP", "quantity": 1},
        {"group_id": "REEMPLAZA_GID", "catalog_item_id": "REEMPLAZA_NATA", "quantity": 1}
      ]
    }
  ]
}
'@
$ORDER_BODY = $ORDER_BODY.Replace("REEMPLAZA_PID", $PID).Replace("REEMPLAZA_GID", $GRUPO).Replace("REEMPLAZA_TOP", $TOP_FRESA).Replace("REEMPLAZA_NATA", $NATA)

$O1 = Invoke-RestMethod -Method Post -Uri "$B/api/v1/orders" -Headers $CH -ContentType $CTM -Body $ORDER_BODY   # total = 2*(8000 + 1500 + 2000)
$OID = $O1.id

# Idempotencia: reenvío EXACTO con la MISMA X-Customer-Token y la MISMA clave
# → NO crea un segundo pedido; devuelve el mismo (revisa que `order_number` no cambie)
Invoke-RestMethod -Method Post -Uri "$B/api/v1/orders" -Headers $CH -ContentType $CTM -Body $ORDER_BODY

Invoke-RestMethod "$B/api/v1/orders" -Headers $CH
Invoke-RestMethod "$B/api/v1/orders/$OID" -Headers $CH
```

**Negativos**
- POST sin `X-Customer-Token` → 401.
- POST con token de otro cliente (crear 2ª sesión de cliente) y `GET /orders/$OID` → 401 "Pedido de otro cliente".
- `selections` con `group_id` inexistente en el producto → 422.
- `quantity: 0` o `> 999` en una línea → 422 (topes anti abuso).
- Pedir 999 u de un producto cuyo stock es 500 → 409 `not_enough_stock` **sin pedido parcial**.
- Repetir mientras la primera tx está en vuelo con la MISMA clave → 409 "Clave de idempotencia en proceso".

## 8. Pedidos (admin) — máquina de estados

| Método | Ruta | Roles | Esperado |
|--------|------|-------|----------|
| GET | `/api/v1/admin/orders?status=pending&table_id=...` | STAFF+ | 200 |
| POST | `/api/v1/admin/orders/{id}/accept` | STAFF+ | 200 → ACCEPTED |
| POST | `/api/v1/admin/orders/{id}/preparing` | STAFF+ | 200 → PREPARING (consume reserva) |
| POST | `/api/v1/admin/orders/{id}/ready` | STAFF+ | 200 → READY |
| POST | `/api/v1/admin/orders/{id}/delivered` | STAFF+ | 200 → DELIVERED |
| POST | `/api/v1/admin/orders/{id}/cancel` | STAFF+ | 200 → CANCELLED (libera reserva; `reason` máx 200) |
| POST | `/api/v1/admin/orders/maintenance/expire` | STAFF+ | 200 — lista de pedidos expirados |

```powershell
Invoke-RestMethod "$B/api/v1/admin/orders?status=pending&table_id=$T1" -Headers $SH

Invoke-RestMethod -Method Post -Uri "$B/api/v1/admin/orders/$OID/accept"    -Headers $SH
Invoke-RestMethod -Method Post -Uri "$B/api/v1/admin/orders/$OID/preparing" -Headers $SH
Invoke-RestMethod -Method Post -Uri "$B/api/v1/admin/orders/$OID/ready"     -Headers $SH
Invoke-RestMethod -Method Post -Uri "$B/api/v1/admin/orders/$OID/delivered" -Headers $SH

# Cancelar otro pedido pendiente (reserva liberada) con motivo corto
$O2 = Invoke-RestMethod -Method Post -Uri "$B/api/v1/orders" -Headers $CH -ContentType $CTM `
  -Body ('{"idempotency_key":"prueba-clave-0002","lines":[{"product_id":"' + $PID + '","quantity":1}]}')
Invoke-RestMethod -Method Post -Uri "$B/api/v1/admin/orders/$($O2.id)/cancel?reason=cliente%20retirado" -Headers $SH

# Barrido de expiración (el sweep automático corre cada 30 s en background)
Invoke-RestMethod -Method Post -Uri "$B/api/v1/admin/orders/maintenance/expire" -Headers $SH
```

**Negativos**
- Transición ilegal: `ready` sobre pedido PENDING (sin accept) → 409.
- `GET /admin/orders?status=no-existe` → **422** listando valores válidos (saneado: antes 500).
- `reason` con más de 200 caracteres → 422.
- STAFF puede dar transiciones (diseño: STAFF/OWNER); sin token → 401.

## 9. Cierre de sesiones y limpieza

```powershell
# Cierre de la sesión del cliente
Invoke-RestMethod -Method Post -Uri "$B/api/v1/device/customer-session/close" -Headers $CH

# Cierre de la sesión de mesa (también cierra customer sessions abiertas)
Invoke-RestMethod -Method Post -Uri "$B/api/v1/admin/tables/sessions/$TSID/close" -Headers $SH

# Desactivar dispositivo (OWNER)
Invoke-RestMethod -Method Delete -Uri "$B/api/v1/admin/tables/devices/$($CLAIM.device_id)" -Headers $OH
```

**Negativos**
- `GET /orders` con el `X-Customer-Token` ya cerrado → 401 "Sesión de cliente inválida o cerrada".
- `customer-session` con mesa sin sesión abierta → 422 `unavailable`.

## 10. Datos de resumen rápido (copiar/pegar)

| Dato | Valor |
|------|-------|
| Base URL | `http://localhost:8000` |
| OWNER | `owner` / `heladeria-owner-123` |
| STAFF (creado en pruebas) | `staff01` / `staff-password-123` |
| Header OWNER/STAFF | `Authorization: Bearer <access_token>` |
| Header dispositivo | `X-Device-Token: <device_token>` |
| Header cliente de mesa | `X-Customer-Token: <customer_token>` |
| Clave idempotencia (ej.) | `prueba-clave-0001` |
| Precios | enteros COP (`base_price: 8000` = 8.000 COP) |
| Unidades de inventario | `g`, `ml`, `unit` |

## 11. Saneamientos de seguridad verificados en esta batería

1. **429** tras 11 fallos de login (IP+usuario) o 30 fallos de login/min por IP.
2. **429** tras 21 códigos de vinculación errados en `/device/claim`.
3. `/admin/orders?status=<inválido>` y `/admin/inventory/reservations?statuses=<inválido>` ahora devuelven **422**, no 500.
4. Cabeceras de seguridad presentes en toda respuesta: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cross-Origin-Resource-Policy: same-site`.
5. Los tiempos de login son homogéneos (Argon2 dummy) aunque el usuario no exista → no se puede enumerar usuarios por timing.
6. `link_code` ahora tiene 48 bits de entropía (12 hex) y se quema tras el primer claim.
7. En `production`: Swagger/OpenAPI deshabilitados y el arranque falla si `APP_DEBUG=true`, el JWT secret sigue el valor dev o `ADMIN_SEED_ENABLED=true`.
