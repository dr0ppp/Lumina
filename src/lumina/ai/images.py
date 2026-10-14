"""Prepare an explicitly selected preview, without metadata or RAW decoding."""

import base64
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path

from ..errors import LuminaError


@dataclass(frozen=True)
class PreviewImage:
    data_url: str
    sha256: str


def prepare_image(path):
    from PIL import Image, ImageOps, UnidentifiedImageError

    with Path(path).open("rb") as stream:
        data = stream.read(20 * 1024 * 1024 + 1)
    if len(data) > 20 * 1024 * 1024:
        raise LuminaError("预览图超过 20 MiB；请导出较小的 sRGB JPEG/PNG。")
    try:
        with Image.open(BytesIO(data)) as source:
            if source.format not in {"JPEG", "PNG"} or getattr(source, "n_frames", 1) != 1:
                raise LuminaError("只接受单帧 JPEG/PNG 预览，不读取 RAW。")
            if source.width * source.height > 40000000:
                raise LuminaError("预览图超过 4000 万像素，请先缩小。")
            source.load()
            oriented = ImageOps.exif_transpose(source)
            oriented.thumbnail((1600, 1600))
            # Copy pixels to a fresh image so EXIF/XMP/ICC and other info do not travel.
            rgba = oriented.convert("RGBA")
            clean = Image.new("RGB", rgba.size, "white")
            clean.paste(rgba, mask=rgba.getchannel("A"))
            output = BytesIO()
            clean.save(output, format="JPEG", quality=85)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise LuminaError("无法安全读取该预览图，请重新导出 sRGB JPEG/PNG。") from None
    encoded = output.getvalue()
    if len(encoded) > 2 * 1024 * 1024:
        raise LuminaError("处理后的预览仍超过 2 MiB，请先缩小。")
    return PreviewImage("data:image/jpeg;base64," + base64.b64encode(encoded).decode("ascii"), sha256(encoded).hexdigest())
