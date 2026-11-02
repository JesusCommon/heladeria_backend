"""Fixtures compartidas de dominio (catálogo ejemplo de la especificación)."""

import uuid

from heladeria_backend.catalog.domain.catalog import (
    ConsumptionRequirement,
    CustomizationGroup,
    GroupOption,
    Product,
)


def flavor_id() -> str:
    return str(uuid.uuid4())


def cone_product(sabores_peces: list[str], extra: int = 0) -> Product:
    """Helado de cono: 1 a 3 bolas (§ 2.3)."""
    return Product(
        name="Helado de cono",
        kind="cone",
        base_price=7000 + extra,
        customization=[
            CustomizationGroup(
                name="Sabores",
                kind="balls",
                min_selections=1,
                max_selections=3,
                required=True,
                allow_repeated=True,
                allow_per_option_quantity=True,
                options=[
                    GroupOption(
                        catalog_item_id=s,
                        additional_price=2500,
                        consumption=[ConsumptionRequirement(inventory_item_id=f"inv-{s}", quantity=100, unit="g")],
                    )
                    for s in sabores_peces
                ],
            ),
            CustomizationGroup(
                name="Salsas",
                min_selections=0,
                max_selections=2,
                allow_repeated=False,
                options=[
                    GroupOption(catalog_item_id=f"salsa-{i}", additional_price=1000)
                    for i in (1, 2)
                ],
            ),
            CustomizationGroup(
                name="Decoraciones",
                min_selections=0,
                max_selections=2,
                allow_repeated=False,
                options=[
                    GroupOption(catalog_item_id=f"deco-{i}", additional_price=500)
                    for i in (1, 2)
                ],
            ),
        ],
    )


def special_cup(sabores_peces: list[str]) -> Product:
    """Copa especial: 4 bolas, 3 salsas, 5 decoraciones."""
    return Product(
        name="Copa especial",
        kind="sundae",
        base_price=12000,
        customization=[
            CustomizationGroup(
                name="Sabores",
                min_selections=1,
                max_selections=4,
                required=True,
                allow_repeated=True,
                allow_per_option_quantity=True,
                options=[
                    GroupOption(catalog_item_id=s, additional_price=2500) for s in sabores_peces
                ],
            ),
            CustomizationGroup(
                name="Salsas",
                min_selections=0,
                max_selections=3,
                allow_repeated=False,
                options=[GroupOption(catalog_item_id=f"salsa-{i}") for i in range(1, 5)],
            ),
            CustomizationGroup(
                name="Decoraciones",
                min_selections=0,
                max_selections=5,
                allow_repeated=False,
                options=[GroupOption(catalog_item_id=f"deco-{i}") for i in range(1, 7)],
            ),
        ],
    )
