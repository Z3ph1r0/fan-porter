"""NSP opzionale. Solo Windows, solo se i tool sono già sul PC.

Il percorso normale resta il .nro. I dati del gioco restano in SD:/switch/<slug>/.
Questo modulo non scarica hacbrewpack, non chiede prod.keys e non le copia.
"""

from __future__ import annotations

import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Optional

from engine import PrepareError, patch_nso_archive, rewrite_nacp
from i18n import tr


def nsp_line(lang: str = "en") -> str:
    if sys.platform != "win32":
        return tr(lang, "nsp_mac")
    missing = missing_tools()
    if missing:
        return tr(lang, "nsp_missing").format(tools=", ".join(missing))
    keys = find_keys()
    if keys is None:
        return tr(lang, "nsp_no_keys")
    return tr(lang, "nsp_ready")


def missing_tools(release: Optional[Path] = None) -> list:
    found = _tool_map(release)
    needed = ("npdmtool.exe", "nacptool.exe", "hacbrewpack.exe")
    return [name for name in needed if name not in found]


def find_keys() -> Optional[Path]:
    home = Path.home()
    appdata = Path(os.environ.get("APPDATA", str(home)))
    for path in (
        home / ".switch" / "prod.keys",
        appdata / "Ryujinx" / "system" / "prod.keys",
    ):
        if path.is_file():
            return path
    return None


def visible_tool_line(line: str) -> bool:
    text = line.strip()
    if not text:
        return False
    if "Failed to match key" in text or "field not present" in text:
        return False
    if text.startswith((
        "Writing ", "Calculating ", "Encrypting ", "Getting ",
        "Renaming ", "Visiting ", "===> ", "---> ",
    )):
        return False
    return True


def _tool_map(release: Optional[Path]) -> dict:
    roots = []
    here = Path(__file__).resolve().parent
    roots.append(here / "tools")
    roots.append(here.parent / "tools")
    if release is not None:
        roots.append(release / "tools")
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent / "tools")
    found = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.iterdir():
            if path.is_file():
                found.setdefault(path.name.lower(), path)
    mapped = {}
    for name in ("npdmtool.exe", "nacptool.exe", "hacbrewpack.exe"):
        path = found.get(name.lower())
        if path:
            mapped[name] = path
    return mapped


def _ascii(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text or "")
    chars = []
    for char in decomposed:
        if unicodedata.category(char) == "Mn":
            continue
        chars.append(char if 32 <= ord(char) <= 126 else " ")
    cleaned = re.sub(r"\s+", " ", "".join(chars)).strip()
    return cleaned or "Fan Porter"


def _run(exe: Path, args: list, folder: Path, log) -> int:
    out = folder / (exe.stem + ".out")
    err = folder / (exe.stem + ".err")
    with out.open("w", encoding="utf-8", errors="replace") as stdout, err.open(
        "w", encoding="utf-8", errors="replace"
    ) as stderr:
        result = subprocess.run(
            [str(exe), *args],
            cwd=str(folder),
            stdout=stdout,
            stderr=stderr,
            check=False,
        )
    lines = []
    for path in (out, err):
        if path.is_file():
            lines.extend(path.read_text(encoding="utf-8", errors="replace").splitlines())
            path.unlink()
    for line in lines:
        if visible_tool_line(line) and log:
            log("       " + line.strip())
    return result.returncode


def create_nsp(info, release: Path, output: Path, icon: Path, log=None) -> Path:
    if sys.platform != "win32":
        raise PrepareError(nsp_line())
    tools = _tool_map(release)
    missing = [name for name in ("npdmtool.exe", "nacptool.exe", "hacbrewpack.exe") if name not in tools]
    main = release / "motor" / "main"
    npdm_base = release / "motor" / "npdm.json"
    for path, label in ((main, "motor/main"), (npdm_base, "motor/npdm.json"), (icon, "icona")):
        if not path.is_file():
            missing.append(label)
    if missing:
        raise PrepareError(
            "NSP non creato. Mancano: " + ", ".join(missing) + ". Non scarico questi programmi."
        )
    keys = find_keys()
    if keys is None:
        raise PrepareError(
            "Senza prod.keys non firmo un NSP: resta il .nro, dal menu homebrew. "
            "Le chiavi escono dalla tua console con Lockpick_RCM e si mettono in .switch."
        )

    slug = re.sub(r"[^A-Za-z0-9]", "", info.slug)[:15] or "rgss"
    with tempfile.TemporaryDirectory(prefix="rgss-nsp-") as raw:
        tmp = Path(raw)
        for name in ("exefs", "control", "romfs", "nsp", "nca", "temp"):
            (tmp / name).mkdir()
        if log:
            log("     Il motore dell'NSP cerca data.zip, la stessa cartella dell'NRO.")
        (tmp / "exefs" / "main").write_bytes(patch_nso_archive(main.read_bytes()))
        spec = json.loads(npdm_base.read_text(encoding="utf-8"))
        spec["name"] = slug
        spec["title_id"] = "0x" + info.titleid
        spec["title_id_range_min"] = "0x" + info.titleid
        spec["title_id_range_max"] = "0x" + info.titleid
        spec_path = tmp / "npdm.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        code = _run(tools["npdmtool.exe"], [str(spec_path), str(tmp / "exefs" / "main.npdm")], tmp, log)
        if code != 0:
            raise PrepareError(f"npdmtool ha restituito {code}.")
        nacp_path = tmp / "control" / "control.nacp"
        code = _run(
            tools["nacptool.exe"],
            ["--create", _ascii(info.name), _ascii(info.author), info.version or "1.0", str(nacp_path), "--titleid=" + info.titleid],
            tmp,
            log,
        )
        if code != 0 or not nacp_path.is_file():
            raise PrepareError(f"nacptool ha restituito {code}.")
        nacp = bytearray(nacp_path.read_bytes())
        placed = struct.unpack_from("<Q", nacp, 0x3078)[0]
        if f"{placed:016X}" != info.titleid.upper():
            raise PrepareError("nacptool non ha scritto il title id richiesto.")
        rewrite_nacp(nacp, info.name, info.author, info.version or "1.0")
        nacp_path.write_bytes(nacp)
        for language in ("AmericanEnglish", "Spanish", "LatinAmericanSpanish"):
            (tmp / "control" / f"icon_{language}.dat").write_bytes(icon.read_bytes())
        (tmp / "romfs" / "juego.txt").write_bytes(("sdmc:/switch/" + info.slug + "\n").encode("utf-8"))
        if log:
            log("     hacbrewpack firma il NSP con le chiavi già sul PC. Non le copio.")
        code = _run(
            tools["hacbrewpack.exe"],
            [
                "-k", str(keys),
                "--exefsdir", str(tmp / "exefs"),
                "--controldir", str(tmp / "control"),
                "--romfsdir", str(tmp / "romfs"),
                "--nspdir", str(tmp / "nsp"),
                "--ncadir", str(tmp / "nca"),
                "--tempdir", str(tmp / "temp"),
                "--nologo",
            ],
            tmp,
            log,
        )
        if code != 0:
            raise PrepareError(f"hacbrewpack ha restituito {code}.")
        made = list((tmp / "nsp").glob("*.nsp"))
        if not made:
            raise PrepareError("hacbrewpack non ha lasciato un NSP.")
        final = output.expanduser().resolve() / f"{info.slug}.nsp"
        final.write_bytes(made[0].read_bytes())
        return final
