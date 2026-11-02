"""Dominio del catálogo y reglas de personalización configurables.

Nada hardcodeado: límites y opciones viven en la configuración persistida
de cada producto (Product.customization).
"""

from pydantic import BaseModel, Field, model_validator
from typing import Literal
import inspect
import uuid

from heladeria_backend.shared.domain.errors import DomainValidationError
from heladeria_backend.shared.domain.mixins import TimestampMixin

ItemKind = Literal["flavor", "sauce", "topping", "extra"]
UNIT = Literal["g", "ml", "unit"]


def new_id() -> str:
    return str(uuid.uuid4())


class ConsumptionRequirement(BaseModel):
    """Consume `quantity` unidades de `inventory_item_id` por unidad aplicada."""

    inventory_item_id: str
    quantity: int = Field(gt=0)
    unit: UNIT


class CatalogItem(TimestampMixin):
    id: str = Field(default_factory=new_id)
    name: str = Field(min_length=1)
    kind: ItemKind
    description: str | None = None
    is_active: bool = True


class GroupOption(BaseModel):
    catalog_item_id: str
    additional_price: int = Field(default=0, ge=0, description="COP por unidad de la opción")
    is_active: bool = True
    max_per_selection: int | None = Field(default=None, ge=1)
    consumption: list[ConsumptionRequirement] = Field(default_factory=list)


class CustomizationGroup(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str = Field(min_length=1)
    kind: str = Field(default="choice")
    min_selections: int = Field(default=0, ge=0)
    max_selections: int = Field(gt=0)
    required: bool = False
    allow_repeated: bool = True
    allow_per_option_quantity: bool = False
    options: list[GroupOption] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> "CustomizationGroup":
        if self.required and self.min_selections < 1:
            raise DomainValidationError(f"Grupo '{self.name}' requerido exige min_selections>=1")
        if self.min_selections > self.max_selections:
            raise DomainValidationError(f"Grupo '{self.name}': min > max")
        ids = [o.catalog_item_id for o in self.options]
        if len(ids) != len(set(ids)):
            raise DomainValidationError(f"Grupo '{self.name}': opción duplicada")
        return self


class Product(TimestampMixin):
    id: str = Field(default_factory=new_id)
    name: str = Field(min_length=1)
    description: str | None = None
    kind: str = Field(default="generic")
    base_price: int = Field(ge=0, description="COP")
    is_active: bool = True
    base_consumption: list[ConsumptionRequirement] = Field(default_factory=list)
    customization: list[CustomizationGroup] = Field(default_factory=list)

    @model_validator(mode="before")
    def _name_check(cls, data):
        if isinstance(data, dict) and not str(data.get("name") or "").strip():
            raise ValueError("name no puede estar vacío")
        return data

    def group(self, group_id: str) -> CustomizationGroup | None:
        return next((g for g in self.customization if g.id == group_id), None)

    def option(self, group_id: str, catalog_item_id: str) -> GroupOption | None:
        g = self.group(group_id)
        if g is None:
            return None
        return next((o for o in g.options if o.catalog_item_id == catalog_item_id), None)

    def consumptions_for(self, selections: list["SelectionInput"], line_quantity: int) -> dict[str, int]:
        """Agrega recetas por elemento. La unidad base se multiplica por la
        cantidad del producto; las opciones por su cantidad. Un mismo
        inventory_item_id suma una única entrada (evita descuento doble)."""
        agg: dict[str, int] = {}
        for req in self.base_consumption:
            agg[req.inventory_item_id] = agg.get(req.inventory_item_id, 0) + req.quantity * line_quantity
        for sel in selections:
            opt = self.option(sel.group_id, sel.catalog_item_id)
            if opt is None:  # será validado por el validator; aquí toleramos
                continue
            for req in opt.consumption:
                agg[req.inventory_item_id] = agg.get(req.inventory_item_id, 0) + req.quantity * sel.quantity
        return agg


class SelectionInput(BaseModel):
    group_id: str
    catalog_item_id: str
    quantity: int = Field(default=1, ge=1)


class CustomizationValidator:
    """Valida SelectionInput contra la configuración del producto.

    Reglas financiadas por la especificación §2.4:
      - grupo inexistente / ajeno al producto
      - opción ajena al grupo o desactivada
      - mínimos / máximos del grupo (cuenta = suma de cantidades)
      - repetición bloqueada cuando allow_repeated = False
      - cantidad por opción siempre 1 cuando allow_per_option_quantity = False
      - límite por opción (max_per_selection)
      - red de obligatoriedad (required ⇒ al menos min)
    """

    @staticmethod
    def validate(product: Product, selections: list[SelectionInput],
                 require_required_groups: bool = True) -> None:
        counts_per_group: dict[str, dict[str, int]] = {}
        for s in selections:
            group = product.group(s.group_id)
            if group is None:
                raise DomainValidationError(f"Grupo '{s.group_id}' no existe en '{product.name}'")
            option = product.option(group.id, s.catalog_item_id)
            if option is None:
                raise DomainValidationError(
                    f"La opción {s.catalog_item_id} no pertenece al grupo '{group.name}' de '{product.name}'"
                )
            if not option.is_active:
                raise DomainValidationError(f"Opción '{option.catalog_item_id}' inactiva en '{group.name}'")
            g = counts_per_group.setdefault(group.id, {})
            g[s.catalog_item_id] = g.get(s.catalog_item_id, 0) + s.quantity
            gcounts = counts_per_group[group.id]

        for group in product.customization:
            sel_map = counts_per_group.get(group.id, {})
            total = sum(sel_map.values())
            repeats = {k: v for k, v in sel_map.items() if v > 1}
            if not group.allow_repeated and repeats:
                raise DomainValidationError(f"Grupo '{group.name}': no puede repetir opciones")
            effective = total if group.allow_repeated else len(sel_map)
            if group.required and require_required_groups and effective < group.min_selections:
                raise DomainValidationError(f"Grupo '{group.name}': mínimo {group.min_selections}")
            if sel_map and effective > group.max_selections:
                raise DomainValidationError(f"Grupo '{group.name}': máximo {group.max_selections} (recibido {effective})")
            for item_id, qty in sel_map.items():
                opt = product.option(group.id, item_id)
                if not group.allow_per_option_quantity and qty > 1:
                    raise DomainValidationError(f"Grupo '{group.name}': no permite cantidad por opción")
                if opt and opt.max_per_selection and qty > opt.max_per_selection:
                    raise DomainValidationError(
                        f"Grupo '{group.name}': '{item_id}' admite máx {opt.max_per_selection} por selección"
                    )
