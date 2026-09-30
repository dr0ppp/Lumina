"""Shared numeric rules; no XML, filesystem, CLI or language parsing."""

from dataclasses import dataclass
from decimal import Context, Decimal, InvalidOperation
import re

from .errors import LuminaError


def decimal_value(value: object, name: str) -> Decimal:
    text = str(value).strip()
    if not text or len(text) > 64 or isinstance(value, bool):
        raise LuminaError(f"{name} 必须是有限数值。")
    # Decimal accepts underscores and Unicode digits that are not XMP numbers.
    if re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", text) is None:
        raise LuminaError(f"{name} 不是有效数值：{text!r}")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise LuminaError(f"{name} 不是有效数值：{text!r}") from exc
    if not number.is_finite() or number.copy_abs() > Decimal("1e9"):
        raise LuminaError(f"{name} 必须是有限且合理的数值。")
    return number.copy_abs() if number.is_zero() else number


@dataclass(frozen=True)
class ParameterRule:
    minimum: int
    maximum: int
    integer: bool = True
    unit: str = ""

    def validate(self, value: object, name: str, *, relative: bool = False) -> Decimal:
        number = decimal_value(value, name)
        if self.integer:
            if number != number.to_integral_value():
                raise LuminaError(f"{name} 必须是整数；不会自动舍入。")
        elif number != number.quantize(Decimal("0.01"), context=Context(prec=80)):
            raise LuminaError(f"{name} 最多支持两位有效小数；不会自动舍入。")
        low, high = self.minimum, self.maximum
        if relative:
            low, high = -(high - low), high - low
        if not low <= number <= high:
            kind = "调整量" if relative else "最终值"
            raise LuminaError(f"{name} {kind}必须在 {low} 到 {high} 之间；不会自动截断。")
        return number


RULES = {
    "Exposure": ParameterRule(-5, 5, integer=False, unit="EV"),
    "Contrast": ParameterRule(-100, 100),
    "Highlights": ParameterRule(-100, 100),
    "Shadows": ParameterRule(-100, 100),
    "Whites": ParameterRule(-100, 100),
    "Blacks": ParameterRule(-100, 100),
    "Temperature": ParameterRule(2000, 50000, unit="K"),
    "Tint": ParameterRule(-150, 150),
    "Vibrance": ParameterRule(-100, 100),
    "Saturation": ParameterRule(-100, 100),
}


def json_number(name: str, value: Decimal) -> int | float:
    return int(value) if RULES[name].integer else float(value)
