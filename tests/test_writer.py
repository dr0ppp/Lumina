from pathlib import Path
import stat

from lxml import etree
import pytest

from lumina.xmp import read_parameters, set_exposure
from lumina.xmp.errors import LuminaError
from lumina.xmp.reader import parse_xmp, property_slots
from lumina.xmp import writer


def without_global_exposure(data):
    tree = parse_xmp(data)
    slot = property_slots(tree)["Exposure2012"]
    slot.set("EXCLUDED_FROM_COMPARISON")
    return etree.tostring(tree, method="c14n", with_comments=True)


@pytest.mark.parametrize("element_form", [False, True])
def test_backup_and_only_global_exposure_changes(make_photo, element_form):
    attributes = {"Exposure2012": None} if element_form else {}
    exposure = "<crs:Exposure2012>0.25</crs:Exposure2012>" if element_form else ""
    children = exposure + '''
      <crs:Snapshots><rdf:Seq><rdf:li><rdf:Description crs:Exposure2012="+2.00" crs:ProcessVersion="5.7" /></rdf:li></rdf:Seq></crs:Snapshots>
      <crs:MaskGroupBasedCorrections><rdf:Seq><rdf:li crs:Exposure2012="-1.00" /></rdf:Seq></crs:MaskGroupBasedCorrections>
      <crs:ToneCurvePV2012><rdf:Seq><rdf:li>0, 0</rdf:li><rdf:li>255, 255</rdf:li></rdf:Seq></crs:ToneCurvePV2012>
      <test:unknownStructure><test:data><![CDATA[keep <this>]]></test:data></test:unknownStructure>
    '''
    nef, xmp = make_photo(attributes=attributes, children=children)
    before, raw = xmp.read_bytes(), nef.read_bytes()
    result = set_exposure(nef, "0.50")
    after = xmp.read_bytes()
    assert result["status"] == "updated"
    assert result["before"] == .25 and result["after"] == .5
    assert Path(result["backup_path"]).read_bytes() == before
    assert without_global_exposure(before) == without_global_exposure(after)
    assert b'<?xpacket end="w"?>' in after
    assert b"keep comment" in after
    assert nef.read_bytes() == raw
    assert read_parameters(nef)["parameters"]["Exposure"] == .5
    assert not list(xmp.parent.glob("*.tmp"))
    # Restore the exact original bytes as documented and verify the old value.
    xmp.write_bytes(Path(result["backup_path"]).read_bytes())
    assert read_parameters(nef)["parameters"]["Exposure"] == .25


def test_dry_run_does_not_create_or_change_files(make_photo):
    nef, xmp = make_photo()
    before = xmp.read_bytes(), xmp.stat().st_mtime_ns, set(xmp.parent.iterdir())
    result = set_exposure(nef, ".5", dry_run=True)
    assert result["status"] == "dry_run"
    assert result["backup_path"] is None
    assert before == (xmp.read_bytes(), xmp.stat().st_mtime_ns, set(xmp.parent.iterdir()))


def test_repeated_absolute_assignment_is_noop(make_photo):
    nef, xmp = make_photo()
    first = set_exposure(nef, ".5")
    before = xmp.read_bytes(), xmp.stat().st_mtime_ns
    second = set_exposure(nef, "0.500")
    assert second["status"] == "unchanged"
    assert second["backup_path"] is None
    assert before == (xmp.read_bytes(), xmp.stat().st_mtime_ns)
    assert len(list(xmp.parent.glob("*.bak"))) == 1
    assert Path(first["backup_path"]).exists()


@pytest.mark.parametrize("value", ["-5", "5", "0", "-0.00", "-0.35"])
def test_valid_exposure_boundaries(make_photo, value):
    nef, _ = make_photo()
    set_exposure(nef, value)
    assert read_parameters(nef)["parameters"]["Exposure"] == float(value)


@pytest.mark.parametrize("value", [
    "-5.01", "5.01", "0.333", "NaN", "sNaN", "Infinity", "-Infinity",
    "1e999999", "0.5oops", "", True, None,
])
def test_invalid_values_do_not_touch_files(make_photo, value):
    nef, xmp = make_photo()
    before = xmp.read_bytes(), set(xmp.parent.iterdir())
    with pytest.raises(LuminaError):
        set_exposure(nef, value)
    assert before == (xmp.read_bytes(), set(xmp.parent.iterdir()))


@pytest.mark.parametrize("attributes", [
    {"ProcessVersion": "5.7"}, {"ProcessVersion": "99.0"}, {"ProcessVersion": None},
    {"HasSettings": "False"}, {"HasSettings": None}, {"Exposure2012": None},
    {"AutoTone": "True"}, {"AutoExposure": "true"},
])
def test_unsupported_settings_are_not_migrated(make_photo, attributes):
    nef, xmp = make_photo(attributes=attributes)
    before = xmp.read_bytes()
    with pytest.raises(LuminaError):
        set_exposure(nef, ".5")
    assert xmp.read_bytes() == before
    assert not list(xmp.parent.glob("*.bak"))


def test_readonly_file_and_packet(make_photo):
    nef, xmp = make_photo()
    before = xmp.read_bytes()
    xmp.chmod(stat.S_IREAD)
    try:
        with pytest.raises(LuminaError, match="只读"):
            set_exposure(nef, ".5")
    finally:
        xmp.chmod(stat.S_IREAD | stat.S_IWRITE)
    assert xmp.read_bytes() == before
    xmp.write_bytes(before.replace(b'end="w"', b'end="r"'))
    with pytest.raises(LuminaError, match="只读"):
        set_exposure(nef, ".5")


def test_backup_failure_keeps_original_and_cleans_temp(make_photo, monkeypatch):
    nef, xmp = make_photo()
    before = xmp.read_bytes()

    def fail_backup(document):
        raise PermissionError("simulated backup failure")

    monkeypatch.setattr(writer, "_backup", fail_backup)
    with pytest.raises(LuminaError, match="未替换"):
        set_exposure(nef, ".5")
    assert xmp.read_bytes() == before
    assert not list(xmp.parent.glob("*.tmp"))


def test_unserializable_unknown_metadata_is_a_safe_error(make_photo):
    nef, xmp = make_photo()
    # Relative namespace URIs cannot be canonicalized by libxml2.
    before = xmp.read_bytes().replace(b'xmlns:test="urn:lumina:test"', b'xmlns:test="relative"')
    xmp.write_bytes(before)
    with pytest.raises(LuminaError, match="未替换"):
        set_exposure(nef, ".5")
    assert xmp.read_bytes() == before
    assert not list(xmp.parent.glob("*.bak"))


def test_replace_failure_keeps_original_and_backup(make_photo, monkeypatch):
    nef, xmp = make_photo()
    before = xmp.read_bytes()

    def fail_replace(source, target):
        raise PermissionError("simulated Windows sharing violation")

    monkeypatch.setattr(writer.os, "replace", fail_replace)
    with pytest.raises(LuminaError, match="原始备份"):
        set_exposure(nef, ".5")
    assert xmp.read_bytes() == before
    assert next(xmp.parent.glob("*.bak")).read_bytes() == before
    assert not list(xmp.parent.glob("*.tmp"))


def test_external_change_during_backup_is_not_overwritten(make_photo, monkeypatch):
    nef, xmp = make_photo()
    before = xmp.read_bytes()
    external = before.replace(b'crs:Exposure2012="+0.25"', b'crs:Exposure2012="+1.00"')
    original_backup = writer._backup

    def simultaneous_writer(document):
        path = original_backup(document)
        xmp.write_bytes(external)
        return path

    monkeypatch.setattr(writer, "_backup", simultaneous_writer)
    with pytest.raises(LuminaError, match="其他程序修改"):
        set_exposure(nef, ".5")
    assert xmp.read_bytes() == external
    assert next(xmp.parent.glob("*.bak")).read_bytes() == before
    assert not list(xmp.parent.glob("*.tmp"))


def test_change_after_replace_is_reported_without_overwriting_external_edit(make_photo, monkeypatch):
    nef, xmp = make_photo()
    before = xmp.read_bytes()
    original_replace = writer.os.replace
    external = before.replace(b'crs:Exposure2012="+0.25"', b'crs:Exposure2012="+2.00"')

    def external_write_after_replace(source, target):
        original_replace(source, target)
        xmp.write_bytes(external)

    monkeypatch.setattr(writer.os, "replace", external_write_after_replace)
    with pytest.raises(LuminaError, match="替换已完成"):
        set_exposure(nef, ".5")
    assert xmp.read_bytes() == external
    assert next(xmp.parent.glob("*.bak")).read_bytes() == before
