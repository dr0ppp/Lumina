"""Shared bounded normalization for explicit and semantic instructions."""

import re
import unicodedata

from ..errors import LuminaError

MAX_INPUT_LENGTH = 4096


def split_instructions(text: str) -> list[str]:
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
    if len(clauses) > 10:
        raise LuminaError("一批最多指定十个不同参数。")
    return clauses
