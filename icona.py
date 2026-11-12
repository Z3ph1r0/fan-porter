"""Icona dentro l'eseguibile Windows del gioco (Game.exe)."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Optional


def jpeg_icon(image) -> bytes:
    """JPEG 256×256, il formato che il menu homebrew mostra accanto al nome."""
    import io
    from PIL import Image
    mark = image.convert("RGBA").resize((256, 256), Image.Resampling.LANCZOS)
    sheet = Image.new("RGB", (256, 256), (11, 16, 32))
    sheet.paste(mark, mask=mark.split()[-1])
    out = io.BytesIO()
    sheet.save(out, format="JPEG", quality=85)
    return out.getvalue()


def exe_icon(folder: Path):
    """La icona più grande di Game.exe, oppure di un altro .exe nella cartella."""
    names = []
    direct = folder / "Game.exe"
    if direct.is_file():
        names.append(direct)
    for path in sorted(folder.glob("*.exe")):
        if path.name.lower() in ("mkxp-z.exe", "game.exe"):
            continue
        names.append(path)
    for path in names:
        try:
            image = _from_exe(path)
        except Exception:
            continue
        if image is not None:
            return image
    return None


def _from_exe(path: Path):
    data = path.read_bytes()
    if len(data) < 0x40 or data[:2] != b"MZ":
        return None
    lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if lfanew <= 0 or lfanew + 24 > len(data) or data[lfanew:lfanew + 4] != b"PE\x00\x00":
        return None
    coff = lfanew + 4
    _machine, sections, _stamp, _sym, _nsym, opt_size, _flags = struct.unpack_from("<HHIIIHH", data, coff)
    optional = coff + 20
    if optional + 2 > len(data):
        return None
    magic = struct.unpack_from("<H", data, optional)[0]
    if magic == 0x20B:
        number_at = optional + 108
        directory = optional + 112
    elif magic == 0x10B:
        number_at = optional + 92
        directory = optional + 96
    else:
        return None
    if number_at + 4 > len(data):
        return None
    count = struct.unpack_from("<I", data, number_at)[0]
    if count < 3 or directory + 24 > len(data):
        return None
    resource_rva, _resource_size = struct.unpack_from("<II", data, directory + 16)
    if resource_rva == 0:
        return None
    table = optional + opt_size
    mapped = []
    for _index in range(sections):
        if table + 40 > len(data):
            break
        _name, virtual, address, raw_size, raw = struct.unpack_from("<8sIIII", data, table)
        mapped.append((address, raw, max(virtual, raw_size)))
        table += 40

    def locate(rva: int) -> Optional[int]:
        for address, raw, size in mapped:
            if address <= rva < address + size:
                return raw + (rva - address)
        return None

    root = locate(resource_rva)
    if root is None:
        return None

    def directory_at(offset: int):
        named, ids = struct.unpack_from("<HH", data, offset + 12)
        entries = []
        cursor = offset + 16
        for _index in range(named + ids):
            if cursor + 8 > len(data):
                break
            key, value = struct.unpack_from("<II", data, cursor)
            entries.append((key, value))
            cursor += 8
        return entries

    def child(entry: int) -> tuple:
        return bool(entry & 0x80000000), entry & 0x7FFFFFFF

    def walk(offset: int, depth: int, wanted: Optional[int]):
        found = []
        for key, entry in directory_at(offset):
            is_dir, relative = child(entry)
            ident = key if not (key & 0x80000000) else None
            if wanted is not None and depth == 0 and ident != wanted:
                continue
            point = root + relative
            if is_dir:
                found.extend(walk(point, depth + 1, None))
            elif point + 16 <= len(data):
                data_rva, size = struct.unpack_from("<II", data, point)
                file_off = locate(data_rva)
                if file_off is not None and size and file_off + size <= len(data):
                    found.append((ident, data[file_off:file_off + size]))
        return found

    groups = walk(root, 0, 14)
    icons = walk(root, 0, 3)
    if not icons:
        return None
    chosen = _best(groups, icons)
    if chosen is None:
        return None
    return _decode(chosen)


def _best(groups: list, icons: list) -> Optional[bytes]:
    by_id = {}
    for ident, blob in icons:
        if ident is not None:
            by_id.setdefault(ident, blob)
    ranked = []
    for _ident, group in groups:
        if len(group) < 6:
            continue
        count = struct.unpack_from("<H", group, 4)[0]
        cursor = 6
        for _index in range(count):
            if cursor + 14 > len(group):
                break
            width, height, _colors, _reserved, _planes, bits, _nbytes, icon_id = struct.unpack_from(
                "<BBBBHHIH", group, cursor
            )
            cursor += 14
            blob = by_id.get(icon_id)
            if blob is None:
                continue
            side = width or 256
            tall = height or 256
            ranked.append((side * tall, bits, blob))
    if ranked:
        ranked.sort(key=lambda item: (item[0], item[1]))
        return ranked[-1][2]
    return max(icons, key=lambda item: len(item[1]))[1]


def _decode(blob: bytes):
    from PIL import Image
    import io
    if blob.startswith(b"\x89PNG\r\n\x1a\n"):
        return Image.open(io.BytesIO(blob)).convert("RGBA")
    if len(blob) < 40:
        return None
    header = struct.unpack_from("<I", blob, 0)[0]
    if header < 40 or header > 128 or len(blob) < header:
        return None
    width, height, _planes, bits = struct.unpack_from("<iiHH", blob, 4)
    if width <= 0 or width > 1024 or bits not in (24, 32):
        return None
    xor_height = height // 2 if height == width * 2 else height
    if xor_height <= 0 or xor_height > 1024:
        return None
    pixels = blob[header:header + width * xor_height * (bits // 8)]
    if len(pixels) < width * xor_height * (bits // 8):
        return None
    if bits == 32:
        image = Image.frombytes("RGBA", (width, xor_height), pixels, "raw", "BGRA")
    else:
        row = ((width * 3 + 3) // 4) * 4
        raw = bytearray()
        for y in range(xor_height):
            start = y * row
            raw.extend(pixels[start:start + width * 3])
        image = Image.frombytes("RGB", (width, xor_height), bytes(raw), "raw", "BGR")
    return image.transpose(Image.Transpose.FLIP_TOP_BOTTOM).convert("RGBA")
