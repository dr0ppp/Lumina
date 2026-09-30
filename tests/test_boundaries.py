"""Guard subject identity, packet flags and host-independent arithmetic."""

from decimal import Inexact, localcontext

import pytest

from lumina.adjustments import apply_adjustments, plan_adjustments
from lumina.errors import LuminaError
from lumina.parser import parse_instructions
from lumina.xmp import read_parameters, set_exposure, set_parameters


@pytest.mark.parametrize("trailer", [
    'end = "r"', "end\t=\t'r'", 'end = "unknown"',
    'end="w" end="r"', 'end=unquoted',
])
def test_unwritable_packet_variants_leave_every_file_untouched(make_photo, trailer):
    nef, xmp = make_photo()
    before = xmp.read_bytes().replace(b'end="w"', trailer.encode())
    xmp.write_bytes(before)
    files = set(xmp.parent.iterdir())
    assert not plan_adjustments(nef, "曝光+0.3")["can_apply"]
    with pytest.raises(LuminaError, match="packet"):
        set_parameters(nef, {"Exposure": .55, "Highlights": -60})
    assert xmp.read_bytes() == before
    assert set(xmp.parent.iterdir()) == files


def test_writable_packet_with_spaces_is_preserved(make_photo):
    nef, xmp = make_photo()
    xmp.write_bytes(xmp.read_bytes().replace(b'end="w"', b"end = 'w'"))
    set_exposure(nef, ".55")
    assert b"<?xpacket end = 'w'?>" in xmp.read_bytes()


@pytest.mark.parametrize("tag", [b"x:xmpmeta", b"rdf:RDF", b"rdf:Description"])
def test_inherited_xml_base_cannot_redirect_current_subject(make_photo, tag):
    nef, xmp = make_photo()
    before = xmp.read_bytes().replace(b"<" + tag + b" ", b"<" + tag + b' xml:base="other.NEF" ', 1)
    xmp.write_bytes(before)
    with pytest.raises(LuminaError, match="xml:base"):
        set_exposure(nef, ".5")
    assert xmp.read_bytes() == before
    assert not list(xmp.parent.glob("*.bak"))


@pytest.mark.parametrize("identifier", ["ID", "nodeID"])
def test_conflicting_subject_identifiers_are_rejected(make_photo, identifier):
    nef, xmp = make_photo()
    before = xmp.read_bytes().replace(b'rdf:about=""', f'rdf:about="" rdf:{identifier}="other"'.encode())
    xmp.write_bytes(before)
    with pytest.raises(LuminaError, match="RDF 标识"):
        read_parameters(nef)
    assert xmp.read_bytes() == before


def test_unrelated_nested_base_is_preserved(make_photo):
    nef, xmp = make_photo(children='<test:other xml:base="other.NEF">preserve</test:other>')
    set_exposure(nef, ".5")
    assert b'xml:base="other.NEF"' in xmp.read_bytes()


def test_parser_and_application_ignore_host_decimal_context(make_photo):
    nef, _ = make_photo()
    with localcontext() as context:
        context.prec = 1
        context.traps[Inexact] = True
        context.clear_flags()
        text = "曝光+0.3，高光降低12，阴影设为25"
        operations = parse_instructions(text)
        assert str(operations[1].value) == "-12"
        plan = plan_adjustments(nef, text)
        assert [change["after"] for change in plan["changes"]] == [.55, -52, 25]
        assert apply_adjustments(nef, text)["status"] == "updated"
        assert set_exposure(nef, "1.25")["after"] == 1.25
        assert not any(context.flags.values())


def test_inexact_exposure_remains_a_controlled_error_with_host_traps():
    with localcontext() as context:
        context.traps[Inexact] = True
        with pytest.raises(LuminaError, match="不会自动舍入"):
            parse_instructions("曝光设为0.333")


@pytest.mark.parametrize("value", ["0_0.5", "０.５", "1e-10000"])
def test_nonstandard_or_underflowing_xmp_number_is_not_silently_converted(make_photo, value):
    nef, xmp = make_photo(attributes={"Exposure2012": value})
    before = xmp.read_bytes()
    with pytest.raises(LuminaError):
        read_parameters(nef)
    assert xmp.read_bytes() == before
