"""Check built archives against an explicit source-only file inventory."""

from pathlib import Path
import tarfile
import tomllib
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def check_inventory(actual: set[str], required: set[str], allowed: set[str], label: str) -> None:
    missing = required - actual
    unexpected = actual - allowed
    if missing or unexpected:
        raise SystemExit(
            f"{label}: missing={sorted(missing)}, unexpected={sorted(unexpected)}"
        )
    print(f"{label}: {len(actual)} files, inventory verified")


def main() -> None:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    name = f"lumina_raw-{version}"
    source = {p.relative_to(ROOT / "src").as_posix() for p in (ROOT / "src/lumina").rglob("*.py")}
    info = f"{name}.dist-info"
    wheel_files = source | {
        f"{info}/{filename}" for filename in (
            "METADATA", "WHEEL", "entry_points.txt", "top_level.txt", "RECORD",
        )
    }
    with zipfile.ZipFile(ROOT / "dist" / f"{name}-py3-none-any.whl") as wheel:
        entries = wheel.namelist()
        if len(entries) != len(set(entries)) or wheel.testzip() is not None:
            raise SystemExit("Wheel contains duplicate entries or corrupt data")
        check_inventory(set(entries), wheel_files, wheel_files, "wheel")

    required = {
        "README.md", "AGENTS.md", "CHANGELOG.md", "pyproject.toml", "MANIFEST.in",
        "requirements.txt", "requirements-dev.txt",
        *(f"src/{path}" for path in source),
        *(p.relative_to(ROOT).as_posix() for directory, pattern in (
            ("tests", "*.py"), ("docs", "*.md"), ("tools", "*.py"),
        ) for p in (ROOT / directory).glob(pattern)),
    }
    generated = {"PKG-INFO", "setup.cfg"} | {
        f"src/lumina_raw.egg-info/{filename}" for filename in (
            "PKG-INFO", "SOURCES.txt", "dependency_links.txt", "entry_points.txt",
            "requires.txt", "top_level.txt",
        )
    }
    with tarfile.open(ROOT / "dist" / f"{name}.tar.gz", "r:gz") as sdist:
        entries = []
        for member in sdist:
            if member.isdir():
                continue
            if not member.isfile() or not member.name.startswith(name + "/"):
                raise SystemExit(f"Unexpected source archive entry: {member.name}")
            entries.append(member.name.removeprefix(name + "/"))
        if len(entries) != len(set(entries)):
            raise SystemExit("Source archive contains duplicate entries")
        check_inventory(set(entries), required, required | generated, "sdist")


if __name__ == "__main__":
    main()
