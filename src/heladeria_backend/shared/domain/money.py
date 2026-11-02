"""Primitivas de dinero.

Decisión D1: COP con cantidades enteras (sin decimales). Nunca float.
Todas las entidades de dominio usan `COP = int` validado (>= 0) y
`currency` queda constante global para persistir.
"""

from typing import Literal

CURRENCY = Literal["COP"]
CURRENCY_CODE: CURRENCY = "COP"
