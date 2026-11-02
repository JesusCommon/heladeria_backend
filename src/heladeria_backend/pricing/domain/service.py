"""Servicio puro de Precios (Decisión D1: COP entero).

El dominio calcula a partir de la configuración vigente; nunca a partir de
valores enviados por el cliente. Salidas tipo detalle para persistir como
instantánea en el pedido.
"""

from dataclasses import dataclass, field

from heladeria_backend.catalog.domain.catalog import Product, SelectionInput
from heladeria_backend.shared.domain.money import CURRENCY_CODE


@dataclass
class SelectionSnapshot:
    group_id: str
    group_name: str
    catalog_item_id: str
    quantity: int
    unit_price: int


@dataclass
class LinePrice:
    base_price: int
    options_price: int
    unit_final_price: int
    subtotal: int
    quantity: int
    currency: str = CURRENCY_CODE
    selections: list[SelectionSnapshot] = field(default_factory=list)


def price_line(product: Product, selections: list[SelectionInput], quantity: int) -> LinePrice:
    if quantity < 1:
        raise ValueError("quantity >= 1")

    snap_selections: list[SelectionSnapshot] = []
    options_total = 0
    for s in selections:
        group = product.group(s.group_id)
        opt = product.option(s.group_id, s.catalog_item_id)
        # el validator ya corrió; defensivo mínimo
        if group is None or opt is None:
            raise ValueError("Selección no coincide con configuración del producto")
        unit_price = opt.additional_price
        options_total += unit_price * s.quantity
        snap_selections.append(
            SelectionSnapshot(
                group_id=group.id,
                group_name=group.name,
                catalog_item_id=s.catalog_item_id,
                quantity=s.quantity,
                unit_price=unit_price,
            )
        )

    unit_final = product.base_price + options_total
    return LinePrice(
        base_price=product.base_price,
        options_price=options_total,
        unit_final_price=unit_final,
        subtotal=unit_final * quantity,
        quantity=quantity,
        selections=snap_selections,
    )


def order_total(lines: list[LinePrice]) -> int:
    return sum(line.subtotal for line in lines)
