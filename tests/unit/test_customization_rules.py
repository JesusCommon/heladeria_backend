"""Pruebas unitarias de las invariantes de personalización (§ 2.4)."""

import pytest

from heladeria_backend.catalog.domain.catalog import (
    CustomizationValidator,
    SelectionInput,
)
from heladeria_backend.shared.domain.errors import DomainValidationError

from .fixtures_catalog import cone_product, flavor_id, special_cup

CHOCO = flavor_id()
VANI = flavor_id()
FRESA = flavor_id()


def cone():
    p = cone_product([CHOCO, VANI, FRESA])
    g = p.customization[0]
    return p, g


def test_cone_max_3_balls_rejects_4():
    p, g = cone()
    for item in (CHOCO, VANI, FRESA, CHOCO):
        pass
    sels = [SelectionInput(group_id=g.id, catalog_item_id=CHOCO, quantity=4)]
    with pytest.raises(DomainValidationError, match="máximo"):
        CustomizationValidator.validate(p, sels)


def test_cone_accepts_3_balls():
    p, g = cone()
    CustomizationValidator.validate(
        p,
        [
            SelectionInput(group_id=g.id, catalog_item_id=CHOCO, quantity=1),
            SelectionInput(group_id=g.id, catalog_item_id=CHOCO, quantity=1),
            SelectionInput(group_id=g.id, catalog_item_id=VANI, quantity=1),
        ],
    )


def test_cone_default_4_balls_accepted_for_special_cup():
    p = special_cup([CHOCO, VANI, FRESA])
    g = p.customization[0]
    CustomizationValidator.validate(
        p,
        [
            SelectionInput(group_id=g.id, catalog_item_id=CHOCO, quantity=2),
            SelectionInput(group_id=g.id, catalog_item_id=VANI, quantity=2),
        ],
    )
    with pytest.raises(DomainValidationError, match="máximo"):
        CustomizationValidator.validate(
            p,
            [
                SelectionInput(group_id=g.id, catalog_item_id=CHOCO, quantity=3),
                SelectionInput(group_id=g.id, catalog_item_id=VANI, quantity=2),
            ],
        )


def test_foreign_group_rejected():
    p, g = cone()
    foreign = str(__import__("uuid").uuid4())
    with pytest.raises(DomainValidationError, match="no existe"):
        CustomizationValidator.validate(
            p,
            [SelectionInput(group_id=foreign, catalog_item_id=CHOCO, quantity=1)],
        )


def test_option_not_in_group_rejected():
    p, g = cone()
    salsa_group = p.customization[1]
    with pytest.raises(DomainValidationError, match="no pertenece"):
        CustomizationValidator.validate(
            p,
            [SelectionInput(group_id=salsa_group.id, catalog_item_id=CHOCO, quantity=1)],
        )


def test_inactive_option_rejected():
    p, _ = cone_product([CHOCO, VANI, FRESA]), None
    g = p.customization[0]
    g.options[0].is_active = False
    with pytest.raises(DomainValidationError, match="inactiva"):
        CustomizationValidator.validate(p, [SelectionInput(group_id=g.id, catalog_item_id=CHOCO, quantity=1)])


def test_repetition_blocked_when_disallowed():
    p, _g = cone()
    sabor = p.customization[0]
    salsa = p.customization[1]
    sels = [
        SelectionInput(group_id=sabor.id, catalog_item_id=CHOCO, quantity=1),
        SelectionInput(group_id=salsa.id, catalog_item_id="salsa-1", quantity=1),
        SelectionInput(group_id=salsa.id, catalog_item_id="salsa-1", quantity=1),
    ]
    with pytest.raises(DomainValidationError, match="repetir"):
        CustomizationValidator.validate(p, sels)


def test_required_group_missing_min_rejected():
    p, g = cone()
    # Sabores es required min 1
    with pytest.raises(DomainValidationError, match="mínimo"):
        CustomizationValidator.validate(p, [])


def test_optional_group_can_be_empty():
    p, g = cone()
    salsa = p.customization[1]
    CustomizationValidator.validate(
        p,
        [
            SelectionInput(group_id=g.id, catalog_item_id=CHOCO, quantity=1),
        ],
    )


def test_per_option_quantity_blocked_when_disallowed():
    p, _g = cone()
    sabor, salsa, deco = p.customization
    salsa.allow_repeated = True  # caso puro de cantidad por opción
    with pytest.raises(DomainValidationError, match="no permite cantidad"):
        CustomizationValidator.validate(
            p,
            [
                SelectionInput(group_id=sabor.id, catalog_item_id=CHOCO, quantity=1),
                SelectionInput(group_id=salsa.id, catalog_item_id="salsa-1", quantity=2),
            ],
        )


def test_max_per_selection_limit():
    p = special_cup([CHOCO])
    g = p.customization[0]
    g.options[0].max_per_selection = 3
    with pytest.raises(DomainValidationError, match="máx"):
        CustomizationValidator.validate(
            p, [SelectionInput(group_id=g.id, catalog_item_id=CHOCO, quantity=4)]
        )


def test_foreign_product_group_sent_in_another_product():
    """Mandar el grupo de la copa especial sobre el cono debe rechazar."""
    cone = cone_product([CHOCO])
    cup = special_cup([VANI])
    with pytest.raises(DomainValidationError):
        CustomizationValidator.validate(
            cone,
            [SelectionInput(group_id=cup.customization[0].id, catalog_item_id=VANI, quantity=1)],
        )
