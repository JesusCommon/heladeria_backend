"""Pruebas unitarias de la máquina de estados del pedido (§ 5.3)."""

import pytest

from heladeria_backend.orders.domain.order import LEGAL_TRANSITIONS, Order, OrderStatus
from heladeria_backend.shared.domain.errors import ConflictError


def order(status: OrderStatus) -> Order:
    o = Order(
        order_number=1,
        customer_session_id="cs",
        table_session_id="ts",
        table_id="t",
        status=status,
        total=0,
        items=[],
    )
    return o


def test_full_happy_path():
    o = order(OrderStatus.PENDING)
    for s in (OrderStatus.ACCEPTED, OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.DELIVERED):
        o.transition(s)
    assert o.status is OrderStatus.DELIVERED
    assert o.completed_at is not None


def test_illegal_transition_delivered_to_preparing():
    o = order(OrderStatus.PENDING)
    o.transition(OrderStatus.ACCEPTED)
    o.transition(OrderStatus.PREPARING)
    o.transition(OrderStatus.READY)
    o.transition(OrderStatus.DELIVERED)
    with pytest.raises(ConflictError, match="ilegal"):
        o.transition(OrderStatus.PREPARING)


def test_illegal_jump_accept_to_delivered():
    o = order(OrderStatus.ACCEPTED)
    with pytest.raises(ConflictError):
        o.transition(OrderStatus.DELIVERED)


def test_same_transition_is_idempotent():
    o = order(OrderStatus.PENDING)
    o.transition(OrderStatus.ACCEPTED)
    o.transition(OrderStatus.ACCEPTED)  # no-op, no error
    assert o.status is OrderStatus.ACCEPTED


def test_terminal_statuses_have_no_exits():
    assert LEGAL_TRANSITIONS[OrderStatus.DELIVERED] == set()
    assert LEGAL_TRANSITIONS[OrderStatus.CANCELLED] == set()
    assert LEGAL_TRANSITIONS[OrderStatus.EXPIRED] == set()


def test_total_tampering_rejected_by_invariant():
    import pydantic
    with pytest.raises(pydantic.ValidationError):
        Order(
            order_number=2,
            customer_session_id="cs",
            table_session_id="ts",
            table_id="t",
            total=9999,
            items=[],
        )


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        (OrderStatus.PENDING, OrderStatus.ACCEPTED),
        (OrderStatus.PENDING, OrderStatus.EXPIRED),
        (OrderStatus.ACCEPTED, OrderStatus.PREPARING),
        (OrderStatus.PREPARING, OrderStatus.READY),
        (OrderStatus.READY, OrderStatus.DELIVERED),
    ],
)
def test_legal_transitions_matrix(from_status, to_status):
    o = order(from_status)
    o.transition(to_status)
    assert o.status is to_status
