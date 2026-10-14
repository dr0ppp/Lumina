"""Strict bounded JSON, with no executable or filesystem instructions."""

from decimal import Decimal
import json

from ..errors import LuminaError
from ..parameters import RULES, json_number
from ..parser import Adjustment


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise LuminaError("JSON 含重复字段，拒绝选择其中一个。")
        result[key] = value
    return result


def _constant(value):
    raise LuminaError("JSON 不允许非有限数值。")


def load_json(data, limit=65536):
    if not isinstance(data, (str, bytes)) or len(data) > limit:
        raise LuminaError("JSON 内容类型无效或超过大小上限。")
    try:
        if isinstance(data, str) and len(data.encode("utf-8")) > limit:
            raise LuminaError("JSON 超过 UTF-8 字节大小上限。")
        return json.loads(data, object_pairs_hook=_pairs, parse_float=Decimal, parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise LuminaError("无法解析完整 JSON；不接受截断内容或 Markdown 代码块。") from None


def text_value(value, name, maximum, *, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise LuminaError(f"{name} 必须是有效且长度受限的文字。")
    # Reject lone surrogates before they reach network or UTF-8 persistence.
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise LuminaError(f"{name} 含无效 Unicode 字符。") from None
    return value


def validate_proposal(value):
    if not isinstance(value, dict) or set(value) != {"adjustments", "explanation", "warnings"}:
        raise LuminaError("AI 方案只能包含 adjustments、explanation、warnings。")
    items = value["adjustments"]
    if not isinstance(items, list) or not 1 <= len(items) <= len(RULES):
        raise LuminaError("AI 必须给出 1 至 10 项明确参数；空方案不会应用。")
    operations, seen = [], set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"parameter", "value"}:
            raise LuminaError("每项 AI 调整只能包含 parameter 和最终绝对 value。")
        name, number = item["parameter"], item["value"]
        if not isinstance(name, str) or name not in RULES or name in seen:
            raise LuminaError("AI 参数未知或重复，整批拒绝。")
        if isinstance(number, bool) or not isinstance(number, (int, float, Decimal)):
            raise LuminaError("AI 参数必须是 JSON 数字，不能是字符串或布尔值。")
        operations.append(Adjustment(name, "set", number))
        seen.add(name)
    explanation = text_value(value["explanation"], "explanation", 2000)
    warnings = value["warnings"]
    if not isinstance(warnings, list) or len(warnings) > 10:
        raise LuminaError("warnings 必须是至多十条文字的列表。")
    normalized = {
        "adjustments": [{"parameter": op.parameter, "value": json_number(op.parameter, op.value)} for op in operations],
        "explanation": explanation,
        "warnings": [text_value(w, "warning", 500) for w in warnings],
    }
    return tuple(operations), normalized


SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["adjustments", "explanation", "warnings"],
    "properties": {
        "adjustments": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["parameter", "value"],
            "properties": {"parameter": {"type": "string", "enum": list(RULES)}, "value": {"type": "number"}},
        }},
        "explanation": {"type": "string"},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
}
