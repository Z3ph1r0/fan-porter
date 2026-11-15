"""Schermata di caricamento al posto di CARGANDO.

Logo Fan Porter al centro, sotto «made by zephiro for you», e
CARICAMENTO o LOADING secondo la lingua scelta nel porter.
L'immagine è dentro il .nro (nx_espera). Stessa dimensione in byte, così
il motore la decodifica senza essere ricompilato.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

PNG_LEN = 21405
APP_VERSION = "0.7.6"
CREDIT = "made by zephiro for you"


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


def _tint(logo, color: tuple[int, int, int, int]):
    mark = logo.convert("RGBA")
    pixels = mark.load()
    for y in range(mark.height):
        for x in range(mark.width):
            _, _, _, alpha = pixels[x, y]
            pixels[x, y] = (*color[:3], alpha)
    return mark


def _paste_center(image, logo, y: int) -> None:
    image.paste(logo, ((image.width - logo.width) // 2, y), logo)


def render_loading_png(title: str, icon=None, app_version: str = APP_VERSION, lang: str = "en") -> bytes:
    from PIL import Image, ImageDraw
    del icon, app_version
    image = Image.new("RGBA", (640, 400), (10, 20, 40, 255))
    draw = ImageDraw.Draw(image)
    assets = Path(__file__).resolve().parent / "assets"
    mark_path = assets / "logo-mark.png"
    line_path = assets / "logo-line.png"
    cursor = 78
    if mark_path.is_file():
        logo = Image.open(mark_path)
        side = 108
        logo = logo.resize((side, side), Image.Resampling.LANCZOS)
        logo = _tint(logo, (197, 228, 255, 255))
        _paste_center(image, logo, cursor)
        cursor += side + 16
    if line_path.is_file():
        line = Image.open(line_path)
        width = 280
        height = max(int(line.height * width / max(line.width, 1)), 1)
        line = line.resize((width, height), Image.Resampling.LANCZOS)
        line = _tint(line, (234, 241, 255, 255))
        _paste_center(image, line, cursor)
        cursor += height + 14
    _center(draw, CREDIT, cursor, 18, (143, 163, 199, 255), False)
    loading = "CARICAMENTO" if lang == "it" else "LOADING"
    _center(draw, loading, cursor + 36, 28, (234, 241, 255, 255), True)
    if title:
        _center(draw, title, 360, 16, (143, 163, 199, 255), False)
    raw = _png_bytes(image)
    if len(raw) > PNG_LEN:
        flat = image.convert("P", palette=Image.Palette.ADAPTIVE, colors=32).convert("RGBA")
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
