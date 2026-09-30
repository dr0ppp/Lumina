"""Local parameter commands. JSON on stdout, errors on stderr."""

import argparse
import json
import sys

from . import __version__
from .adjustments import apply_adjustments, plan_adjustments
from .parser import parse_instructions
from .semantics import catalog, suggest
from .style_adjustments import apply_style, plan_style
from .xmp import read_parameters, set_exposure
from .xmp.errors import LuminaError


def main(argv: list[str] | None = None) -> int:
    # Windows pipe encodings otherwise vary by locale, corrupting Chinese JSON.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Lumina：本地 Camera Raw 参数指令与 XMP")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    read = commands.add_parser("read", help="读取同名 XMP 中的十项参数")
    read.add_argument("nef", help="NEF 文件路径")
    read.add_argument("--parameters-only", action="store_true", help="仅输出参数 JSON")
    write = commands.add_parser(
        "set-exposure", help="设置绝对曝光并备份 XMP；请先保存并关闭 ACR 中的照片",
    )
    write.add_argument("nef", help="NEF 文件路径")
    write.add_argument("value", help="绝对曝光值，-5.00 至 +5.00 EV")
    write.add_argument("--dry-run", action="store_true", help="只预览，不写文件或备份")
    parse = commands.add_parser("parse", help="将明确参数指令解析为 set/adjust 操作，不访问照片")
    parse.add_argument("text", help="用引号包围指令，例如：曝光+0.3，高光降低40")
    plan = commands.add_parser("plan", help="根据现有 XMP 预览参数前后值，不写文件")
    plan.add_argument("nef", help="NEF 文件路径")
    plan.add_argument("text", help="用引号包围参数指令")
    apply = commands.add_parser("apply", help="应用明确参数指令；请先保存并关闭 ACR 中的照片")
    apply.add_argument("nef", help="NEF 文件路径")
    apply.add_argument("text", help="用引号包围参数指令；相对调整重复应用会再次增减")
    apply.add_argument("--dry-run", action="store_true", help="检查应用条件并预览，不保存")
    apply.add_argument("--expect-sha256", help="plan 输出的 original_xmp_sha256，用于拒绝过期预览")
    commands.add_parser("styles", help="列出本地摄影词典及默认幅度")
    for name, help_text in (("suggest", "只生成摄影语言建议，不访问照片"),
                            ("plan-style", "根据照片预览摄影语言方案"),
                            ("apply-style", "应用已预览的摄影语言方案；先保存并关闭 ACR")):
        style = commands.add_parser(name, help=help_text)
        if name != "suggest":
            style.add_argument("nef", help="NEF 文件路径")
        style.add_argument("text", help="完整词组，例如：压高光，拉阴影")
        style.add_argument("--strength", choices=("gentle", "standard", "strong"), default="standard",
                           help="语义默认强度；句中“轻微/明显/一点”优先，明确数字不缩放")
        if name == "apply-style":
            style.add_argument("--expect-plan", help="plan-style 输出的 preview_sha256，实际应用必须提供")
            style.add_argument("--dry-run", action="store_true", help="只检查，不写入；无需预览摘要")
    args = parser.parse_args(argv)
    try:
        if args.command == "read":
            report = read_parameters(args.nef)
            if args.parameters_only:
                for warning in report["warnings"]:
                    print(f"提示：{warning}", file=sys.stderr)
                report = report["parameters"]
        elif args.command == "set-exposure":
            report = set_exposure(args.nef, args.value, dry_run=args.dry_run)
        elif args.command == "parse":
            report = {"operations": [operation.to_dict() for operation in parse_instructions(args.text)]}
        elif args.command == "plan":
            report = plan_adjustments(args.nef, args.text)
        elif args.command == "apply":
            report = apply_adjustments(
                args.nef, args.text, dry_run=args.dry_run, expected_sha256=args.expect_sha256,
            )
        elif args.command == "styles":
            report = catalog()
        elif args.command == "suggest":
            report = suggest(args.text, args.strength)
        elif args.command == "plan-style":
            report = plan_style(args.nef, args.text, strength=args.strength)
        else:
            report = apply_style(args.nef, args.text, strength=args.strength,
                                 expected_preview=args.expect_plan, dry_run=args.dry_run)
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    except (LuminaError, OSError) as exc:
        print(f"Lumina：{exc}", file=sys.stderr)
        return 1
    return 0
