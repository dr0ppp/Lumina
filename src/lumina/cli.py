"""Small Phase 1 command line. JSON on stdout, errors on stderr."""

import argparse
import json
import sys

from . import __version__
from .xmp import read_parameters, set_exposure
from .xmp.errors import LuminaError


def main(argv: list[str] | None = None) -> int:
    # Windows pipe encodings otherwise vary by locale, corrupting Chinese JSON.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Lumina Phase 1：Camera Raw XMP 读写验证")
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
    args = parser.parse_args(argv)
    try:
        if args.command == "read":
            report = read_parameters(args.nef)
            if args.parameters_only:
                for warning in report["warnings"]:
                    print(f"提示：{warning}", file=sys.stderr)
                report = report["parameters"]
        else:
            report = set_exposure(args.nef, args.value, dry_run=args.dry_run)
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    except (LuminaError, OSError) as exc:
        print(f"Lumina：{exc}", file=sys.stderr)
        return 1
    return 0
