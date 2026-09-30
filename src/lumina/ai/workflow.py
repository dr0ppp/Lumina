"""Persist a reviewable proposal and apply it offline against its exact source."""

from hashlib import sha256
import json
import os
from pathlib import Path
import re

from ..adjustments import _prepare_operations
from ..errors import LuminaError
from ..xmp.reader import document_report, load_document
from ..xmp.writer import write_document
from .client import ENDPOINTS
from .images import prepare_image
from .validation import load_json, text_value, validate_proposal

_FIELDS = {"format", "nef_path", "xmp_path", "original_xmp_sha256", "request", "provider", "model", "image_sha256", "proposal", "plan_sha256"}


def _digest(data):
    return sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def validate_plan(plan):
    if not isinstance(plan, dict) or set(plan) != _FIELDS or type(plan["format"]) is not int or plan["format"] != 1:
        raise LuminaError("不支持的 AI 方案文件结构或版本。")
    operations, proposal = validate_proposal(plan["proposal"])
    normalized = dict(plan, proposal=proposal)
    for field in ("nef_path", "xmp_path", "request", "model"):
        text_value(normalized[field], field, 4096 if field != "model" else 128)
    if not Path(plan["nef_path"]).is_absolute() or not Path(plan["xmp_path"]).is_absolute():
        raise LuminaError("AI 方案必须绑定照片与 XMP 的完整路径。")
    if not isinstance(plan["provider"], str) or plan["provider"] not in ENDPOINTS:
        raise LuminaError("方案的模型来源无效。")
    if not _hash(plan["original_xmp_sha256"]) or not _hash(plan["plan_sha256"]):
        raise LuminaError("方案摘要格式无效。")
    if plan["image_sha256"] is not None and not _hash(plan["image_sha256"]):
        raise LuminaError("预览图摘要无效。")
    payload = {key: value for key, value in normalized.items() if key != "plan_sha256"}
    if _digest(payload) != plan["plan_sha256"]:
        raise LuminaError("AI 方案内容被修改或损坏，请重新生成并审核。")
    return operations, normalized


def _review(plan):
    operations, plan = validate_plan(plan)
    document, updates, report = _prepare_operations(plan["nef_path"], operations, plan["original_xmp_sha256"])
    if str(document.xmp_path) != plan["xmp_path"]:
        raise LuminaError("当前 XMP 路径与 AI 方案绑定目标不同。")
    report.update(plan_sha256=plan["plan_sha256"], provider=plan["provider"], model=plan["model"],
                  request=plan["request"], explanation=plan["proposal"]["explanation"], image_sha256=plan["image_sha256"])
    report["warnings"].extend(plan["proposal"]["warnings"])
    report["warnings"].append("AI 仅提供建议，未保证视觉效果；请审核前后值并在 ACR 检查。")
    return document, updates, report


def generate_plan(nef_path, request_text, client, *, preview_path=None, send_preview=False):
    text_value(request_text, "需求", 4096)
    if (preview_path is not None) != bool(send_preview):
        raise LuminaError("发送图片需要同时指定 --preview 和 --send-preview。")
    if preview_path is not None and client.config.provider != "openai":
        raise LuminaError("当前该服务商仅支持文字方案，不会读取或上传预览图。")
    document = load_document(nef_path)
    snapshot = document_report(document)
    for field in ("ProcessVersion", "WhiteBalance"):
        if document.get(field) is not None:
            text_value(document.get(field), field, 100)
    image = prepare_image(preview_path) if preview_path is not None else None
    # No paths, sidecar bytes, identifying metadata or unrelated XMP fields leave the device.
    context = {"parameters": snapshot["parameters"], "missing_fields": snapshot["missing_fields"],
               "process_version": document.get("ProcessVersion"), "white_balance": document.get("WhiteBalance")}
    response = client.propose(context, request_text, image)
    _, proposal = validate_proposal(load_json(response, 32768))
    plan = {"format": 1, "nef_path": str(document.nef_path), "xmp_path": str(document.xmp_path),
            "original_xmp_sha256": sha256(document.original).hexdigest(), "request": request_text,
            "provider": client.config.provider, "model": client.config.model,
            "image_sha256": image.sha256 if image is not None else None, "proposal": proposal}
    plan["plan_sha256"] = _digest(plan)
    # Re-read and compare with the pre-request snapshot, never apply values to a changed baseline.
    _, _, report = _review(plan)
    return plan, report


def check_plan_destination(path):
    target = Path(path)
    if not target.name.casefold().endswith(".lumina-plan.json"):
        raise LuminaError("方案文件必须以 .lumina-plan.json 结尾，避免覆盖照片或 XMP。")
    if target.exists() or target.is_symlink() or not target.parent.is_dir():
        raise LuminaError("方案输出位置已存在或父目录不存在；请选择新的方案文件。")
    return target


def save_plan(path, plan):
    _, normalized = validate_plan(plan)
    target = check_plan_destination(path)
    serialized = json.dumps(normalized, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if len(serialized.encode("utf-8")) > 65536:
        raise LuminaError("方案超过 64 KiB 保存上限，请缩短需求或模型解释。")
    # Exclusive creation: no clobbering an earlier reviewed plan or a symlink.
    created = False
    try:
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            created = True
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        if created:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                raise LuminaError("保存失败且残缺方案无法清理，请勿使用该文件。") from None
        raise


def read_plan(path):
    with Path(path).open("rb") as stream:
        data = stream.read(65537)
    return validate_plan(load_json(data))[1]


def show_plan(path):
    return _review(read_plan(path))[2]


def apply_plan(path, *, expected_plan=None, dry_run=False):
    plan = read_plan(path)
    if expected_plan is not None:
        if not isinstance(expected_plan, str) or expected_plan.lower() != plan["plan_sha256"]:
            raise LuminaError("提供的摘要不匹配当前方案，请重新运行 ai-show 审核。")
    elif not dry_run:
        raise LuminaError("实际应用需要 --expect-plan 指定已审核的 plan_sha256。")
    document, updates, review = _review(plan)
    if not review["can_apply"]:
        raise LuminaError("无法应用：" + "；".join(review["blocked_reasons"]))
    result = write_document(document, updates, dry_run=dry_run, expected_sha256=plan["original_xmp_sha256"])
    result.update(plan_sha256=plan["plan_sha256"], explanation=review["explanation"], warnings=review["warnings"])
    return result
