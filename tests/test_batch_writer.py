from pathlib import Path

from lxml import etree
import pytest

from lumina.errors import LuminaError
from lumina.xmp import read_parameters, set_parameters
from lumina.xmp.mapping import PARAMETERS
from lumina.xmp.reader import load_document, parse_xmp, property_slots
from lumina.xmp import writer


def without_targets(data, targets):
    tree = parse_xmp(data)
    slots = property_slots(tree)
    for name in targets:
        slots[PARAMETERS[name].xmp_name].set("EXCLUDED_FROM_COMPARISON")
    return etree.tostring(tree, method="c14n", with_comments=True)


def test_eight_parameter_batch_preserves_everything_else_and_creates_one_backup(make_photo):
    nef, xmp = make_photo(children='''
      <crs:Snapshots><rdf:Seq><rdf:li><rdf:Description crs:Exposure2012="+2.00" crs:Highlights2012="-90" crs:Saturation="33" /></rdf:li></rdf:Seq></crs:Snapshots>
      <crs:MaskGroupBasedCorrections><rdf:Seq><rdf:li crs:Contrast2012="70" crs:Whites2012="-90" /></rdf:Seq></crs:MaskGroupBasedCorrections>
    ''')
    before, raw = xmp.read_bytes(), nef.read_bytes()
    targets = {"Exposure": ".55", "Contrast": 20, "Highlights": -60, "Shadows": 50,
               "Whites": -5, "Blacks": 5, "Vibrance": 20, "Saturation": -10}
    result = set_parameters(nef, targets)
    assert result["status"] == "updated" and len(result["changes"]) == 8
    actual = read_parameters(nef)["parameters"]
    assert {key: actual[key] for key in targets} == {**targets, "Exposure": .55}
    assert actual["Temperature"] == 5050 and actual["Tint"] == 29
    assert without_targets(before, targets) == without_targets(xmp.read_bytes(), targets)
    assert len(list(xmp.parent.glob("*.bak"))) == 1
    assert Path(result["backup_path"]).read_bytes() == before
    assert nef.read_bytes() == raw


def test_unchanged_requested_field_preserves_its_original_representation(make_photo):
    nef, xmp = make_photo(attributes={"Contrast2012": "+0010"})
    set_parameters(nef, {"Exposure": .5, "Contrast": 10})
    assert b'crs:Contrast2012="+0010"' in xmp.read_bytes()


def test_element_fields_and_batch_noop(make_photo):
    nef, xmp = make_photo(attributes={"Highlights2012": None}, children='<crs:Highlights2012>-40</crs:Highlights2012>')
    targets = {"Exposure": .5, "Highlights": -60}
    set_parameters(nef, targets)
    assert b"<crs:Highlights2012>-60</crs:Highlights2012>" in xmp.read_bytes()
    before = xmp.read_bytes(), xmp.stat().st_mtime_ns, set(xmp.parent.iterdir())
    assert set_parameters(nef, targets)["status"] == "unchanged"
    assert before == (xmp.read_bytes(), xmp.stat().st_mtime_ns, set(xmp.parent.iterdir()))


@pytest.mark.parametrize("targets", [
    {"Exposure": .5, "Contrast": 101}, {"Exposure": .5, "Highlights": -101},
    {"Exposure": .5, "Shadows": 1.5}, {"Exposure": .5, "Whites": "NaN"},
    {"Exposure": .5, "Saturation": True}, {"Exposure": .5, "Unknown": 3},
    {"Exposure": .5, "Temperature": 5200}, {"Exposure": .5, "Tint": 10}, {}, [],
])
def test_invalid_batch_has_no_partial_changes_or_backup(make_photo, targets):
    nef, xmp = make_photo()
    before = xmp.read_bytes(), set(xmp.parent.iterdir())
    with pytest.raises(LuminaError):
        set_parameters(nef, targets)
    assert before == (xmp.read_bytes(), set(xmp.parent.iterdir()))


@pytest.mark.parametrize("name", ["Contrast", "Highlights", "Shadows", "Whites", "Blacks", "Vibrance", "Saturation"])
@pytest.mark.parametrize("value", [-100, 100])
def test_integer_endpoints_are_valid(make_photo, name, value):
    nef, _ = make_photo()
    set_parameters(nef, {name: value})
    assert read_parameters(nef)["parameters"][name] == value


def test_unrelated_missing_exposure_does_not_require_inventing_it(make_photo):
    nef, _ = make_photo(attributes={"Exposure2012": None})
    set_parameters(nef, {"Contrast": 30})
    parameters = read_parameters(nef)["parameters"]
    assert parameters["Contrast"] == 30 and "Exposure" not in parameters


@pytest.mark.parametrize("digest", ["", "123", "z" * 64, "0" * 64, True])
def test_invalid_or_stale_digest_never_writes(make_photo, digest):
    nef, xmp = make_photo()
    before = xmp.read_bytes()
    with pytest.raises(LuminaError):
        set_parameters(nef, {"Exposure": .5}, expected_sha256=digest)
    assert xmp.read_bytes() == before


def test_failed_batch_does_not_mutate_loaded_snapshot_and_can_retry(make_photo, monkeypatch):
    nef, xmp = make_photo()
    document = load_document(nef)
    backup = writer._backup

    def fail_backup(document):
        raise OSError("simulated backup failure")

    monkeypatch.setattr(writer, "_backup", fail_backup)
    with pytest.raises(LuminaError):
        writer.write_document(document, {"Exposure": .5, "Highlights": -60})
    assert document.get("Exposure2012") == "+0.25"
    assert document.get("Highlights2012") == "-40"
    assert document.original == xmp.read_bytes()
    monkeypatch.setattr(writer, "_backup", backup)
    assert writer.write_document(document, {"Exposure": .5, "Highlights": -60})["status"] == "updated"


@pytest.mark.parametrize("fail_call", [1, 2])
def test_disk_sync_failure_keeps_original_and_leaves_no_invalid_backup(make_photo, monkeypatch, fail_call):
    nef, xmp = make_photo()
    before = xmp.read_bytes()
    calls = 0
    original_sync = writer.os.fsync

    def fail_sync(fd):
        nonlocal calls
        calls += 1
        if calls == fail_call:
            raise OSError("simulated disk failure")
        return original_sync(fd)

    monkeypatch.setattr(writer.os, "fsync", fail_sync)
    with pytest.raises(LuminaError, match="未替换"):
        set_parameters(nef, {"Exposure": .5, "Highlights": -60})
    assert xmp.read_bytes() == before
    assert not list(xmp.parent.glob("*.bak"))
    assert not list(xmp.parent.glob("*.tmp"))


def test_large_external_file_is_compared_with_a_bounded_read(tmp_path, monkeypatch):
    target = tmp_path / "large.xmp"
    target.write_bytes(b"x" * 10000)
    original_open = Path.open
    reads = []

    class TrackedRead:
        def __enter__(self):
            self.stream = original_open(target, "rb")
            return self

        def __exit__(self, *args):
            self.stream.close()

        def read(self, size=-1):
            reads.append(size)
            return self.stream.read(size)

    monkeypatch.setattr(Path, "open", lambda self, *args, **kwargs: TrackedRead())
    assert writer._matches_bytes(target, b"small snapshot") is False
    assert reads == [len(b"small snapshot") + 1]
