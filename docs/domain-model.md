# Modelo de dominio — Heladería Backend (Fase 1)

Estado: propuesta para revisión. Este documento es el contrato previo a la implementación (Fase 3+). Cualquier desvío posterior debe reflejarse aquí o en un ADR.

## 1. Decisiones ya tomadas

| # | Decisión | Valor | Motivo |
|---|----------|-------|--------|
| D1 | Moneda | COP, cantidades enteras sin decimales | Decisión del propietario. `Money` = entero + código de moneda. Nunca `float`. |
| D2 | Entorno comercial | Presencial en mesa, sin pagos en esta etapa | El alcance no incluye cobros; el pago se resuelve fuera del sistema. |
| D3 | Expiración de reserva | 10 minutos por defecto, configurable por settings | Decisión del propietario. |
| D4 | Estilo arquitectónico | Monolito modular con arquitectura hexagonal | Evita complejidad operativa prematura. |
| D5 | Persistencia | MongoDB, arriba de la base existente (FastAPI + PyMongo/UnitOfWork) | Ya implementado en el repo. |
| D6 | Cantidades de inventario | Enteros en unidades base (g, ml, unidades) | Evita errores de punto flotante; la conversión es problema de presentación. |
| D7 | Precios históricos | Instantáneas embebidas en el pedido | Los cambios de catálogo no alteran pedidos previos. |

## 2. Mapa de módulos y dependencias permitidas

Módulos de dominio: `catalog`, `customization`, `inventory`, `tables`, `orders`, `pricing`, `identity`.

Reglas de dependencia (módulo → depende de):

- `catalog` → nada del dominio (autónomo).
- `customization` → `catalog` (referencia opciones), `inventory` (solo reglas de consumo declaradas; no calcula stock).
- `inventory` → nada del dominio (autónomo).
- `tables` → `identity` (sesiones/credenciales).
- `pricing` → `catalog`, `customization`.
- `orders` → `catalog`, `customization`, `inventory`, `tables`, `pricing`.
- `identity` → nada del dominio.

Ningún módulo de dominio depende de HTTP, ORM ni del framework. Los controladores HTTP solo conocen puertos de entrada.

## 3. Módulo Catalog

### Entidades

**CatalogItem** (opción de personalización, generaliza "sabor / salsa / decoración / adicional"):

- `id`, `name`, `kind` (flavor | sauce | topping | extra), `description`
- `isActive`, `createdAt`, `updatedAt`

**Product**:

- `id`, `name`, `description`, `kind` (cone | sundae | shake | …), `imageUrl` (opcional, no obligatorio)
- `basePrice: Money`
- `isActive`
- `baseConsumption: list[ConsumptionRequirement]` — inventario que consume la unidad base del producto (ej.: 1 cono vacío).
- `customizationConfig: ProductCustomizationConfig` (ver módulo Customization).

### Invariantes de Catalog

1. `name` no vacío; único entre opciones del mismo `kind` (regla administrativa prudencial, no del dominio puro).
2. Un producto inactivo no puede incluirse en pedidos nuevos; los pedidos históricos no cambian (protección por instantánea).
3. `basePrice >= 0`.
4. Una opción de personalización inactiva deja de poder seleccionarse en pedidos nuevos (validación en Customization/Orders), sin afectar históricos.

> ⓘ Decisión de modelado flaggeada: en lugar de entidades separadas `Flavor`/`Topping`/`Salsa`, se usa una sola entidad `CatalogItem` con `kind`. La semántica la aporta el grupo de personalización. Si el propietario quiere validaciones distintas por tipo (p. ej. sabores de una sola bola), se modelará como regla del grupo, no como subtipos de código.

## 4. Módulo Customization

El corazón del sistema. Todo es configuración persistida; nada hardcodeado.

### Modelo

**ProductCustomizationConfig** (valor embebido en `Product`):

- `groups: list[CustomizationGroup]`

**CustomizationGroup**:

| Atributo | Tipo | Notas |
|---|---|---|
| id | UUID | |
| name | str | "Sabores", "Salsas", "Decoraciones" |
| description | str? | |
| kind | grupo tipo semántico | informativo; no condiciona lógica |
| options | list[GroupOption] | referencia a `CatalogItem` + reglas |
| minSelections | int >= 0 | mínimo de opciones distintas |
| maxSelections | int >= 1 | máximo de opciones distintas |
| required | bool | si true, `minSelections >= 1` |
| allowRepeatedOption | bool | permitir misma opción varias veces (p. ej. 2 bolas de chocolate) |
| allowPerOptionQuantity | bool | si false, cantidad por opción siempre 1 |
| defaultOptionQuantity | int | cantidad por selección cuando aplica |

**GroupOption**:

| Atributo | Tipo | Notas |
|---|---|---|
| catalogItemId | UUID | referencia al CatalogItem |
| additionalPrice: Money | >= 0 | precio por unidad de la opción |
| isActive | bool | disponible en el grupo |
| consumption | list[ConsumptionRequirement] | receta de inventario por unidad seleccionada |
| maxPerSelection | int? | límite de cantidad de esta opción por ítem (p. ej. máx 3 bolas de chocolate) |

**ConsumptionRequirement** (valor): `{inventoryItemId, quantity: int, unit}` — cuánto consume del `InventoryItem` por unidad.

### Entidad de selección (lo que envía el cliente)

`Selection` = `{groupId, catalogItemId, quantity}`; un ítem de pedido trae `list[Selection]`.

### Invariantes de personalización (validadas por casos de uso del dominio, en el servidor)

1. Cada `groupId` enviado debe pertenecer a la configuración del producto.
2. Cada `catalogItemId` debe pertenecer al grupo indicado y estar activo (opción y CatalogItem activos).
3. Número de opciones del grupo entre `minSelections` y `maxSelections`.
4. No repetir opciones si `allowRepeatedOption = false`.
5. `quantity` por opción: `1 <= q <= maxPerSelection` y, si `allowPerOptionQuantity = false`, `q == 1`.
6. Si el grupo es `required`, debe enviarse al menos el mínimo.
7. El precio nunca viaja desde el cliente: se recalcula con la configuración vigente.
8. La validación se ejecuta en dos momentos: (a) al consultar/validar catálogo para el cliente (feedback temprano) y (b) obligatoriamente en la transacción de creación del pedido con la versión vigente.
9. Si la configuración cambió entre (a) y (b), gana (b): el pedido se rechaza con el detalle de qué ya no es válido.

## 5. Módulo Inventory

### Entidades

**InventoryItem** (raíz de agregado):

- `id`, `name`, `unit` (g | ml | units)
- `stockQuantity: int >= 0` (físico)
- `reservedQuantity: int >= 0` (reservado)
- `minimumStock: int >= 0`
- `isActive: bool`, `trackStock: bool`
- `version: int` (control de concurrencia optimista, complementa las transacciones)

Disponible = `stockQuantity − reservedQuantity` (si `trackStock = false`, se asume ilimitado).

**Reservation** (raíz de agregado, una por pedido):

- `id`, `orderId`, `lines: list[{inventoryItemId, quantity, unit}]`
- `state`: ACTIVE → CONSUMED | RELEASED | EXPIRED
- `expiresAt`, `createdAt`

**InventoryMovement** (registro append-only; no es agregado con estado mutable):

- `id`, `inventoryItemId`, `quantity` (con signo según tipo), `type` (ENTRY | CONSUMPTION | RESERVE | RELEASE | ADJUSTMENT | RETURN | CORRECTION)
- `orderId?`, `actor?`, `reason?`, `occurredAt`

### Estados y ciclo de vida de la reserva

1. Creación de pedido → transacción: verificar disponibilidad + `reservedQuantity += q` + Reservation ACTIVE + movimientos RESERVE. Todo o nada.
2. Pedido pasa a PREPARING/entrega → consumo: `stockQuantity −= q`, `reservedQuantity −= q`, Reservation CONSUMED, movimientos CONSUMPTION. Idempotente (si la reserva ya está CONSUMED, no-op).
3. Cancelación/expiración → liberación: `reservedQuantity −= q`, Reservation RELEASED/EXPIRED, movimientos RELEASE. Idempotente.
4. Tarea programada: vencidas con pedido aún PENDING → liberar.

### Invariantes de Inventory

1. `stockQuantity >= 0` y `reservedQuantity >= 0` siempre; `reservedQuantity <= stockQuantity`.
2. Ninguna reserva excede lo disponible (`stock − reserved >= requerido`).
3. Verificación y reserva dentro de la MISMA transacción y con actualización atómica condicional (ver protocolo abajo).
4. Toda alteración de cantidad genera `InventoryMovement`.
5. Desactivar un elemento no borra historial ni movimientos.
6. Reservas: una sola ACTIVE por pedido.

### Protocolo de concurrencia (MongoDB, transacciones)

Dentro de la transacción del caso de uso "Crear pedido":

```
Para cada inventoryItem requerido (agrupando consumos por ítem):
  resultado = findOneAndUpdate(
    { _id: itemId, isActive: true,
      $expr: { $and: [
        { $eq: ["$trackStock", true] },  // o bypass si trackStock=false
        { $gte: [{ $subtract: ["$stockQuantity", "$reservedQuantity"] }, requerido] }
      ]}},
    { $inc: { reservedQuantity: +requerido, version: 1 } },
    { session, writeConcern majority }
  )
  si resultado es null → imposible reservar → abortar transacción completa
```

La condición de disponibilidad vive en el **filtro del update atómico**: dos transacciones simultáneas que compitan por la última unidad generan `WriteConflict`; una gana, la otra aborta y su pedido no se crea. No hay ventana entre "consultar" y "reservar". Reintentos controlados solo para `TransientTransactionError`.

Prueba crítica obligatoria (Fase 9, contra Mongo real con replica set): 100 g de chocolate, 2 clientes × 100 g simultáneos → exactamente una reserva exitosa, stock no negativo, sin pedidos parciales.

## 6. Módulo Tables

### Entidades

**Table**: `id, number (único), name?, status (OPEN | CLOSED | DISABLED), isActive, createdAt, updatedAt`.

**Device**: `id, name?, linkedTableId?, credentialHash (token), isActive, createdAt`. Vinculación autorizada por administrador (el token nunca lo genera el cliente).

**TableSession**: `id, tableId, openedAt, closedAt?, status (OPEN | CLOSED)`. Una mesa abierta puede tener una sesión activa (o varias históricas); decisión: **una sesión abierta por mesa a la vez** — flaggeada en §11.

**CustomerSession**: `id, tableSessionId, deviceId, token (hash), openedAt, closedAt?, status`. Cada cliente/dispositivo tiene la suya. No hay carrito compartido entre CustomerSessions.

### Invariantes

1. Los pedidos referencian `customerSessionId`; la mesa se deduce por la cadena sesión → mesa. **Nunca** se acepta `tableId` suelto del cliente.
2. Un Device solo puede tener una CustomerSession activa; su token es opaco y se guarda hasheado.
3. Cerrar una TableSession no debe ser posible con pedidos activos sin antes cancelarlos o entregarlos (regla operativa; flaggeada §11).
4. Una CustomerSession solo crea pedidos si su TableSession está OPEN.

## 7. Módulo Orders

### Entidad Order (raíz de agregado)

- `id, orderNumber (secuencial legible p. ej. #0042), customerSessionId, tableId (denormalizado solo lectura), status, currency: "COP", total: Money, createdAt, acceptedAt?, completedAt?, cancelledAt?, cancelReason?`
- `items: list[OrderItem]` (embebidos)
- `reservationId` (cuando tiene reserva activa/consumida)
- `idempotencyKey` (único junto con customerSessionId)

**OrderItem** (instantánea inmutable):

- `productId` (referencia solo informativa), `productName` (histórico), `basePriceAtOrder: Money`, `quantity: int >= 1`
- `selections: list[{groupId, groupName, groupType?, catalogItemId, optionName, quantity, unitPrice: Money}]` (histórico)
- `optionsPrice: Money`, `unitFinalPrice: Money` = base + opciones, `subtotal: Money`
- `idempotencyKey`

> Prohibido mutar un ítem confirmado. Cambiar el catálogo nunca reescribe pedidos existentes.

### Máquina de estados

```
PENDING → ACCEPTED → PREPARING → READY → DELIVERED
   │          │           │
   └──────────┴───────────┴──→ CANCELLED
   └→ EXPIRED (solo PENDING, por TTL)
```

Transiciones legales (todas validadas en el dominio):

| Desde | Hacia | Efecto en reserva |
|---|---|---|
| PENDING | ACCEPTED | conserva |
| ACCEPTED | PREPARING | conserva (aún no se consume) |
| PREPARING | READY | conserva |
| READY | DELIVERED | **consume** stock reservado (momento de consumo; flaggeada §11 si el propietario prefiere consumir al iniciar preparación) |
| PENDING/ACCEPTED/PREPARING/READY | CANCELLED | libera reserva (si aún no se consumió) |
| PENDING | EXPIRED (TTL) | libera reserva |
| * | misma | idempotente (repetir la misma transición es no-op) |
| cualquier otra | * | rechazada |

### Idempotencia

Colección `idempotency_keys`: `{ key, customerSessionId, scope: "create_order", requestHash, orderId?, createdAt, expiresAt }` con **índice único** `(key, customerSessionId)`. La creación de pedido:

1. Busca la clave (puede estar fuera de la tx, con lectura mayoritaria).
2. Si existe con `orderId` → devolver ese pedido (no crear nada).
3. Si no, dentro de la misma transacción: insertar clave + pedido + reserva atómica. Un duplicado vía índice único ⇒ otro request ya ganó; releer y devolver su resultado.

### Invariantes de Orders

1. Total = Σ subtotales de ítems, calculado por el dominio (Pricing), nunca por el cliente.
2. No se crea pedido sin reserva exitosa cuando hay consumos `trackStock` requeridos.
3. No se aceptan transiciones fuera de la tabla ni mutaciones de ítems confirmados.
4. Un pedido histórico sobrevive intacto a cualquier cambio de catálogo/inventario.

## 8. Módulo Pricing

Servicio de dominio puro `PricingCalculator`:

- precio ítem = `basePrice(product)` + Σ (`unitPrice(option, config vigente)` × cantidad de la selección)
- inputs: instantánea de configuración del producto leída en la transacción; salida: detalle por ítem.
- `Money`: `Amount: int (COP) + currency: Literal["COP"]`. Sin decimales, sin float. Sumas con verificación de moneda.

## 9. Módulo Identity & Access (esqueleto en esta fase)

- `AdminUser` (`id, username, passwordHash, role: OWNER | STAFF, isActive`), JWT de corta vida para endpoints `/admin/**`.
- `CustomerSession` es la credencial del cliente; **no** puede alcanzar rutas administrativas (middleware por tipo de credencial).
- Detalle de rotación de tokens y permisos finos: pendiente de decisión (§11), no bloquea las Fases 3–5.

## 10. Puertos (contratos)

**Entrada** (casos de uso, uno por operación del §8 de la especificación; agrupados por módulo):

- `ProductManagementPort`, `CatalogQueryPort`
- `CustomizationManagementPort` (+ `CustomizationValidationPort` para validar sin crear pedido)
- `InventoryManagementPort` (entradas, ajustes, consultas, liberaciones)
- `TableManagementPort`, `DeviceLinkPort`, `CustomerSessionPort`
- `OrderManagementPort` (crear, consultar, transicionar), `OrderExpirationProcessor` (tarea)

**Salida** (implementados en infraestructura):

- Repositorios: `ProductRepository`, `CatalogItemRepository`, `InventoryItemRepository`, `ReservationRepository`, `InventoryMovementRepository`, `TableRepository`, `DeviceRepository`, `TableSessionRepository`, `CustomerSessionRepository`, `OrderRepository`, `IdempotencyKeyRepository`
- `UnitOfWork` (ya existe), `TransactionManager` (semántica sobre UnitOfWork + reintentos), `ClockPort`, `PasswordHasherPort`, `TokenIssuerPort`

## 11. Decisiones pendientes (no las invento; la implementación las necesita)

| # | Decisión | Impacto | Propuesta por defecto |
|---|---|---|---|
| P1 | ¿Una sola TableSession abierta por mesa a la vez? | Tables | Sí (modelo simple; varias abiertas sería para "cuenta por franja horaria") |
| P2 | Momento de consumo del inventario: al DELIVERED o al iniciar PREPARING | Orders/Inventory | DELIVERED (lo propuesto) |
| P3 | ¿Los ítems de pedido permiten quantity > 1 del mismo producto configurado? | Orders | Sí (ej. 2 conos iguales), con reservas multiplicadas |
| P4 | Caducidad de la clave de idempotencia | Orders | 24 h |
| P5 | Autenticación admin: ¿JWT user/pass simple ahora, o OAuth? | Identity | JWT local user/pass (efímero para desarrollo) |
| P6 | ¿IVA/impuestos en el precio? | Pricing | Fuera de alcance: precios finales de carta, sin cálculo fiscal |
| P7 | ¿Notificaciones en tiempo real (WebSocket) de estados al cliente? | Bootstrap | Fuera de alcance de esta etapa; polling REST |
| P8 | Orden de mesa: ¿`number` único e inmutable? | Tables | Sí |

## 12. Colecciones MongoDB preliminares

| Colección | Contenido |
|---|---|
| `catalog_items` | opciones de personalización |
| `products` | productos + configuración de personalización embebida |
| `inventory_items` | existencias (+ `version`) |
| `inventory_movements` | auditoría append-only |
| `reservations` | reservas por pedido |
| `tables`, `devices`, `table_sessions`, `customer_sessions` | módulo Tables |
| `orders` | pedidos con ítems-instantánea embebidos |
| `idempotency_keys` | claves únicas de operación |
| `admin_users` | identidad (fase posterior) |

Índices críticos: único en `orders.idempotencyKey+customerSessionId`, `devices.tokenHash`, `tables.number`, `table_sessions.tableId+status`.
