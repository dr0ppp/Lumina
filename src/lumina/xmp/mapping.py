"""Explicit mappings for the modern Camera Raw basic-adjustment fields."""

from dataclasses import dataclass
from decimal import Context, Decimal

from ..parameters import decimal_value
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
WRITABLE_PARAMETERS = frozenset(PARAMETERS) - {"Temperature", "Tint"}


def parameter_value(value: str, name: str) -> int | float:
    number = decimal_value(value, name)
    if PARAMETERS[name].integer:
        if number != number.to_integral_value():
            raise LuminaError(f"{name} 应为整数，XMP 中记录了 {value!r}。")
        return int(number)
    converted = float(number)
    if converted == 0 and number != 0:
        raise LuminaError(f"{name} 数值过小，无法可靠输出；不会转换为零。")
    return converted


def exposure_value(value: object) -> Decimal:
    number = decimal_value(value, "Exposure")
    if not Decimal("-5") <= number <= Decimal("5"):
        raise LuminaError("曝光必须在 -5.00 到 +5.00 EV 之间。")
    if number != number.quantize(Decimal("0.01"), context=Context(prec=80)):
        raise LuminaError("曝光最多支持两位有效小数；不会自动舍入。")
    return number.copy_abs() if number == 0 else number
