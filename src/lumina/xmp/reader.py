"""Read existing NEF sidecars without resolving defaults or nested edits."""

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from lxml import etree

from .errors import LuminaError
from .mapping import (
    CRS, RDF, XMP_META, PARAMETERS, METADATA, WATCHED_FIELDS,
    WRITABLE_PROCESS_VERSIONS, parameter_value,
)

MAX_XMP_BYTES = 16 * 1024 * 1024


@dataclass
class PropertySlot:
    element: etree._Element
    attribute: str | None

    def get(self) -> str:
        value = self.element.get(self.attribute) if self.attribute else self.element.text
        return (value or "").strip()

    def set(self, value: str) -> None:
        if self.attribute:
            self.element.set(self.attribute, value)
        else:
            self.element.text = value


@dataclass
class XmpDocument:
    nef_path: Path
    xmp_path: Path
    original: bytes
    tree: etree._ElementTree
    slots: dict[str, PropertySlot]

    def get(self, name: str) -> str | None:
        return self.slots[name].get() if name in self.slots else None


def find_sidecar(nef_path: str | Path) -> tuple[Path, Path]:
    nef = Path(nef_path).expanduser().absolute()
    if nef.suffix.casefold() != ".nef":
        raise LuminaError("当前仅接受 .NEF 文件路径。")
    if not nef.is_file():
        raise LuminaError(f"NEF 文件不存在或不是普通文件：{nef}")
    try:
        candidates = [
            p for p in nef.parent.iterdir()
            if p.stem.casefold() == nef.stem.casefold() and p.suffix.casefold() == ".xmp"
        ]
    except OSError as exc:
        raise LuminaError(f"无法访问照片目录：{exc}") from exc
    if not candidates:
        raise LuminaError("未找到同名 XMP；请先在 Camera Raw 中保存为 sidecar XMP 并关闭照片。")
    if len(candidates) != 1:
        raise LuminaError("找到多个大小写不同的同名 XMP，无法确定目标。")
    xmp = candidates[0]
    if xmp.is_symlink() or not xmp.is_file():
        raise LuminaError("XMP 必须是普通文件，不能是符号链接或目录。")
    return nef, xmp


def parse_xmp(data: bytes) -> etree._ElementTree:
    if len(data) > MAX_XMP_BYTES:
        raise LuminaError("XMP 超过当前 16 MiB 文件大小上限。")
    parser = etree.XMLParser(
        resolve_entities=False, load_dtd=False, no_network=True,
        recover=False, remove_blank_text=False, remove_comments=False,
        remove_pis=False, strip_cdata=False, huge_tree=False,
    )
    try:
        tree = etree.parse(BytesIO(data), parser)
    except (etree.XMLSyntaxError, ValueError) as exc:
        raise LuminaError(f"XMP 不是有效的 XML：{exc}") from exc
    if tree.docinfo.doctype:
        raise LuminaError("不支持含 DTD 或自定义实体声明的 XMP。")
    return tree


def property_slots(tree: etree._ElementTree) -> dict[str, PropertySlot]:
    root = tree.getroot()
    if root.tag == f"{{{RDF}}}RDF":
        rdf = root
    elif root.tag == f"{{{XMP_META}}}xmpmeta":
        roots = root.findall(f"{{{RDF}}}RDF")
        if len(roots) != 1:
            raise LuminaError("XMP 必须包含唯一的顶层 rdf:RDF。")
        rdf = roots[0]
    else:
        raise LuminaError("无法识别 XMP 文档根节点。")

    slots: dict[str, PropertySlot] = {}

    def add(name: str, slot: PropertySlot) -> None:
        if name in slots:
            raise LuminaError(f"当前照片的 {name} 重复或冲突；不会任选一个值。")
        slots[name] = slot

    for desc in rdf.findall(f"{{{RDF}}}Description"):
        # Only the current document's subject. Nested snapshots/masks and
        # descriptions of other RDF subjects must never become write targets.
        if desc.get(f"{{{RDF}}}about") != "":
            continue
        for name in WATCHED_FIELDS:
            key = f"{{{CRS}}}{name}"
            if key in desc.attrib:
                add(name, PropertySlot(desc, key))
            for child in desc.findall(key):
                if len(child) or child.attrib:
                    raise LuminaError(f"{name} 使用了不支持的复杂 XMP 结构。")
                add(name, PropertySlot(child, None))
    if not slots:
        raise LuminaError("未找到当前照片主体的 Camera Raw 参数。请使用 ACR 生成的照片 sidecar。")
    return slots


def load_document(nef_path: str | Path) -> XmpDocument:
    nef, xmp = find_sidecar(nef_path)
    try:
        with xmp.open("rb") as stream:
            original = stream.read(MAX_XMP_BYTES + 1)
    except OSError as exc:
        raise LuminaError(f"无法读取 XMP：{exc}") from exc
    tree = parse_xmp(original)
    document = XmpDocument(nef, xmp, original, tree, property_slots(tree))
    raw_name = document.get("RawFileName")
    if raw_name is not None and raw_name.casefold() != nef.name.casefold():
        raise LuminaError("XMP 的 RawFileName 与输入 NEF 不一致，已停止处理。")
    return document


def document_report(document: XmpDocument) -> dict:
    values = {}
    missing = []
    for name, parameter in PARAMETERS.items():
        value = document.get(parameter.xmp_name)
        if value is None:
            missing.append(name)
        else:
            values[name] = parameter_value(value, name)
    metadata = {name: document.get(name) for name in METADATA}
    warnings = []
    if missing:
        warnings.append("部分字段未记录；没有用零值或 ACR 默认值补齐。")
    if document.get("ProcessVersion") not in WRITABLE_PROCESS_VERSIONS:
        warnings.append("此处理版本仅检查已记录的现代字段，不支持写入；不转换旧版参数。")
    if document.get("WhiteBalance") in {"As Shot", "Auto"}:
        warnings.append("色温/色调是 XMP 记录值；实际白平衡还受 WhiteBalance 模式影响。")
    return {
        "nef_path": str(document.nef_path),
        "xmp_path": str(document.xmp_path),
        "parameters": values,
        "missing_fields": missing,
        "metadata": metadata,
        "warnings": warnings,
    }


def read_parameters(nef_path: str | Path) -> dict:
    """Return JSON-compatible values plus missing-field and version context."""
    return document_report(load_document(nef_path))
