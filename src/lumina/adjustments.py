"""Resolve explicit instructions against one immutable-on-write XMP snapshot."""

from decimal import Context, Decimal
from pathlib import Path

from .errors import LuminaError
from .parameters import RULES, json_number
from .parser import parse_instructions
from .xmp.mapping import PARAMETERS
from .xmp.reader import document_report, load_document
from .xmp.writer import validate_expected_sha256, validate_write, write_document


def _prepare(nef_path: str | Path, text: str, expected_sha256: str | None = None):
    operations = parse_instructions(text)
    return _prepare_operations(nef_path, operations, expected_sha256)


def _prepare_operations(nef_path, operations, expected_sha256=None):
    """Internal bridge for already validated, unique immutable operations."""
    document = load_document(nef_path)
    digest = validate_expected_sha256(document, expected_sha256)
    snapshot = document_report(document)
    updates: dict[str, Decimal] = {}
    changes = []
    for operation in operations:
        name = operation.parameter
        raw = document.get(PARAMETERS[name].xmp_name)
        if raw is None:
            raise LuminaError(f"{name} 当前值未记录，无法可靠预览；请先在 ACR 保存该参数。")
        before = RULES[name].validate(raw, name)
        after = (
            operation.value if operation.operation == "set"
            else Context(prec=80).add(before, operation.value)
        )
        after = RULES[name].validate(after, name)
        updates[name] = after
        changes.append({
            "parameter": name, "before": json_number(name, before),
            "after": json_number(name, after),
        })
    blockers = []
    try:
        validate_write(document, list(updates))
    except LuminaError as exc:
        blockers.append(str(exc))
    warnings = list(snapshot["warnings"])
    if any(operation.operation == "adjust" for operation in operations):
        warnings.append("包含相对调整，重复应用会再次增减；请先检查预览。")
    report = {
        "status": "planned", "nef_path": str(document.nef_path),
        "xmp_path": str(document.xmp_path), "original_xmp_sha256": digest,
        "operations": [operation.to_dict() for operation in operations],
        "changes": changes, "can_apply": not blockers, "blocked_reasons": blockers,
        "warnings": warnings,
    }
    return document, updates, report


def plan_adjustments(nef_path: str | Path, text: str) -> dict:
    """Preview supported numeric values without modifying files."""
    return _prepare(nef_path, text)[2]


def apply_adjustments(
    nef_path: str | Path, text: str, *, dry_run: bool = False,
    expected_sha256: str | None = None,
) -> dict:
    """Calculate and save from the same snapshot; one invalid item cancels all."""
    document, updates, plan = _prepare(nef_path, text, expected_sha256)
    if not plan["can_apply"]:
        raise LuminaError("无法应用：" + "；".join(plan["blocked_reasons"]))
    result = write_document(
        document, updates, dry_run=dry_run, expected_sha256=expected_sha256,
    )
    result.update(operations=plan["operations"], warnings=plan["warnings"])
    return result
