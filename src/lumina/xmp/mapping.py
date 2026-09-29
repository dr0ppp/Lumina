"""Explicit mappings for the modern Camera Raw basic-adjustment fields."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .errors import LuminaError

CRS = "http://ns.adobe.com/camera-raw-settings/1.0/"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
XMP_META = "adobe:ns:meta/"


@dataclass(frozen=True)
class Parameter:
    xmp_name: str
    integer: bool = True


PARAMETERS = {
    "Exposure": Parameter("Exposure2012", integer=False),
    "Contrast": Parameter("Contrast2012"),
    "Highlights": Parameter("Highlights2012"),
    "Shadows": Parameter("Shadows2012"),
    "Whites": Parameter("Whites2012"),
    "Blacks": Parameter("Blacks2012"),
    "Temperature": Parameter("Temperature"),
    "Tint": Parameter("Tint"),
    "Vibrance": Parameter("Vibrance"),
    "Saturation": Parameter("Saturation"),
}
METADATA = ("Version", "ProcessVersion", "WhiteBalance", "HasSettings", "RawFileName")
WATCHED_FIELDS = {p.xmp_name for p in PARAMETERS.values()} | set(METADATA) | {
    "AutoTone", "AutoExposure",
}
# Deliberately narrow: observed in the user's ACR 17.5 sidecar, not a claim
# of visual compatibility with every Camera Raw release. Never upgrade it.
WRITABLE_PROCESS_VERSIONS = frozenset({"15.4"})


def decimal_value(value: object, name: str) -> Decimal:
    text = str(value).strip()
    if not text or len(text) > 64 or isinstance(value, bool):
        raise LuminaError(f"{name} 必须是有限数值。")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise LuminaError(f"{name} 不是有效数值：{text!r}") from exc
    if not number.is_finite() or number.copy_abs() > Decimal("1e9"):
        raise LuminaError(f"{name} 必须是有限且合理的数值。")
    return number


def parameter_value(value: str, name: str) -> int | float:
    number = decimal_value(value, name)
    if PARAMETERS[name].integer:
        if number != number.to_integral_value():
            raise LuminaError(f"{name} 应为整数，XMP 中记录了 {value!r}。")
        return int(number)
    return float(number)


def exposure_value(value: object) -> Decimal:
    number = decimal_value(value, "Exposure")
    if not Decimal("-5") <= number <= Decimal("5"):
        raise LuminaError("曝光必须在 -5.00 到 +5.00 EV 之间。")
    if number != number.quantize(Decimal("0.01")):
        raise LuminaError("曝光最多支持两位有效小数；不会自动舍入。")
    return abs(number) if number == 0 else number
