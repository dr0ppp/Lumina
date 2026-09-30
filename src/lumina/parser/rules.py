"""Whole-clause grammar, not fuzzy photography-language interpretation."""

from dataclasses import dataclass
from decimal import Decimal
import re
from typing import Literal
import unicodedata

from ..errors import LuminaError
from ..parameters import RULES, json_number

MAX_INPUT_LENGTH = 4096
ALIASES = {
    "曝光": "Exposure", "对比度": "Contrast", "高光": "Highlights",
    "阴影": "Shadows", "白色": "Whites", "白色色阶": "Whites",
    "黑色": "Blacks", "黑色色阶": "Blacks", "色温": "Temperature",
    "色调": "Tint", "自然饱和度": "Vibrance", "饱和度": "Saturation",
    **{name.casefold(): name for name in RULES},
}
_FLAGS = re.IGNORECASE | re.ASCII
_NAME = re.compile(
    "^(" + "|".join(re.escape(name) for name in sorted(ALIASES, key=len, reverse=True)) + ")(.*)$",
    _FLAGS,
)
_NUMBER = r"(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)"
_TAIL = r"\s*(?P<unit>[A-Za-z%°]*)\s*$"
_SET = re.compile(
    r"^(?:设置为|设置成|设为|设成|调整为|调整到|=|:|set(?:\s+to)?\s+)\s*"
    + r"(?P<number>[+-]?" + _NUMBER + ")" + _TAIL, _FLAGS,
)
_INCREASE = re.compile(
    r"^(?:增加|提高|上调|加|increase(?:\s+by)?|add)\s*"
    + "(?P<number>" + _NUMBER + ")" + _TAIL, _FLAGS,
)
_DECREASE = re.compile(
    r"^(?:降低|减少|下调|减|decrease(?:\s+by)?|subtract)\s*"
    + "(?P<number>" + _NUMBER + ")" + _TAIL, _FLAGS,
)
_SIGNED = re.compile(
    r"^(?P<sign>[+-])=?\s*(?P<number>" + _NUMBER + ")" + _TAIL, _FLAGS,
)


@dataclass(frozen=True)
class Adjustment:
    parameter: str
    operation: Literal["set", "adjust"]
    value: Decimal

    def __post_init__(self) -> None:
        if self.parameter not in RULES:
            raise LuminaError(f"不支持参数：{self.parameter}")
        if self.operation not in {"set", "adjust"}:
            raise LuminaError("操作必须为 set（设为）或 adjust（增减）。")
        number = RULES[self.parameter].validate(
            self.value, self.parameter, relative=self.operation == "adjust",
        )
        object.__setattr__(self, "value", number)

    def to_dict(self) -> dict:
        return {
            "parameter": self.parameter, "operation": self.operation,
            "value": json_number(self.parameter, self.value),
        }


def _parse_clause(clause: str) -> Adjustment:
    match = _NAME.fullmatch(clause)
    if match is None:
        raise LuminaError("未识别参数名；当前只接受十项明确参数，不解释摄影风格。")
    parameter = ALIASES[match.group(1).casefold()]
    body = match.group(2).strip()
    operation: Literal["set", "adjust"] = "set"
    sign = 1
    value_match = _SET.fullmatch(body)
    if value_match is None:
        operation = "adjust"
        value_match = _INCREASE.fullmatch(body)
        if value_match is None:
            value_match = _DECREASE.fullmatch(body)
            if value_match is not None:
                sign = -1
        if value_match is None:
            value_match = _SIGNED.fullmatch(body)
            if value_match is not None and value_match.group("sign") == "-":
                sign = -1
    if value_match is None:
        raise LuminaError("请完整指定操作和数值，如“曝光设为0.3”或“曝光增加0.3”；不要混用方向与负号。")
    unit = value_match.group("unit").upper()
    if unit and unit != RULES[parameter].unit:
        expected = RULES[parameter].unit or "无单位的滑块数值"
        raise LuminaError(f"{parameter} 不接受单位 {unit!r}；请使用 {expected}。")
    # Validate before multiplication to bound precision/size of Decimal work.
    number = RULES[parameter].validate(
        value_match.group("number"), parameter, relative=operation == "adjust",
    )
    return Adjustment(parameter, operation, number.copy_negate() if sign == -1 else number)


def parse_instructions(text: str) -> tuple[Adjustment, ...]:
    """Parse every clause or fail, keeping relative and absolute intent distinct."""
    if not isinstance(text, str) or not text.strip():
        raise LuminaError("参数指令不能为空。")
    if len(text) > MAX_INPUT_LENGTH:
        raise LuminaError(f"参数指令不能超过 {MAX_INPUT_LENGTH} 个字符。")
    normalized = unicodedata.normalize("NFKC", text).replace("−", "-").strip()
    if len(normalized) > MAX_INPUT_LENGTH:
        raise LuminaError("规范化后的参数指令过长。")
    normalized = normalized.removesuffix("。").strip()
    clauses = [part.strip() for part in re.split(r"[,;\r\n]+", normalized) if part.strip()]
    if not clauses:
        raise LuminaError("参数指令不能为空。")
    if len(clauses) > len(RULES):
        raise LuminaError("一批最多指定十个不同参数。")
    operations = []
    seen = set()
    for index, clause in enumerate(clauses, 1):
        try:
            operation = _parse_clause(clause)
            if operation.parameter in seen:
                raise LuminaError(f"{operation.parameter} 重复指定；请合并为一条明确指令。")
        except LuminaError as exc:
            raise LuminaError(f"第 {index} 项 {clause!r}：{exc}") from exc
        seen.add(operation.parameter)
        operations.append(operation)
    return tuple(operations)
