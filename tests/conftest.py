"""Only artificial XML and fake RAW bytes; no private media in Git."""

import pytest

from lumina.xmp.mapping import CRS, RDF, XMP_META


@pytest.fixture
def make_photo(tmp_path):
    def make(*, attributes=None, children="", extra_descriptions="", prefix="crs", suffix=".xmp"):
        directory = tmp_path / "照片 test"
        directory.mkdir(exist_ok=True)
        nef = directory / "DSC_0001.NEF"
        nef.write_bytes(b"artificial RAW placeholder - never a real NEF")
        values = {
            "Version": "17.5", "ProcessVersion": "15.4", "HasSettings": "True",
            "WhiteBalance": "As Shot", "Exposure2012": "+0.25",
            "Contrast2012": "10", "Highlights2012": "-40", "Shadows2012": "+30",
            "Whites2012": "5", "Blacks2012": "-5", "Temperature": "5050",
            "Tint": "+29", "Vibrance": "12", "Saturation": "-3",
        }
        for key, value in (attributes or {}).items():
            if value is None:
                values.pop(key, None)
            else:
                values[key] = value
        attrs = " ".join(f'{prefix}:{key}="{value}"' for key, value in values.items())
        data = f'''<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="{XMP_META}">
  <rdf:RDF xmlns:rdf="{RDF}" xmlns:{prefix}="{CRS}" xmlns:test="urn:lumina:test" xmlns:dc="http://purl.org/dc/elements/1.1/">
    <rdf:Description rdf:about="" {attrs} test:unknown="keep">
      <!-- keep comment -->
      <dc:description><rdf:Alt><rdf:li xml:lang="x-default">人工测试 &amp; metadata</rdf:li></rdf:Alt></dc:description>
      {children}
    </rdf:Description>
    {extra_descriptions}
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>'''.encode("utf-8")
        xmp = nef.with_suffix(suffix)
        xmp.write_bytes(data)
        return nef, xmp
    return make
