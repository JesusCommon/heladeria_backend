"""API de administración: productos y catálogo."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from heladeria_backend.catalog.domain.catalog import (
    CatalogItem,
    ConsumptionRequirement,
    CustomizationGroup,
    GroupOption,
    Product,
)
from heladeria_backend.identity.adapters.api_security import (
    container,
    require_owner,
    require_staff,
)
from heladeria_backend.identity.domain.identity import Principal
from heladeria_backend.shared.domain.errors import NotFoundError

router = APIRouter(prefix="/admin", tags=["admin-catalog"])


class ConsumptionDTO(BaseModel):
    inventory_item_id: str
    quantity: int = Field(gt=0)
    unit: Literal["g", "ml", "unit"]


class GroupOptionDTO(BaseModel):
    catalog_item_id: str
    additional_price: int = Field(default=0, ge=0)
    is_active: bool = True
    max_per_selection: int | None = Field(default=None, ge=1)
    consumption: list[ConsumptionDTO] = Field(default_factory=list)


class GroupDTO(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1)
    kind: str = "choice"
    min_selections: int = Field(default=0, ge=0)
    max_selections: int = Field(gt=0)
    required: bool = False
    allow_repeated: bool = True
    allow_per_option_quantity: bool = False
    options: list[GroupOptionDTO] = Field(default_factory=list)


class ProductCreateDTO(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None
    kind: str = "generic"
    base_price: int = Field(ge=0)
    base_consumption: list[ConsumptionDTO] = Field(default_factory=list)
    customization: list[GroupDTO] = Field(default_factory=list)


class ProductUpdateDTO(ProductCreateDTO):
    is_active: bool = True


class CatalogItemCreateDTO(BaseModel):
    name: str = Field(min_length=1)
    kind: Literal["flavor", "sauce", "topping", "extra"]
    description: str | None = None


def _domain_group(g: GroupDTO) -> CustomizationGroup:
    return CustomizationGroup(
        id=g.id or str(uuid.uuid4()),
        name=g.name,
        kind=g.kind,
        min_selections=g.min_selections,
        max_selections=g.max_selections,
        required=g.required,
        allow_repeated=g.allow_repeated,
        allow_per_option_quantity=g.allow_per_option_quantity,
        options=[
            GroupOption(
                catalog_item_id=o.catalog_item_id,
                additional_price=o.additional_price,
                is_active=o.is_active,
                max_per_selection=o.max_per_selection,
                consumption=[
                    ConsumptionRequirement(inventory_item_id=c.inventory_item_id, quantity=c.quantity, unit=c.unit)
                    for c in o.consumption
                ],
            )
            for o in g.options
        ],
    )


def _domain_product(dto: ProductCreateDTO | ProductUpdateDTO, product_id: str | None = None) -> Product:
    product = Product(
        id=product_id or str(uuid.uuid4()),
        name=dto.name,
        description=dto.description,
        kind=dto.kind,
        base_price=dto.base_price,
        base_consumption=[
            ConsumptionRequirement(inventory_item_id=c.inventory_item_id, quantity=c.quantity, unit=c.unit)
            for c in dto.base_consumption
        ],
        customization=[_domain_group(g) for g in dto.customization],
    )
    if isinstance(dto, ProductUpdateDTO):
        product.is_active = dto.is_active
    return product


def _product_out(p: Product) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "kind": p.kind,
        "base_price": p.base_price,
        "currency": "COP",
        "is_active": p.is_active,
        "base_consumption": [c.model_dump() for c in p.base_consumption],
        "customization": [
            {
                "id": g.id,
                "name": g.name,
                "kind": g.kind,
                "min_selections": g.min_selections,
                "max_selections": g.max_selections,
                "required": g.required,
                "allow_repeated": g.allow_repeated,
                "allow_per_option_quantity": g.allow_per_option_quantity,
                "options": [
                    {
                        "catalog_item_id": o.catalog_item_id,
                        "additional_price": o.additional_price,
                        "is_active": o.is_active,
                        "max_per_selection": o.max_per_selection,
                        "consumption": [c.model_dump() for c in o.consumption],
                    }
                    for o in g.options
                ],
            }
            for g in p.customization
        ],
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


@router.post("/products", status_code=201)
async def create_product(
    dto: ProductCreateDTO,
    request: Request,
    _: Annotated[Principal, Depends(require_owner)],
) -> dict:
    c = container(request)
    product = _domain_product(dto)
    await c.products.save(product)
    return _product_out(product)


@router.put("/products/{product_id}")
async def update_product(
    product_id: str,
    dto: ProductUpdateDTO,
    request: Request,
    _: Annotated[Principal, Depends(require_owner)],
) -> dict:
    c = container(request)
    existing = await c.products.get(product_id)
    if not existing:
        raise NotFoundError(f"Producto {product_id} no existe")
    product = _domain_product(dto, product_id=product_id)
    product.created_at = existing.created_at
    await c.products.save(product)
    return _product_out(product)


@router.get("/products")
async def list_products(
    request: Request,
    _: Annotated[Principal, Depends(require_staff)],
) -> list[dict]:
    c = container(request)
    products = await c.products.list()
    return [_product_out(p) for p in products]


@router.get("/products/{product_id}")
async def get_product(
    product_id: str,
    request: Request,
    _: Annotated[Principal, Depends(require_staff)],
) -> dict:
    c = container(request)
    product = await c.products.get(product_id)
    if not product:
        raise NotFoundError(f"Producto {product_id} no existe")
    return _product_out(product)


@router.delete("/products/{product_id}", status_code=204)
async def deactivate_product(
    product_id: str,
    request: Request,
    _: Annotated[Principal, Depends(require_owner)],
):
    c = container(request)
    product = await c.products.get(product_id)
    if not product:
        raise NotFoundError(f"Producto {product_id} no existe")
    product.is_active = False
    await c.products.save(product)


class CatalogItemUpdateDTO(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


def _item_out(i: CatalogItem) -> dict:
    return {
        "id": i.id,
        "name": i.name,
        "kind": i.kind,
        "description": i.description,
        "is_active": i.is_active,
    }


@router.post("/catalog-items", status_code=201)
async def create_catalog_item(
    dto: CatalogItemCreateDTO,
    request: Request,
    _: Annotated[Principal, Depends(require_owner)],
) -> dict:
    c = container(request)
    item = CatalogItem(name=dto.name, kind=dto.kind, description=dto.description)
    await c.catalog_items.save(item)
    return _item_out(item)


@router.patch("/catalog-items/{item_id}")
async def update_catalog_item(
    item_id: str,
    dto: CatalogItemUpdateDTO,
    request: Request,
    _: Annotated[Principal, Depends(require_owner)],
) -> dict:
    c = container(request)
    item = await c.catalog_items.get(item_id)
    if not item:
        raise NotFoundError(f"Item {item_id} no existe")
    if dto.name is not None:
        item.name = dto.name
    if dto.description is not None:
        item.description = dto.description
    if dto.is_active is not None:
        item.is_active = dto.is_active
    await c.catalog_items.save(item)
    return _item_out(item)


@router.get("/catalog-items")
async def list_catalog_items(
    request: Request,
    _: Annotated[Principal, Depends(require_staff)],
    active_only: bool = False,
) -> list[dict]:
    c = container(request)
    items = await c.catalog_items.list(active_only)
    return [_item_out(i) for i in items]
