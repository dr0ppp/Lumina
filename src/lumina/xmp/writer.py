"""Atomic batches of explicit final values with verified original backups."""

from collections.abc import Mapping
from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path
import re
import stat
import tempfile
from uuid import uuid4

from lxml import etree

from .errors import LuminaError
from ..parameters import RULES, json_number
from .mapping import PARAMETERS, WRITABLE_PARAMETERS, WRITABLE_PROCESS_VERSIONS, exposure_value
from .reader import XmpDocument, document_report, load_document, parse_xmp, property_slots


def _matches_bytes(path: Path, expected: bytes) -> bool:
    # Bound reads even when an external process replaces a small sidecar with
    # a very large file between checks.
    with path.open("rb") as stream:
        return stream.read(len(expected) + 1) == expected


def _assert_unchanged(document: XmpDocument) -> None:
    if document.xmp_path.is_symlink():
        raise LuminaError("XMP 已被替换为符号链接，取消保存。")
    if not _matches_bytes(document.xmp_path, document.original):
        raise LuminaError("XMP 在读取后被其他程序修改，取消保存；请重新读取。")


def _backup(document: XmpDocument) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = document.xmp_path.with_name(
        f"{document.xmp_path.name}.lumina-{stamp}-{uuid4().hex[:8]}.bak"
    )
    created = False
    try:
        with backup.open("xb") as stream:
            created = True
            stream.write(document.original)
            stream.flush()
            os.fsync(stream.fileno())
        if not _matches_bytes(backup, document.original):
            raise LuminaError("原始 XMP 备份校验失败，取消保存。")
    except (OSError, LuminaError) as exc:
        if created:
            try:
                backup.unlink(missing_ok=True)
            except OSError as cleanup_error:
                raise LuminaError(f"备份失败且无法清理未验证文件，请勿用其恢复：{backup}") from cleanup_error
        raise exc
    return backup


def validate_write(document: XmpDocument, parameters: list[str]) -> None:
    document_report(document)  # Refuse malformed values before any mutation.
    for name in parameters:
        if name not in PARAMETERS:
            raise LuminaError(f"不支持参数：{name}")
        if name not in WRITABLE_PARAMETERS:
            raise LuminaError(f"{name} 涉及白平衡模式，当前仅支持解析和预览；整批未应用。")
    if document.get("ProcessVersion") not in WRITABLE_PROCESS_VERSIONS:
        raise LuminaError("当前仅允许写入 ProcessVersion=15.4；不会自动转换或升级。")
    for name in parameters:
        if document.get(PARAMETERS[name].xmp_name) is None:
            raise LuminaError(f"缺少 {PARAMETERS[name].xmp_name}；请先在 ACR 中保存该参数设置。")
    if document.get("HasSettings") not in {"True", "true", "1"}:
        raise LuminaError("需要 HasSettings=True 的现有显影设置；请先在 ACR 保存调整。")
    for name in ("AutoTone", "AutoExposure"):
        value = document.get(name)
        if value is not None and value not in {"False", "false", "0"}:
            raise LuminaError(f"{name} 可能覆盖手动曝光；请先在 ACR 保存明确的手动设置。")
    for packet in document.tree.xpath('/processing-instruction("xpacket")'):
        if 'end="r"' in packet.text or "end='r'" in packet.text:
            raise LuminaError("XMP packet 标记为只读，取消修改。")


def validate_expected_sha256(document: XmpDocument, expected: str | None) -> str:
    digest = sha256(document.original).hexdigest()
    if expected is not None:
        if not isinstance(expected, str) or re.fullmatch(r"[0-9a-fA-F]{64}", expected) is None:
            raise LuminaError("预览摘要必须是完整的 64 位 SHA-256 十六进制字符串。")
        if digest != expected.lower():
            raise LuminaError("XMP 已与预览时不同，取消应用；请重新生成预览。")
    return digest


def write_document(
    document: XmpDocument, values: Mapping[str, object], *,
    dry_run: bool = False, expected_sha256: str | None = None,
) -> dict:
    """Write a complete batch against one loaded snapshot, never partially.

    The caller must save and close this photo in ACR first. Conflict checks
    cannot stop ACR from overwriting the file later from its in-memory state.
    """
    if not isinstance(values, Mapping) or not values:
        raise LuminaError("请提供至少一项明确的最终参数值。")
    digest = validate_expected_sha256(document, expected_sha256)
    validate_write(document, list(values))
    changes, updates = [], {}
    for name, value in values.items():
        requested = RULES[name].validate(value, name)
        previous = RULES[name].validate(document.get(PARAMETERS[name].xmp_name), name)
        changes.append({
            "parameter": name, "before": json_number(name, previous),
            "after": json_number(name, requested),
        })
        if previous != requested:
            updates[name] = requested
    result = {
        "status": "dry_run" if dry_run else "unchanged",
        "nef_path": str(document.nef_path),
        "xmp_path": str(document.xmp_path),
        "changes": changes,
        "backup_path": None,
        "original_xmp_sha256": digest,
        "written_xmp_sha256": None,
    }
    if dry_run or not updates:
        return result

    temporary: Path | None = None
    backup: Path | None = None
    replaced = False
    try:
        if not document.xmp_path.stat().st_mode & stat.S_IWRITE:
            raise LuminaError("XMP 为只读文件，取消保存。")
        _assert_unchanged(document)
        # A failed write must not mutate the caller's snapshot in memory.
        updated_tree = parse_xmp(document.original)
        updated_slots = property_slots(updated_tree)
        for name, requested in updates.items():
            text = f"{int(requested):+d}" if RULES[name].integer else f"{requested:+.2f}"
            updated_slots[PARAMETERS[name].xmp_name].set(text)
        serialized = etree.tostring(updated_tree, encoding="UTF-8", xml_declaration=True)
        validated = parse_xmp(serialized)
        if etree.tostring(validated, method="c14n") != etree.tostring(updated_tree, method="c14n"):
            raise LuminaError("序列化后元数据结构发生变化，取消保存。")
        validated_slots = property_slots(validated)
        for name, requested in updates.items():
            actual = RULES[name].validate(validated_slots[PARAMETERS[name].xmp_name].get(), name)
            if actual != requested:
                raise LuminaError(f"{name} 写入校验失败，取消保存。")

        with tempfile.NamedTemporaryFile(
            mode="wb", dir=document.xmp_path.parent,
            prefix=f".{document.xmp_path.name}.lumina-", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        if not _matches_bytes(temporary, serialized):
            raise LuminaError("临时 XMP 写入不完整，取消保存。")
        _assert_unchanged(document)
        backup = _backup(document)
        _assert_unchanged(document)
        # Close the temporary stream before replacing on Windows.
        os.replace(temporary, document.xmp_path)
        replaced = True
        if not _matches_bytes(document.xmp_path, serialized):
            raise LuminaError("替换后 XMP 校验失败或遭到外部修改。")
    except (OSError, LuminaError, etree.LxmlError) as exc:
        recovery = f" 原始备份：{backup}" if backup else ""
        state = "替换已完成，请检查当前 XMP。" if replaced else "Lumina 未替换原 XMP。"
        raise LuminaError(f"保存失败：{exc} {state}{recovery}") from exc
    finally:
        if temporary is not None:
            # Never mask the original error if Windows keeps a failed file open.
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    result.update(
        status="updated", backup_path=str(backup),
        written_xmp_sha256=sha256(serialized).hexdigest(),
    )
    return result


def set_parameters(
    nef_path: str | Path, values: Mapping[str, object], *,
    dry_run: bool = False, expected_sha256: str | None = None,
) -> dict:
    """Set explicit final values. Relative arithmetic belongs to the planner."""
    return write_document(
        load_document(nef_path), values, dry_run=dry_run, expected_sha256=expected_sha256,
    )


def set_exposure(nef_path: str | Path, value: object, *, dry_run: bool = False) -> dict:
    """Preserve the Phase 1 absolute-exposure API and result fields."""
    requested = exposure_value(value)
    result = set_parameters(nef_path, {"Exposure": requested}, dry_run=dry_run)
    change, = result.pop("changes")
    result.update(change)
    return result
