"""Local, whole-phrase suggestions with explicit provenance."""

from decimal import Context, Decimal

from ..errors import LuminaError
from ..parser import Adjustment, parse_instructions
from ..parser.text import split_instructions
from .dictionary import RULES, VERSION, catalog

__all__ = ["catalog", "suggest"]

_FACTORS = {"gentle": Decimal("0.5"), "standard": Decimal("1"), "strong": Decimal("1.5")}
_ALIASES = {alias: rule for rule in RULES for alias in rule.aliases}
_PREFIXES = {"轻微": "gentle", "稍微": "gentle", "稍稍": "gentle", "明显": "strong"}
_UNSUPPORTED = {
    "电影感": "电影感没有唯一参数方案，请改为明确的明暗或色彩需求。",
    "通透": "通透感涉及尚未支持的清晰度、去雾等参数，不会只执行其中一部分。",
    "肤色": "肤色需要颜色或局部判断，当前未分析照片，也未支持相应参数。",
    "绿色": "单独调整绿色需要 HSL 等颜色参数，当前未支持。",
}


def _resolve(text: str, strength: str = "standard"):
    if not isinstance(strength, str) or strength not in _FACTORS:
        raise LuminaError("强度必须为 gentle、standard 或 strong。")
    operations, matches, seen = [], [], set()
    for index, clause in enumerate(split_instructions(text), 1):
        try:
            try:
                operation, = parse_instructions(clause)
            except LuminaError:
                phrase, selected = clause, strength
                explicit_strength = False
                for prefix, level in _PREFIXES.items():
                    if phrase.startswith(prefix):
                        phrase, selected = phrase[len(prefix):].strip(), level
                        explicit_strength = True
                        break
                if phrase.endswith("一点"):
                    if explicit_strength and selected != "gentle":
                        raise LuminaError("“明显”与“一点”的强度冲突，请只选择一种。")
                    phrase, selected = phrase[:-2].strip(), "gentle"
                rule = _ALIASES.get(phrase)
                if rule is None:
                    for keyword, reason in _UNSUPPORTED.items():
                        if keyword in clause:
                            raise LuminaError(reason)
                    raise LuminaError("未完整匹配摄影词组；不猜测否定、遗漏数值或未知表达。请用 styles 查看支持词组，或使用明确参数指令。")
                delta = Context(prec=80).multiply(Decimal(rule.delta), _FACTORS[selected])
                operation = Adjustment(rule.parameter, "adjust", delta)
                match = {"source": clause, "kind": "dictionary", "rule_id": rule.id,
                         "strength": selected, "explanation": rule.explanation}
            else:
                match = {"source": clause, "kind": "explicit", "rule_id": None,
                         "strength": None, "explanation": "保留用户明确数值，不按语义强度缩放。"}
            if operation.parameter in seen:
                raise LuminaError(f"{operation.parameter} 重复或方向冲突，请合并为一条指令。")
        except LuminaError as exc:
            raise LuminaError(f"第 {index} 项 {clause!r}：{exc}") from exc
        seen.add(operation.parameter)
        operations.append(operation)
        matches.append(match)
    report = {
        "dictionary_version": VERSION, "matches": matches,
        "operations": [op.to_dict() for op in operations],
        "warnings": ["语义幅度是项目默认建议，未分析照片；不保证特定视觉效果。"],
    }
    return tuple(operations), report


def suggest(text: str, strength: str = "standard") -> dict:
    """No file access. One invalid phrase rejects the entire proposal."""
    return _resolve(text, strength)[1]
