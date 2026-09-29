import json
import os
import subprocess
import sys

from lumina.cli import main


def test_read_json_and_plain_parameter_json(make_photo, capsys):
    nef, _ = make_photo()
    assert main(["read", str(nef)]) == 0
    assert json.loads(capsys.readouterr().out)["parameters"]["Exposure"] == .25
    assert main(["read", str(nef), "--parameters-only"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["Exposure"] == .25
    assert "WhiteBalance" in captured.err


def test_command_roundtrip_and_dry_run(make_photo, capsys):
    nef, _ = make_photo()
    assert main(["set-exposure", str(nef), "-0.50", "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "dry_run"
    assert main(["set-exposure", str(nef), "0.50"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "updated"


def test_error_goes_to_stderr_without_traceback(make_photo, capsys):
    nef, _ = make_photo()
    assert main(["set-exposure", str(nef), "6"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "-5.00" in captured.err
    assert "Traceback" not in captured.err


def test_python_module_entrypoint():
    result = subprocess.run([sys.executable, "-m", "lumina", "--version"], capture_output=True, text=True)
    assert result.returncode == 0
    assert result.stdout.strip() == "0.1.0.dev0"


def test_redirected_output_is_utf8_even_with_ascii_environment(make_photo):
    nef, _ = make_photo()
    result = subprocess.run(
        [sys.executable, "-m", "lumina", "read", str(nef)],
        env={**os.environ, "PYTHONIOENCODING": "ascii"}, capture_output=True,
    )
    assert result.returncode == 0
    report = json.loads(result.stdout.decode("utf-8"))
    assert "照片 test" in report["nef_path"]
    assert "色温" in report["warnings"][0]
