"""API de catálogo público (para el dispositivo/mesa) y cotización."""


from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from heladeria_backend.catalog.domain.catalog import (
    CustomizationValidator,
    SelectionInput,
)
from heladeria_backend.identity.adapters.api_security import (
    container,
)
from heladeria_backend.pricing.domain.service import price_line
from heladeria_backend.shared.domain.errors import NotFoundError

router = APIRouter(prefix="/public", tags=["public"])


async def _availability_map(request: Request) -> dict[str, bool]:
    """:id -> puede seleccionarse (activo + stock suficiente para 1 unidad)."""
    c = container(request)
    avail: dict[str, bool] = {}
    for item in await c.inventory_items.list():
        ok = item.is_active if item.track_stock else True
        avail[item.id] = bool(ok)
    products = await c.products.list(active_only=True)
    for product in products:
        reqs = product.consumptions_for([], 1)
        avail.setdefault(product.id, product.is_active)
        # base_consumption disponible
        product_ok = all(avail.get(item_id, True) or not any(
            i.id == item_id and i.track_stock
            for i in await c.inventory_items.list()
        ) for item_id in reqs)
        avail[product.id] = product_ok
    return avail


@router.get("/catalog")
async def public_catalog(request: Request):
    c = container(request)
    products = await c.products.list(active_only=True)
    items = {i.id: i for i in await c.catalog_items.list()}
    inv = {i.id: i for i in await c.inventory_items.list()}

    out = []
    for p in products:
        base_ok = all(
            not inv[req.inventory_item_id].track_stock
            or inv[req.inventory_item_id].is_active
            and inv[req.inventory_item_id].available >= req.quantity
            for req in p.base_consumption
            if req.inventory_item_id in inv
        )
        groups_out = []
        for g in p.customization:
            options_out = []
            for o in g.options:
                ci = items.get(o.catalog_item_id)
                inv_lines_ok = all(
                    not inv[req.inventory_item_id].track_stock
                    or (inv[req.inventory_item_id].is_active and inv[req.inventory_item_id].available >= req.quantity)
                    for req in o.consumption
                    if req.inventory_item_id in inv
                )
                options_out.append({
                    "catalog_item_id": o.catalog_item_id,
                    "name": ci.name if ci else o.catalog_item_id,
                    "kind": ci.kind if ci else "extra",
                    "additional_price": o.additional_price,
                    "is_selectable": o.is_active and ci is not None and ci.is_active and inv_lines_ok,
                })
            groups_out.append({
                "id": g.id,
                "name": g.name,
                "min_selections": g.min_selections,
                "max_selections": g.max_selections,
                "required": g.required,
                "allow_repeated": g.allow_repeated,
                "allow_per_option_quantity": g.allow_per_option_quantity,
                "options": options_out,
            })
        out.append({
            "id": p.id,
            "name": p.name,
            "kind": p.kind,
            "description": p.description,
            "base_price": p.base_price,
            "currency": "COP",
            "is_selectable": base_ok,
            "groups": groups_out,
        })
    return out


class SelectionDTO(BaseModel):
    group_id: str
    catalog_item_id: str
    quantity: int = Field(default=1, ge=1)


class QuoteDTO(BaseModel):
    product_id: str
    quantity: int = Field(default=1, ge=1)
    selections: list[SelectionDTO] = Field(default_factory=list)


@router.post("/price-quote")
async def price_quote(dto: QuoteDTO, request: Request):
    """Cotización en servidor; jamás se aceptan precios del cliente."""
    c = container(request)
    product = await c.products.get(dto.product_id)
    if product is None:
        raise NotFoundError("Producto no existe")
    selections = [SelectionInput(group_id=s.group_id, catalog_item_id=s.catalog_item_id, quantity=s.quantity)
                  for s in dto.selections]
    CustomizationValidator.validate(product, selections)
    priced = price_line(product, selections, dto.quantity)
    return {
        "product_id": product.id,
        "quantity": dto.quantity,
        "base_price": priced.base_price,
        "options_price": priced.options_price,
        "unit_final_price": priced.unit_final_price,
        "subtotal": priced.subtotal,
        "currency": "COP",
    }
