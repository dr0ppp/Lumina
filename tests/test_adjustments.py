from pathlib import Path

import pytest

from lumina import adjustments
from lumina.adjustments import apply_adjustments, plan_adjustments
from lumina.errors import LuminaError
from lumina.xmp import read_parameters


def state(xmp):
    return xmp.read_bytes(), xmp.stat().st_mtime_ns, set(xmp.parent.iterdir())


def test_plan_resolves_nonzero_baseline_exactly_without_writes(make_photo):
    nef, xmp = make_photo()
    before = state(xmp)
    report = plan_adjustments(nef, "曝光+0.3，高光降低40，阴影提高30")
    assert report["changes"] == [
        {"parameter": "Exposure", "before": .25, "after": .55},
        {"parameter": "Highlights", "before": -40, "after": -80},
        {"parameter": "Shadows", "before": 30, "after": 60},
    ]
    assert report["can_apply"] is True
    assert len(report["original_xmp_sha256"]) == 64
    assert any("重复应用" in text for text in report["warnings"])
    assert state(xmp) == before


def test_assignments_are_absolute_and_repeating_them_is_noop(make_photo):
    nef, xmp = make_photo()
    text = "曝光设为0.3，高光设为-40，阴影设为30"
    result = apply_adjustments(nef, text)
    assert result["status"] == "updated"
    assert read_parameters(nef)["parameters"]["Exposure"] == .3
    before = state(xmp)
    assert apply_adjustments(nef, text)["status"] == "unchanged"
    assert state(xmp) == before


def test_repeating_relative_commands_adjusts_again(make_photo):
    nef, _ = make_photo()
    apply_adjustments(nef, "曝光增加0.3")
    second = apply_adjustments(nef, "曝光增加0.3")
    assert second["changes"] == [{"parameter": "Exposure", "before": .55, "after": .85}]


def test_relative_delta_may_exceed_absolute_range_when_result_is_valid(make_photo):
    nef, _ = make_photo(attributes={"Exposure2012": "-4.00"})
    apply_adjustments(nef, "曝光+8")
    assert read_parameters(nef)["parameters"]["Exposure"] == 4.0


@pytest.mark.parametrize("text", [
    "曝光+5", "曝光-6", "高光降低61", "阴影提高71", "曝光+0.3,高光降低61",
    "曝光+0.3,饱和度+10%", "曝光+0.3,曝光设为1", "曝光+0.3,随便好看一些",
])
def test_one_bad_clause_cancels_entire_batch(make_photo, text):
    nef, xmp = make_photo()
    before = state(xmp)
    with pytest.raises(LuminaError):
        apply_adjustments(nef, text)
    assert state(xmp) == before


@pytest.mark.parametrize("text", ["曝光+0.3,色温设为5200K", "色调增加10", "色温降低300"])
def test_white_balance_can_be_previewed_but_not_partially_applied(make_photo, text):
    nef, xmp = make_photo()
    before = state(xmp)
    report = plan_adjustments(nef, text)
    assert report["can_apply"] is False
    assert "白平衡" in report["blocked_reasons"][0]
    for dry_run in (False, True):
        with pytest.raises(LuminaError, match="白平衡"):
            apply_adjustments(nef, text, dry_run=dry_run)
    assert state(xmp) == before


@pytest.mark.parametrize("text", ["高光+10", "高光设为0"])
def test_missing_current_value_is_not_assumed_even_for_assignment(make_photo, text):
    nef, xmp = make_photo(attributes={"Highlights2012": None})
    before = state(xmp)
    with pytest.raises(LuminaError, match="当前值未记录"):
        plan_adjustments(nef, text)
    assert state(xmp) == before


@pytest.mark.parametrize("attributes", [
    {"ProcessVersion": "99.0"}, {"HasSettings": "False"}, {"AutoTone": "True"},
])
def test_file_settings_block_application_but_are_visible_in_plan(make_photo, attributes):
    nef, xmp = make_photo(attributes=attributes)
    before = state(xmp)
    plan = plan_adjustments(nef, "曝光+0.3")
    assert not plan["can_apply"]
    assert plan["blocked_reasons"]
    with pytest.raises(LuminaError, match="无法应用"):
        apply_adjustments(nef, "曝光+0.3")
    assert state(xmp) == before


def test_preview_digest_and_dry_run_then_apply(make_photo):
    nef, xmp = make_photo()
    before = state(xmp)
    text = "曝光+0.3，对比度-5，阴影+10"
    plan = plan_adjustments(nef, text)
    result = apply_adjustments(nef, text, dry_run=True, expected_sha256=plan["original_xmp_sha256"])
    assert result["status"] == "dry_run" and result["changes"] == plan["changes"]
    assert state(xmp) == before
    result = apply_adjustments(nef, text, expected_sha256=plan["original_xmp_sha256"])
    assert result["changes"] == plan["changes"]
    assert Path(result["backup_path"]).read_bytes() == before[0]


def test_expired_preview_never_overwrites_new_edits(make_photo):
    nef, xmp = make_photo()
    plan = plan_adjustments(nef, "曝光+0.3")
    external = xmp.read_bytes().replace(b'crs:Contrast2012="10"', b'crs:Contrast2012="20"')
    xmp.write_bytes(external)
    with pytest.raises(LuminaError, match="预览时不同"):
        apply_adjustments(nef, "曝光+0.3", expected_sha256=plan["original_xmp_sha256"])
    assert xmp.read_bytes() == external
    assert not list(xmp.parent.glob("*.bak"))


def test_load_only_once_and_detect_change_after_calculation(make_photo, monkeypatch):
    nef, xmp = make_photo()
    original_load = adjustments.load_document
    original_save = adjustments.write_document
    calls = []
    external = xmp.read_bytes().replace(b'crs:Exposure2012="+0.25"', b'crs:Exposure2012="+1.00"')

    def count_load(path):
        calls.append(path)
        return original_load(path)

    def concurrent_write(document, values, **kwargs):
        xmp.write_bytes(external)
        return original_save(document, values, **kwargs)

    monkeypatch.setattr(adjustments, "load_document", count_load)
    monkeypatch.setattr(adjustments, "write_document", concurrent_write)
    with pytest.raises(LuminaError, match="其他程序修改"):
        apply_adjustments(nef, "曝光+0.3")
    assert len(calls) == 1
    assert xmp.read_bytes() == external
