from decimal import Inexact, localcontext
import json
from pathlib import Path

import pytest

from lumina.cli import main
from lumina.errors import LuminaError
from lumina.semantics import catalog, suggest
from lumina.style_adjustments import apply_style, plan_style
from lumina.xmp import read_parameters
from lumina.xmp import writer


def test_default_proposal_has_provenance_and_no_visual_guarantee():
    result = suggest("压高光，拉阴影，整体提亮")
    assert result["operations"] == [
        {"parameter": "Highlights", "operation": "adjust", "value": -20},
        {"parameter": "Shadows", "operation": "adjust", "value": 20},
        {"parameter": "Exposure", "operation": "adjust", "value": .2},
    ]
    assert result["matches"][0]["source"] == "压高光"
    assert result["matches"][0]["rule_id"] == "lower_highlights"
    assert "未分析照片" in result["warnings"][0]


@pytest.mark.parametrize("text,strength,value", [
    ("压高光", "gentle", -10), ("压高光", "strong", -30),
    ("轻微压高光", "strong", -10), ("明显压一下高光", "gentle", -30),
    ("压高光一点", "strong", -10), ("稍微压高光一点", "standard", -10),
])
def test_strength_and_phrase_override(text, strength, value):
    assert suggest(text, strength)["operations"][0]["value"] == value


def test_explicit_values_are_not_scaled_and_whole_input_is_normalized():
    result = suggest("曝光设为＋０．５０；轻微压高光。", "strong")
    assert result["operations"][0]["value"] == .5
    assert result["operations"][0]["operation"] == "set"
    assert result["matches"][0]["kind"] == "explicit"
    assert result["operations"][1]["value"] == -10


@pytest.mark.parametrize("text", [
    "不要压高光", "不压高光", "压高光但不要变暗", "压高光然后拉阴影", "压高光，随便调",
    "电影感", "增加通透感", "肤色自然一点", "让绿色不要这么脏", "明显压高光一点",
    "轻微明显压高光", "曝光增加", "压高光，高光设为10", "压高光，降低高光",
    "拉阴影，压阴影", "", "；，", "a" * 4097,
])
def test_unsupported_ambiguous_or_conflicting_proposal_is_rejected(text):
    with pytest.raises(LuminaError):
        suggest(text)


def test_dictionary_aliases_are_unique_and_all_have_valid_operations():
    from lumina.semantics.dictionary import RULES
    aliases = [a for rule in RULES for a in rule.aliases]
    assert len(aliases) == len(set(aliases))
    assert len({rule.id for rule in RULES}) == len(RULES)
    for alias in aliases:
        for strength in ("gentle", "standard", "strong"):
            assert len(suggest(alias, strength)["operations"]) == 1
    copy = catalog()
    copy["rules"].clear()
    assert catalog()["rules"]


def test_invalid_strength_and_host_precision():
    with pytest.raises(LuminaError, match="强度"):
        suggest("压高光", "maximum")
    with localcontext() as ctx:
        ctx.prec = 1
        ctx.traps[Inexact] = True
        assert suggest("整体提亮", "strong")["operations"][0]["value"] == .3


def test_preview_apply_backup_and_repeat_rejection(make_photo):
    nef, xmp = make_photo()
    original, raw = xmp.read_bytes(), nef.read_bytes()
    text = "压高光，拉阴影，整体提亮"
    plan = plan_style(nef, text)
    assert [c["after"] for c in plan["changes"]] == [-60, 50, .45]
    assert xmp.read_bytes() == original
    assert apply_style(nef, text, dry_run=True)["status"] == "dry_run"
    assert not list(xmp.parent.glob("*.bak"))
    result = apply_style(nef, text, expected_preview=plan["preview_sha256"])
    assert result["status"] == "updated"
    assert Path(result["backup_path"]).read_bytes() == original
    assert len(list(xmp.parent.glob("*.bak"))) == 1
    assert nef.read_bytes() == raw
    assert read_parameters(nef)["parameters"]["Highlights"] == -60
    after = xmp.read_bytes()
    with pytest.raises(LuminaError, match="与预览不同"):
        apply_style(nef, text, expected_preview=plan["preview_sha256"])
    assert xmp.read_bytes() == after


@pytest.mark.parametrize("change", ["text", "strength", "xmp", "path", "version"])
def test_preview_binds_complete_proposal(make_photo, tmp_path, monkeypatch, change):
    nef, xmp = make_photo()
    text, strength = "压高光", "standard"
    digest = plan_style(nef, text)["preview_sha256"]
    if change == "text":
        text = "拉阴影"
    elif change == "strength":
        strength = "strong"
    elif change == "xmp":
        xmp.write_bytes(xmp.read_bytes().replace(b'crs:Contrast2012="10"', b'crs:Contrast2012="11"'))
    elif change == "version":
        monkeypatch.setattr("lumina.semantics.VERSION", "future")
    else:
        other = tmp_path / "other"
        other.mkdir()
        copied = other / nef.name
        copied.write_bytes(nef.read_bytes())
        copied.with_suffix(".xmp").write_bytes(xmp.read_bytes())
        nef, xmp = copied, copied.with_suffix(".xmp")
    before = xmp.read_bytes(), set(xmp.parent.iterdir())
    with pytest.raises(LuminaError, match="与预览不同"):
        apply_style(nef, text, strength=strength, expected_preview=digest)
    assert before == (xmp.read_bytes(), set(xmp.parent.iterdir()))


@pytest.mark.parametrize("digest", [None, "", "invalid", True])
def test_actual_apply_requires_valid_preview(make_photo, digest):
    nef, xmp = make_photo()
    before = xmp.read_bytes()
    with pytest.raises(LuminaError):
        apply_style(nef, "压高光", expected_preview=digest)
    assert xmp.read_bytes() == before
    assert not list(xmp.parent.glob("*.bak"))


def test_white_balance_blocks_whole_semantic_batch(make_photo):
    nef, xmp = make_photo()
    text = "压高光，画面冷一点"
    before = xmp.read_bytes()
    plan = plan_style(nef, text)
    assert plan["changes"][1]["after"] == 4900
    assert not plan["can_apply"]
    with pytest.raises(LuminaError, match="白平衡"):
        apply_style(nef, text, expected_preview=plan["preview_sha256"])
    assert xmp.read_bytes() == before


@pytest.mark.parametrize("attributes", [{"Highlights2012": "-95"}, {"Highlights2012": None}])
def test_no_clamping_or_invented_defaults(make_photo, attributes):
    nef, xmp = make_photo(attributes=attributes)
    before = xmp.read_bytes()
    with pytest.raises(LuminaError):
        plan_style(nef, "压高光")
    assert xmp.read_bytes() == before


def test_external_change_after_plan_calculation_is_not_overwritten(make_photo, monkeypatch):
    nef, xmp = make_photo()
    digest = plan_style(nef, "压高光")["preview_sha256"]
    before = xmp.read_bytes()
    backup = writer._backup
    external = before.replace(b'crs:Contrast2012="10"', b'crs:Contrast2012="15"')

    def concurrent(document):
        result = backup(document)
        xmp.write_bytes(external)
        return result

    monkeypatch.setattr(writer, "_backup", concurrent)
    with pytest.raises(LuminaError, match="其他程序修改"):
        apply_style(nef, "压高光", expected_preview=digest)
    assert xmp.read_bytes() == external


def test_semantic_cli_flow(make_photo, capsys):
    assert main(["styles"]) == 0
    assert json.loads(capsys.readouterr().out)["rules"]
    assert main(["suggest", "压高光"]) == 0
    assert json.loads(capsys.readouterr().out)["matches"]
    nef, _ = make_photo()
    assert main(["plan-style", str(nef), "压高光"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert main(["apply-style", str(nef), "压高光"]) == 1
    assert "expect-plan" in capsys.readouterr().err
    assert main(["apply-style", str(nef), "压高光", "--expect-plan", plan["preview_sha256"]]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "updated"
