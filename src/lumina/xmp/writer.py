"""Exposure-only updates with verified backups and staged replacement."""

from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path
import stat
import tempfile
from uuid import uuid4

from lxml import etree

from .errors import LuminaError
from .mapping import WRITABLE_PROCESS_VERSIONS, exposure_value
from .reader import XmpDocument, document_report, load_document, parse_xmp, property_slots


def _assert_unchanged(document: XmpDocument) -> None:
    if document.xmp_path.is_symlink():
        raise LuminaError("XMP 已被替换为符号链接，取消保存。")
    if document.xmp_path.read_bytes() != document.original:
        raise LuminaError("XMP 在读取后被其他程序修改，取消保存；请重新读取。")


def _backup(document: XmpDocument) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = document.xmp_path.with_name(
        f"{document.xmp_path.name}.lumina-{stamp}-{uuid4().hex[:8]}.bak"
    )
    with backup.open("xb") as stream:
        stream.write(document.original)
        stream.flush()
        os.fsync(stream.fileno())
    if backup.read_bytes() != document.original:
        raise LuminaError(f"原始 XMP 备份校验失败，取消保存：{backup}")
    return backup


def _validate_write(document: XmpDocument) -> None:
    document_report(document)  # Refuse malformed values before any mutation.
    if document.get("ProcessVersion") not in WRITABLE_PROCESS_VERSIONS:
        raise LuminaError("Phase 1 仅允许写入 ProcessVersion=15.4；不会自动转换或升级。")
    if document.get("Exposure2012") is None:
        raise LuminaError("缺少 Exposure2012；请先在 ACR 中保存曝光设置。")
    if document.get("HasSettings") not in {"True", "true", "1"}:
        raise LuminaError("需要 HasSettings=True 的现有显影设置；请先在 ACR 保存调整。")
    for name in ("AutoTone", "AutoExposure"):
        value = document.get(name)
        if value is not None and value not in {"False", "false", "0"}:
            raise LuminaError(f"{name} 可能覆盖手动曝光；请先在 ACR 保存明确的手动设置。")
    for packet in document.tree.xpath('/processing-instruction("xpacket")'):
        if 'end="r"' in packet.text or "end='r'" in packet.text:
            raise LuminaError("XMP packet 标记为只读，取消修改。")


def set_exposure(nef_path: str | Path, value: object, *, dry_run: bool = False) -> dict:
    """Set an absolute exposure. Only the existing global field is changed.

    The caller must save and close this photo in ACR first. Conflict checks
    cannot stop ACR from overwriting the file later from its in-memory state.
    """
    requested = exposure_value(value)
    document = load_document(nef_path)
    _validate_write(document)
    previous = exposure_value(document.get("Exposure2012"))
    result = {
        "status": "dry_run" if dry_run else "unchanged",
        "nef_path": str(document.nef_path),
        "xmp_path": str(document.xmp_path),
        "parameter": "Exposure",
        "before": float(previous),
        "after": float(requested),
        "backup_path": None,
        "original_xmp_sha256": sha256(document.original).hexdigest(),
        "written_xmp_sha256": None,
    }
    if dry_run or previous == requested:
        return result

    temporary: Path | None = None
    backup: Path | None = None
    replaced = False
    try:
        if not document.xmp_path.stat().st_mode & stat.S_IWRITE:
            raise LuminaError("XMP 为只读文件，取消保存。")
        _assert_unchanged(document)
        document.slots["Exposure2012"].set(f"{requested:+.2f}")
        serialized = etree.tostring(document.tree, encoding="UTF-8", xml_declaration=True)
        validated = parse_xmp(serialized)
        if etree.tostring(validated, method="c14n") != etree.tostring(document.tree, method="c14n"):
            raise LuminaError("序列化后元数据结构发生变化，取消保存。")
        if exposure_value(property_slots(validated)["Exposure2012"].get()) != requested:
            raise LuminaError("曝光写入校验失败，取消保存。")

        with tempfile.NamedTemporaryFile(
            mode="wb", dir=document.xmp_path.parent,
            prefix=f".{document.xmp_path.name}.lumina-", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        if temporary.read_bytes() != serialized:
            raise LuminaError("临时 XMP 写入不完整，取消保存。")
        _assert_unchanged(document)
        backup = _backup(document)
        _assert_unchanged(document)
        # Close the temporary stream before replacing on Windows.
        os.replace(temporary, document.xmp_path)
        replaced = True
        if document.xmp_path.read_bytes() != serialized:
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
