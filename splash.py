"""Schermata di caricamento italiana, al posto di CARGANDO.

L'immagine è dentro il .nro (nx_espera). Stessa dimensione in byte, così
il motore la decodifica senza essere ricompilato.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

PNG_LEN = 21405
APP_VERSION = "0.7.5"
CREDIT = "made by Zephiro"


def _chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def fit_png(png: bytes, size: int = PNG_LEN) -> bytes:
    """Allunga un PNG valido fino a `size` con un chunk tEXt, senza spostare IEND."""
    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Non è un PNG.")
    if len(png) > size:
        raise ValueError(f"Il PNG pesa {len(png)} byte, il posto nel motore è {size}.")
    iend = png[-12:]
    if iend[4:8] != b"IEND":
        raise ValueError("Il PNG non finisce con IEND.")
    extra = size - len(png)
    if extra == 0:
        return png
    if extra < 12:
        raise ValueError("Manca spazio per il chunk di riempimento.")
    keyword = b"Comment\x00"
    room = extra - 12 - len(keyword)
    if room >= 0:
        chunk = _chunk(b"tEXt", keyword + (b" " * room))
    else:
        chunk = _chunk(b"fdPt", b"\x00" * (extra - 12))
    fitted = png[:-12] + chunk + iend
    if len(fitted) != size:
        raise ValueError(f"Riempimento {len(fitted)} invece di {size}.")
    return fitted


def _font(size: int, bold: bool):
    from PIL import ImageFont
    bundled = Path(__file__).resolve().parent / "assets" / "fonts"
    names = (
        (
            bundled / "BebasNeue-Regular.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        )
        if bold
        else (
            bundled / "Inter-Regular.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        )
    )
    for path in names:
        if Path(path).is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _center(draw, text: str, y: int, size: int, color, bold: bool, canvas: int = 640) -> None:
    font = _font(size, bold)
    box = draw.textbbox((0, 0), text, font=font)
    width = box[2] - box[0]
    while width > canvas - 48 and size > 16:
        size -= 2
        font = _font(size, bold)
        box = draw.textbbox((0, 0), text, font=font)
        width = box[2] - box[0]
    draw.text(((canvas - width) / 2, y), text, font=font, fill=color)


def render_loading_png(title: str, icon=None, app_version: str = APP_VERSION, lang: str = "en") -> bytes:
    from PIL import Image, ImageDraw
    image = Image.new("RGBA", (640, 400), (10, 20, 40, 255))
    draw = ImageDraw.Draw(image)
    brand = _font(28, True)
    mark_path = Path(__file__).resolve().parent / "assets" / "logo-mark.png"
    brand_x = 28
    if mark_path.is_file():
        try:
            logo = Image.open(mark_path).convert("RGBA")
            mh = 32
            mw = max(int(logo.width * mh / max(logo.height, 1)), 1)
            logo = logo.resize((mw, mh), Image.Resampling.LANCZOS)
            pixels = logo.load()
            tint = (120, 198, 255, 255)
            for y in range(mh):
                for x in range(mw):
                    _, _, _, a = pixels[x, y]
                    pixels[x, y] = (*tint[:3], a)
            image.paste(logo, (28, 16), logo)
            brand_x = 28 + mw + 10
        except Exception:
            brand_x = 28
    draw.text((brand_x, 18), "FAN PORTER", font=brand, fill=(234, 241, 255, 255))
    draw.text((28, 54), CREDIT, font=_font(16, False), fill=(143, 163, 199, 255))
    draw.text((28, 76), app_version, font=_font(15, False), fill=(63, 169, 255, 255))

    mark = icon.convert("RGBA") if icon is not None else None
    if mark is not None:
        side = 112
        mark = mark.resize((side, side), Image.Resampling.LANCZOS)
        image.paste(mark, ((640 - side) // 2, 112), mark)
        name_y, load_y = 236, 282
    else:
        name_y, load_y = 150, 204
    _center(draw, title or "Fan game", name_y, 32, (234, 241, 255, 255), True)
    loading = "CARICAMENTO" if lang == "it" else "LOADING"
    _center(draw, loading, load_y, 36, (234, 241, 255, 255), True)
    _center(draw, "−  menu     +  turbo", 352, 16, (143, 163, 199, 255), False)

    raw = _png_bytes(image)
    if len(raw) > PNG_LEN and mark is not None:
        smaller = mark.resize((72, 72), Image.Resampling.LANCZOS)
        image.paste(Image.new("RGBA", (112, 112), (10, 20, 40, 255)), ((640 - 112) // 2, 112))
        image.paste(smaller, ((640 - 72) // 2, 132), smaller)
        raw = _png_bytes(image)
    if len(raw) > PNG_LEN:
        flat = image.convert("P", palette=Image.Palette.ADAPTIVE, colors=48).convert("RGBA")
        raw = _png_bytes(flat)
    return fit_png(raw, PNG_LEN)


def _png_bytes(image) -> bytes:
    import io
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True, compress_level=9)
    return buffer.getvalue()


def _png_size(blob: bytes, start: int) -> int:
    if blob[start:start + 8] != b"\x89PNG\r\n\x1a\n":
        return 0
    pos = start + 8
    while pos + 12 <= len(blob):
        length = struct.unpack_from(">I", blob, pos)[0]
        if length > 20_000_000:
            return 0
        tag = blob[pos + 4:pos + 8]
        pos += 12 + length
        if tag == b"IEND":
            return pos - start
    return 0


def find_loading_png(blob: bytes):
    signature = b"\x89PNG\r\n\x1a\n"
    start = 0
    while True:
        found = blob.find(signature, start)
        if found < 0:
            return None
        size = _png_size(blob, found)
        if size == PNG_LEN and found >= 8:
            declared = struct.unpack_from("<Q", blob, found - 16)[0]
            if declared == PNG_LEN:
                return found
        start = found + 1


def stamp_loading_screen(path: Path, title: str, icon=None, app_version: str = APP_VERSION, lang: str = "en") -> bool:
    blob = bytearray(path.read_bytes())
    where = find_loading_png(blob)
    if where is None:
        return False
    png = render_loading_png(title, icon, app_version, lang)
    blob[where:where + PNG_LEN] = png
    path.write_bytes(blob)
    return True
