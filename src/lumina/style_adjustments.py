"""Bind a semantic preview to both its source image and exact proposal."""

from hashlib import sha256
import json
import re

from .adjustments import _prepare_operations
from .errors import LuminaError
from .semantics import _resolve
from .xmp.writer import write_document


def _prepare_style(nef_path, text, strength):
    operations, suggestion = _resolve(text, strength)
    document, updates, report = _prepare_operations(nef_path, operations)
    report.update(dictionary_version=suggestion["dictionary_version"], matches=suggestion["matches"])
    report["warnings"].extend(suggestion["warnings"])
    payload = {name: report[name] for name in (
        "nef_path", "xmp_path", "original_xmp_sha256", "dictionary_version", "matches", "operations",
    )}
    report["preview_sha256"] = sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return document, updates, report


def plan_style(nef_path, text, *, strength="standard") -> dict:
    return _prepare_style(nef_path, text, strength)[2]


def apply_style(nef_path, text, *, strength="standard", expected_preview=None, dry_run=False) -> dict:
    document, updates, plan = _prepare_style(nef_path, text, strength)
    if expected_preview is not None:
        if not isinstance(expected_preview, str) or re.fullmatch(r"[0-9a-fA-F]{64}", expected_preview) is None:
            raise LuminaError("预览摘要必须是完整的 64 位 SHA-256。")
        if expected_preview.lower() != plan["preview_sha256"]:
            raise LuminaError("照片、XMP 或方案已与预览不同；请重新运行 plan-style。")
    elif not dry_run:
        raise LuminaError("请先运行 plan-style，再用 --expect-plan 提供 preview_sha256；未写入。")
    if not plan["can_apply"]:
        raise LuminaError("无法应用：" + "；".join(plan["blocked_reasons"]))
    report = write_document(document, updates, dry_run=dry_run)
    report.update({key: plan[key] for key in (
        "operations", "matches", "warnings", "dictionary_version", "preview_sha256",
    )})
    return report
