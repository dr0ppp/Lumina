"""Local parameter commands. JSON on stdout, errors on stderr."""

import argparse
import json
import sys

from . import __version__
from .adjustments import apply_adjustments, plan_adjustments
from .parser import parse_instructions
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
        else:
            report = apply_adjustments(
                args.nef, args.text, dry_run=args.dry_run, expected_sha256=args.expect_sha256,
            )
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    except (LuminaError, OSError) as exc:
        print(f"Lumina：{exc}", file=sys.stderr)
        return 1
    return 0
