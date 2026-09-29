import pytest

from lumina.xmp.errors import LuminaError
from lumina.xmp.mapping import CRS, RDF
from lumina.xmp.reader import read_parameters


def test_reads_ten_typed_parameters_without_touching_files(make_photo):
    nef, xmp = make_photo()
    before = (nef.read_bytes(), xmp.read_bytes(), xmp.stat().st_mtime_ns)
    result = read_parameters(nef)
    assert result["parameters"] == {
        "Exposure": .25, "Contrast": 10, "Highlights": -40, "Shadows": 30,
        "Whites": 5, "Blacks": -5, "Temperature": 5050, "Tint": 29,
        "Vibrance": 12, "Saturation": -3,
    }
    assert isinstance(result["parameters"]["Exposure"], float)
    assert isinstance(result["parameters"]["Temperature"], int)
    assert result["missing_fields"] == []
    assert result["metadata"]["ProcessVersion"] == "15.4"
    assert result["metadata"]["WhiteBalance"] == "As Shot"
    assert (nef.read_bytes(), xmp.read_bytes(), xmp.stat().st_mtime_ns) == before


def test_alternate_namespace_prefix_and_uppercase_extension(make_photo):
    nef, _ = make_photo(prefix="settings", suffix=".XMP")
    assert read_parameters(nef)["parameters"]["Exposure"] == .25


def test_element_form_and_split_descriptions(make_photo):
    nef, _ = make_photo(
        attributes={"Exposure2012": None, "Tint": None},
        children="<crs:Exposure2012>+0.75</crs:Exposure2012>",
        extra_descriptions='<rdf:Description rdf:about=""><crs:Tint>20</crs:Tint></rdf:Description>',
    )
    assert read_parameters(nef)["parameters"]["Exposure"] == .75
    assert read_parameters(nef)["parameters"]["Tint"] == 20


def test_missing_field_is_not_zero(make_photo):
    nef, _ = make_photo(attributes={"Highlights2012": None})
    report = read_parameters(nef)
    assert "Highlights" not in report["parameters"]
    assert report["missing_fields"] == ["Highlights"]


def test_nested_values_and_other_subjects_are_not_current_parameters(make_photo):
    nef, _ = make_photo(
        attributes={"Exposure2012": None},
        children='<crs:Snapshots><rdf:Seq><rdf:li crs:Exposure2012="4" /></rdf:Seq></crs:Snapshots>',
        extra_descriptions='<rdf:Description rdf:about="other-photo" crs:Exposure2012="3" />',
    )
    assert "Exposure" not in read_parameters(nef)["parameters"]


@pytest.mark.parametrize("extra", [
    '<crs:Exposure2012>0.25</crs:Exposure2012>',
    '<crs:Exposure2012>0.50</crs:Exposure2012>',
])
def test_duplicate_fields_are_errors_even_if_equal(make_photo, extra):
    nef, _ = make_photo(children=extra)
    with pytest.raises(LuminaError, match="重复"):
        read_parameters(nef)


def test_duplicate_across_descriptions(make_photo):
    nef, _ = make_photo(extra_descriptions='<rdf:Description rdf:about="" crs:ProcessVersion="15.4" />')
    with pytest.raises(LuminaError, match="重复"):
        read_parameters(nef)


def test_unsupported_version_is_visible_and_old_fields_not_remapped(make_photo):
    nef, _ = make_photo(attributes={"ProcessVersion": "5.7", "Exposure2012": None, "Exposure": "1"})
    report = read_parameters(nef)
    assert "Exposure" not in report["parameters"]
    assert any("不支持写入" in warning for warning in report["warnings"])


@pytest.mark.parametrize("field,value", [
    ("Exposure2012", "NaN"), ("Exposure2012", "Infinity"),
    ("Exposure2012", "1e999999"), ("Exposure2012", "abc"),
    ("Tint", "1.5"), ("Exposure2012", ""),
])
def test_invalid_numeric_fields(make_photo, field, value):
    nef, _ = make_photo(attributes={field: value})
    with pytest.raises(LuminaError):
        read_parameters(nef)


def test_complex_scalar_is_rejected(make_photo):
    nef, _ = make_photo(attributes={"Exposure2012": None}, children='<crs:Exposure2012><rdf:Seq /></crs:Exposure2012>')
    with pytest.raises(LuminaError, match="复杂"):
        read_parameters(nef)


def test_raw_name_mismatch(make_photo):
    nef, _ = make_photo(attributes={"RawFileName": "OTHER.NEF"})
    with pytest.raises(LuminaError, match="RawFileName"):
        read_parameters(nef)


def test_missing_nef_and_wrong_extension(tmp_path):
    with pytest.raises(LuminaError, match="NEF 文件不存在"):
        read_parameters(tmp_path / "missing.NEF")
    with pytest.raises(LuminaError, match="仅接受"):
        read_parameters(tmp_path / "photo.jpg")


def test_missing_sidecar_is_not_created(make_photo):
    nef, xmp = make_photo()
    xmp.unlink()
    with pytest.raises(LuminaError, match="未找到同名"):
        read_parameters(nef)
    assert not xmp.exists()


@pytest.mark.parametrize("content", [b"", b"<broken>", b"<html />"])
def test_invalid_documents(make_photo, content):
    nef, xmp = make_photo()
    xmp.write_bytes(content)
    with pytest.raises(LuminaError):
        read_parameters(nef)
    assert xmp.read_bytes() == content


def test_dtd_and_external_entity_are_rejected(make_photo, tmp_path):
    nef, xmp = make_photo()
    secret = tmp_path / "private.txt"
    secret.write_text("must not resolve", encoding="utf-8")
    xmp.write_text(
        f'<!DOCTYPE rdf:RDF [<!ENTITY ext SYSTEM "{secret.as_uri()}">]>'
        f'<rdf:RDF xmlns:rdf="{RDF}" xmlns:crs="{CRS}">'
        '<rdf:Description rdf:about=""><crs:Exposure2012>&ext;</crs:Exposure2012></rdf:Description></rdf:RDF>',
        encoding="utf-8",
    )
    with pytest.raises(LuminaError) as failure:
        read_parameters(nef)
    assert "must not resolve" not in str(failure.value)


def test_size_limit(make_photo, monkeypatch):
    nef, _ = make_photo()
    monkeypatch.setattr("lumina.xmp.reader.MAX_XMP_BYTES", 50)
    with pytest.raises(LuminaError, match="大小上限"):
        read_parameters(nef)
