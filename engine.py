"""Prepara un fan game RPG Maker per Fan Porter.

Each game lands in switch/<slug>/<slug>.nro, next to data.zip.
Il file .nro è il motore rgss-switch, con nome e icona del gioco.
Non c'è un menu launcher sulla console.
"""

from __future__ import annotations

import datetime
import fnmatch
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import time
import unicodedata
import zlib
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

RESOURCE_DIRS = ("Data", "Graphics", "Audio", "Fonts", "Movies")
EXCLUDE_DEFAULT = ("PBS", "DataBackup", "DataExport", "dist", "Credits")
SKIP_PATTERNS = (
    "*.exe", "*.dll", "*.pdf", "*.lnk", "*.rar", "*.zip", "*.7z",
    "thumbs.db", "desktop.ini", "*.parcial", ".nomedia", ".ds_store",
)
GAME_JSON_KEYS = {
    "windowTitle", "defScreenW", "defScreenH", "rgssVersion",
    "SESourceCount", "BGMTrackCount",
    "midiSoundFont", "midiChorus", "midiReverb",
    "subImageFix", "enableBlitting", "maxTextureSize",
    "bindingNames", "inputRepeatStart", "inputRepeatDelay",
    "patches", "execName", "solidFonts", "fontSub", "useScriptNames",
    "JITEnable", "JITMaxCache", "JITMinCalls",
}
FALLBACK_SHIMS = ("nx-compat.rb", "nx-teclado.rb", "nx-rutas.rb")
RGSSAD_KEY = bytes((0x52, 0x47, 0x53, 0x53, 0x41, 0x44, 0x00, 0x01))
PORT_AUTHOR = "Zephiro"
APP_VERSION = "0.7.5"
MOTOR_VERSION = "0.2.4"
# rgss-switch 0.2.4 mounts this exact filename. We rewrite that string to data.zip.
MOTOR_ARCHIVE = b"datos.zip"
ARCHIVE_NAME = "data.zip"
# The Fan D Porter build of the motor mounts data.zip by itself and keeps
# datos.zip as a fallback: its binary is left as it is.
FANPORTER_MOTOR_MARK = b"fanporter_overlay"
# Nomi letti in mkxp.base.json del motore 0.2.4. Il file sulla scheda è JSON puro:
# i commenti // stanno solo nella base, e l'empaquetador li toglie.
GRAFICA = {
    "intera": {"smoothScaling": False, "integerScalingActive": True, "lanczos3Scaling": False},
    "nitida": {"smoothScaling": False, "integerScalingActive": False, "lanczos3Scaling": False},
    "morbida": {"smoothScaling": True, "integerScalingActive": False, "lanczos3Scaling": False},
    "lanczos": {"smoothScaling": True, "integerScalingActive": False, "lanczos3Scaling": True},
}
MOTOR_URL = (
    "https://github.com/randygil/rgss-switch/releases/download/"
    "v0.2.4/rgss-switch-0.2.4.zip"
)
# zipfile di Python rifiuta uno zip classico oltre 2 GB (ZIP64_LIMIT), anche se il formato arriva a 4.
ZIP_LIMIT_BYTES = (1 << 31) - (1 << 20)
ZIP_LIMIT_ENTRIES = 65534

Log = Callable[[str], None]
Progress = Callable[[int, str], None]


def _tick(progress: Optional[Progress], percent: int, step: str = "progress_working") -> None:
    if progress:
        progress(max(0, min(100, int(percent))), step)


class PrepareError(Exception):
    pass


def _log(log: Optional[Log], message: str) -> None:
    if log:
        log(message)


def json5_loads(text: str):
    """JSON5 ridotto: commenti // e /* */, virgole finali, poi json standard."""
    out = []
    i = 0
    n = len(text)
    in_str = False
    esc = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            i += 2
            while i < n and text[i] not in "\r\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i = min(n, i + 2)
            continue
        out.append(c)
        i += 1

    raw = "".join(out)
    cleaned = []
    i = 0
    n = len(raw)
    in_str = False
    esc = False
    while i < n:
        c = raw[i]
        if in_str:
            cleaned.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            cleaned.append(c)
            i += 1
            continue
        if c == ",":
            j = i + 1
            while j < n and raw[j] in " \t\r\n":
                j += 1
            if j < n and raw[j] in "}]":
                i += 1
                continue
        cleaned.append(c)
        i += 1
    return json.loads("".join(cleaned))


def read_text(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


def load_json_file(path: Path):
    return json5_loads(read_text(path))


def slugify(title: str) -> str:
    if not title:
        return ""
    decomposed = unicodedata.normalize("NFD", title)
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    lowered = stripped.lower()
    dashed = re.sub(r"[^a-z0-9]+", "-", lowered)
    return dashed.strip("-")


def title_id(slug: str) -> str:
    digest = hashlib.sha1(slug.encode("utf-8")).hexdigest()
    return ("05" + digest[:14]).upper()


def skipped_name(name: str) -> bool:
    low = name.lower()
    return any(fnmatch.fnmatch(low, pattern) for pattern in SKIP_PATTERNS)


def parse_ini(path: Path) -> dict:
    sections: dict = {}
    current = ""
    for line in read_text(path).splitlines():
        item = line.strip()
        if not item or item.startswith(";") or item.startswith("#"):
            continue
        if item.startswith("[") and item.endswith("]"):
            current = item[1:-1]
            sections.setdefault(current, {})
            continue
        eq = item.find("=")
        if eq < 1 or not current:
            continue
        sections.setdefault(current, {})
        sections[current][item[:eq].strip()] = item[eq + 1 :].strip()
    return sections


def choose_ini(game: Path) -> Optional[str]:
    if (game / "Game.ini").is_file():
        return "Game.ini"
    exe_stems = {p.stem for p in game.glob("*.exe") if p.is_file()}
    ini_files = sorted(p for p in game.glob("*.ini") if p.is_file())
    for ini in ini_files:
        if ini.stem in exe_stems and "Game" in parse_ini(ini):
            return ini.name
    for ini in ini_files:
        if ini.name.lower() == "editor.ini":
            continue
        sections = parse_ini(ini)
        if sections.get("Game", {}).get("Title"):
            return ini.name
    return None


def _exe_contains(path: Path, needles: Iterable[str]) -> dict:
    blob = path.read_bytes()
    return {needle: needle.encode("ascii") in blob for needle in needles}


def detect_family(game: Path, exe_stem: str) -> str:
    names = [p.name.lower() for p in game.iterdir() if p.is_file()]
    # Una DLL Ruby 3 dice il linguaggio dei script. Reminiscencia ha anche
    # RGSS102: è il lettore vecchio lasciato nella cartella, non i suoi script.
    # Lo strato 1.8 su quei script li rompe appena si preme Inizia.
    ruby3 = any(fnmatch.fnmatch(name, "x64-msvcrt-ruby*.dll") for name in names)
    if ruby3:
        return "ruby31"
    # RGSS102 senza Ruby 3 è un gioco 1.8 (Z, Vitro). Senza lo strato non parte.
    if any(fnmatch.fnmatch(name, "rgss102*.dll") for name in names):
        return "ruby18"
    if any(fnmatch.fnmatch(name, "msvcrt-ruby*.dll") for name in names):
        return "ruby18"
    exe = None
    for candidate in (f"{exe_stem}.exe", "Game.exe"):
        path = game / candidate
        if path.is_file():
            exe = path
            break
    if exe is None:
        exes = sorted((p for p in game.glob("*.exe") if p.is_file()), key=lambda p: p.stat().st_size, reverse=True)
        exe = exes[0] if exes else None
    if exe is None:
        return "sconosciuto"
    size = exe.stat().st_size
    has_rgss = any(fnmatch.fnmatch(name, "rgss10*.dll") for name in names)
    if size < 1_000_000:
        return "rgss1" if has_rgss else "sconosciuto"
    found = _exe_contains(exe, ("/lib/ruby/1.8", "mkxp-z.exe"))
    if found["/lib/ruby/1.8"]:
        return "ruby18"
    if found["mkxp-z.exe"]:
        return "ruby31"
    return "sconosciuto"


def family_warning(family: str) -> Optional[str]:
    if family == "ruby18":
        return (
            "This game ships Ruby 1.8. The Switch engine is Ruby 3.1.7, "
            "so it may not boot. It is prepared anyway."
        )
    if family == "rgss1":
        return (
            "This game is original RPG Maker XP (Ruby 1.8.1). "
            "The Switch engine is Ruby 3.1.7, so it may not boot. It is prepared anyway."
        )
    if family == "sconosciuto":
        return "The PC interpreter could not be identified. It is prepared anyway."
    return None


def _get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


# Giochi verificati sulla Switch. La famiglia è quella degli SCRIPT, e batte
# le DLL rimaste nella cartella vergine.
# ruby31: non si precarica nx-ruby18. Quello strato riscrive i comandi 1.8 e
# chiude l'avvio sui giochi già scritti per Ruby 3.
# ruby18: nx-ruby18 va in preload, prima di nx-porter (StringInput, lettere,
# Missions). nx-porter.rb è sempre l'ultimo e vale per tutti.
#
# nova           ruby31  tasti essentials. preload.rb del gioco, se c'è.
# relict         ruby31  tasti essentials. load_data a due argomenti e
#                        File.open sul contenitore stanno in nx-porter.
# reminiscencia  ruby31  anche se in cartella c'è RGSS102. Tasti essentials.
#                        Win32API, Marshal sullo StringInput e i PNG con
#                        neverload stanno in nx-porter. Mai nx-ruby18.
# vitro          ruby18  tasti essentials. Solo RGSS102, niente DLL Ruby 3.
# pokemon-z      ruby18  tasti rgss: il gioco chiede Input::C/B/A, non le lettere.
# realidea       ruby18  anche se in cartella c'è x64-msvcrt-ruby300. Tasti
#                        rgss. Missions (il C del menu non apre da solo la
#                        scheda) sta in nx-ruby18.
# anil           ruby31  tasti essentials. Gli shim del profilo (tira, centro,
#                        bolas, pokeapi, actualiza, nube, datos, fotogramas,
#                        zoom, tilemap) restano suoi. Il vsync delle opzioni
#                        riscrive mkxp.json senza virgole valide: nx-porter lo
#                        sistema prima della chiusura. 30 e 45 fps richiedono
#                        vsync e syncToRefreshrate spenti, e un riavvio.
# rejuvenation   ruby31  tasti essentials. Non è Reborn: niente nx-reborn e
#                        niente rubyLoadpath su stdlib/gems. Discord è un
#                        modulo finto in nx-porter (discord.so non si carica e
#                        NotImplementedError non è uno StandardError). Il
#                        controllo versione in rete non parte (Thread.new qui
#                        chiude il processo). Save Data/.portable evita che il
#                        nuovo gioco scandisca la cartella padre della scheda.
INPUT_PROFILES = (
    {"id": "pokemon-z", "title": r"pokemon\s*z\b", "folder": r"pokemon\s*z", "tasti": "rgss", "family": "ruby18"},
    {"id": "realidea", "title": r"realidea", "folder": r"realidea", "tasti": "rgss", "family": "ruby18"},
    {"id": "vitro", "title": r"gs\s*vitro|\bvitro\b", "folder": r"vitro", "tasti": "essentials", "family": "ruby18"},
    {"id": "nova", "title": r"^nova$", "folder": r"\bnova\b", "tasti": "essentials", "family": "ruby31"},
    {"id": "relict", "title": r"relict", "folder": r"relict", "tasti": "essentials", "family": "ruby31"},
    {"id": "reminiscencia", "title": r"reminiscen", "folder": r"reminiscen", "tasti": "essentials", "family": "ruby31"},
    {"id": "pokemon-anil", "title": r"a[nñ]il", "folder": r"anil", "tasti": "essentials", "family": "ruby31"},
    {"id": "pokemon-rejuvenation", "title": r"rejuvenation", "folder": r"rejuvenation", "tasti": "essentials", "family": "ruby31"},
    {"id": "pokemon-opalo", "title": r"opalo|ópalo", "folder": r"opalo", "tasti": "essentials", "family": "ruby18"},
    {"id": "xenoverse", "title": r"xenoverse", "folder": r"xenoverse", "tasti": "essentials", "family": "ruby18"},
)


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn").lower()


def match_input_profile(game: Path, title: str) -> Optional[dict]:
    title_fold = _fold(title)
    folder_fold = _fold(game.name)
    for spec in INPUT_PROFILES:
        if spec.get("title") and title_fold and re.search(spec["title"], title_fold, re.I):
            return spec
        if spec.get("folder") and re.search(spec["folder"], folder_fold, re.I):
            return spec
    return None


def _script_looks_essentials(text: str) -> bool:
    return "triggerex?" in text and (
        "DEFAULT_INPUT_MAPPINGS" in text or "input_to_keys" in text
    )


def _script_looks_rgss(text: str) -> bool:
    return "GetAsyncKeyState" in text and "buttonToKey" in text


def _iter_loose_scripts(game: Path):
    roots = [game / "Data" / "Scripts", game / "Data" / "export"]
    seen = 0
    visited = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.rb"):
            key = str(path)
            if key in visited:
                continue
            visited.add(key)
            seen += 1
            if seen > 80:
                return
            try:
                if path.stat().st_size > 400_000:
                    continue
                yield path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue


def _iter_rxdata_scripts(game: Path):
    """I Scripts.rxdata sono Marshal Ruby, non Python: si sgonfiano i pezzi zlib."""
    rx = game / "Data" / "Scripts.rxdata"
    if not rx.is_file() or rx.stat().st_size > 80 * 1024 * 1024:
        return
    blob = rx.read_bytes()
    i = 0
    seen = 0
    while seen < 80:
        j = blob.find(b"\x78", i)
        if j < 0 or j + 1 >= len(blob):
            break
        if blob[j + 1] not in (0x01, 0x5E, 0x9C, 0xDA):
            i = j + 1
            continue
        i = j + 1
        try:
            out = zlib.decompressobj().decompress(blob[j:], 400_000)
        except zlib.error:
            continue
        if len(out) < 40:
            continue
        seen += 1
        yield out.decode("utf-8", "replace")


def scripts_use_essentials_keys(game: Path) -> bool:
    return detect_script_tasti(game) == "essentials"


def detect_script_tasti(game: Path) -> Optional[str]:
    """Legge gli script del gioco, anche se stanno solo nello rxdata."""
    essentials = False
    rgss = False
    for text in _iter_loose_scripts(game):
        if _script_looks_essentials(text):
            essentials = True
            break
        if _script_looks_rgss(text):
            rgss = True
    if not essentials:
        for text in _iter_rxdata_scripts(game):
            if _script_looks_essentials(text):
                essentials = True
                break
            if _script_looks_rgss(text):
                rgss = True
    if essentials:
        return "essentials"
    if rgss:
        return "rgss"
    return None


def detect_tasti(game: Path, title: str) -> tuple:
    """Profilo comandi: essentials (lettere) o rgss (numeri del motore)."""
    spec = match_input_profile(game, title)
    if spec:
        return spec["id"], spec["tasti"]
    kind = detect_script_tasti(game)
    if kind == "essentials":
        return "essentials", "essentials"
    if kind == "rgss":
        return "rgss", "rgss"
    return "rgss", "rgss"


@dataclass
class GameInfo:
    folder: Path
    ini_name: Optional[str]
    title: str
    slug: str
    name: str
    author: str
    profile_name: str
    profile_dir: Optional[Path]
    profile: dict
    family: str
    family_seen: str
    titleid: str
    exe_stem: str
    archive_name: Optional[str]
    warnings: list = field(default_factory=list)
    version: str = "1.0"
    icon_path: Optional[Path] = None
    input_profile: str = "rgss"
    tasti: str = "rgss"


def load_profiles(release: Path) -> list:
    root = release / "juegos"
    found = []
    if not root.is_dir():
        return found
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        profile_path = directory / "perfil.json"
        if not profile_path.is_file():
            continue
        try:
            profile = load_json_file(profile_path)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        found.append((directory.name, directory, profile))
    return found


def match_profile(game: Path, title: str, profiles: list):
    best = None
    best_score = 0
    for name, directory, profile in profiles:
        if name == "generico":
            continue
        detect = _get(profile, "detectar") or {}
        title_re = _get(detect, "titulo") or ""
        files = _as_list(_get(detect, "ficheros"))
        by_title = bool(title_re and title and re.search(title_re, title))
        by_files = False
        if files:
            by_files = all((game / f.replace("\\", "/")).exists() for f in files)
        score = 0
        if by_title and by_files:
            score = 3
        elif by_title:
            score = 2
        elif by_files and not (title_re and title):
            # Rejuvenation ha Scripts/ScriptLoader.rb come Reborn, ma non è Reborn.
            # Un file in comune non basta se il titolo è un altro gioco.
            score = 1
        if score > best_score:
            best_score = score
            best = (name, directory, profile)
    if best:
        return best
    for name, directory, profile in profiles:
        if name == "generico":
            return (name, directory, profile)
    return None


def _archive_name(game: Path) -> Optional[str]:
    archives = [
        p.name for p in game.iterdir()
        if p.is_file() and re.search(r"\.rgss(?:ad|[23]a)$", p.name, re.I)
    ]
    rgssad = [name for name in archives if name.lower().endswith(".rgssad")]
    if rgssad:
        return sorted(rgssad)[0]
    return sorted(archives)[0] if archives else None


def game_version(*texts: str) -> str:
    """Versione scritta nel nome della cartella o nel titolo, per esempio 2.13."""
    for text in texts:
        if not text:
            continue
        match = re.search(r"(?<!\d)(\d+\.\d+(?:\.\d+)?)", text)
        if match:
            return match.group(1)[:15]
    return "1.0"


def detect_game(game: Path, release: Path) -> GameInfo:
    game = game.expanduser().resolve()
    release = release.expanduser().resolve()
    ini_name = choose_ini(game)
    title = ""
    exe_stem = "Game"
    if ini_name:
        sections = parse_ini(game / ini_name)
        title = sections.get("Game", {}).get("Title", "")
        exe_stem = Path(ini_name).stem
    matched = match_profile(game, title, load_profiles(release))
    profile = matched[2] if matched else {}
    profile_name = matched[0] if matched else "(nessuno)"
    profile_dir = matched[1] if matched else None
    slug = _get(profile, "slug") or slugify(title) or slugify(game.name)
    name = _get(profile, "nombre") or title or slug
    author = PORT_AUTHOR
    version = game_version(game.name, title)
    seen = detect_family(game, exe_stem)
    family = _get(profile, "motor") or seen
    input_spec = match_input_profile(game, title)
    if input_spec and input_spec.get("family"):
        family = input_spec["family"]
    input_profile, tasti = detect_tasti(game, title)
    ident = _get(profile, "titleid") or title_id(slug)
    warnings = []
    # I sei giochi già verificati non vanno spacciati per "forse non parte".
    if not (input_spec and input_spec.get("family")):
        note = family_warning(family)
        if note:
            warnings.append(note)
    return GameInfo(
        folder=game,
        ini_name=ini_name,
        title=title,
        slug=slug,
        name=name,
        author=author,
        profile_name=profile_name,
        profile_dir=profile_dir,
        profile=profile or {},
        family=family,
        family_seen=seen,
        titleid=str(ident),
        exe_stem=exe_stem,
        archive_name=_archive_name(game),
        warnings=warnings,
        version=version,
        input_profile=input_profile,
        tasti=tasti,
    )


def check_game(game: Path) -> Optional[str]:
    if not game.is_dir():
        return "La cartella del gioco non esiste."
    if not choose_ini(game):
        return "Nessun .ini con la sezione [Game]. Non sembra una cartella di RPG Maker."
    has_data = (game / "Data").is_dir() or _archive_name(game) is not None
    if not has_data:
        return "Manca Data/ e manca anche un archivio .rgssad/.rgss2a/.rgss3a."
    if not (game / "Graphics").is_dir() and _archive_name(game) is None:
        return "Manca Graphics/."
    return None


def support_dir() -> Path:
    if sys_platform() == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Fan Porter"
        old = Path.home() / "Library" / "Application Support" / "Fan D Porter"
        if not base.exists() and old.exists():
            base = old
    elif sys_platform() == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home()))) / "Fan Porter"
        old = Path(os.environ.get("APPDATA", str(Path.home()))) / "Fan D Porter"
        if not base.exists() and old.exists():
            base = old
    else:
        base = Path.home() / ".fan-porter"
    base.mkdir(parents=True, exist_ok=True)
    return base


def sys_platform() -> str:
    return sys.platform


def default_output_dir() -> Path:
    desktop = Path.home() / "Desktop"
    if not desktop.is_dir():
        desktop = Path.home()
    path = desktop / "Fan Porter"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_extract(archive: zipfile.ZipFile, dest: Path) -> None:
    root = dest.resolve()
    for info in archive.infolist():
        target = (root / info.filename).resolve()
        if target != root and root not in target.parents:
            raise PrepareError("Lo zip del motore ha un percorso non valido.")
    archive.extractall(root)


def _release_root(extracted: Path) -> Path:
    if (extracted / "motor" / "rgss-switch.nro").is_file():
        return extracted
    for child in extracted.iterdir():
        if child.is_dir() and (child / "motor" / "rgss-switch.nro").is_file():
            return child
    raise PrepareError("Lo zip del motore non contiene motor/rgss-switch.nro.")


def ensure_release(cache: Path, log: Optional[Log] = None, url: str = MOTOR_URL, zip_path: Optional[Path] = None) -> Path:
    """Motore rgss-switch, scaricato una volta e poi riusato."""
    cache.mkdir(parents=True, exist_ok=True)
    marker = cache / "release-path.txt"
    # Seconda riga: l'impronta dello zip da cui viene. Uno zip diverso nel
    # pacchetto (motore nuovo) si estrae di nuovo.
    stamp = _zip_stamp(zip_path) if zip_path is not None else None
    if marker.is_file():
        lines = marker.read_text(encoding="utf-8").splitlines()
        saved = Path(lines[0].strip()) if lines else cache
        saved_stamp = lines[1].strip() if len(lines) > 1 else None
        if check_release(saved) is None and (stamp is None or stamp == saved_stamp):
            _log(log, "Motore già pronto.")
            overlay_known_profiles(saved, log)
            return saved

    if zip_path is None:
        zip_path = cache / "rgss-switch.zip"
        if not zip_path.is_file() or zip_path.stat().st_size < 1_000_000:
            _log(log, "Scarico il motore (una volta sola, circa 17 MB)…")
            partial = zip_path.with_suffix(".zip.parcial")

            def hook(block, block_size, total):
                if total and total > 0 and block % 40 == 0:
                    done = min(100, int(block * block_size * 100 / total))
                    _log(log, f"     {done}%")

            urllib.request.urlretrieve(url, partial, hook)
            partial.replace(zip_path)
            _log(log, "Scaricamento finito.")

    unpacked = cache / "unpacked"
    if unpacked.exists():
        shutil.rmtree(unpacked)
    unpacked.mkdir()
    with zipfile.ZipFile(zip_path) as archive:
        _safe_extract(archive, unpacked)
    root = _release_root(unpacked)
    problem = check_release(root)
    if problem:
        raise PrepareError(problem)
    marker.write_text(f"{root}\n{_zip_stamp(zip_path)}\n", encoding="utf-8")
    overlay_known_profiles(root, log)
    _log(log, "Motore pronto.")
    return root


def overlay_known_profiles(release: Path, log: Optional[Log] = None) -> None:
    """I profili dei giochi verificati stanno nel porter, non nello zip del motore.
    Una riestrazione non li cancella."""
    root = Path(__file__).resolve().parent / "profili"
    if not root.is_dir():
        return
    dest_root = release / "juegos"
    dest_root.mkdir(exist_ok=True)
    count = 0
    for profile in sorted(root.glob("*/perfil.json")):
        dest = dest_root / profile.parent.name
        dest.mkdir(exist_ok=True)
        shutil.copy2(profile, dest / "perfil.json")
        count += 1
    if count:
        _log(log, f"Profili dei giochi verificati: {count}.")


def _zip_stamp(path: Path) -> str:
    digest = hashlib.sha1()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def check_release(release: Path) -> Optional[str]:
    needed = (
        release / "motor" / "rgss-switch.nro",
        release / "mkxp.base.json",
        release / "lib",
        release / "juegos",
    )
    missing = [str(path.relative_to(release)) for path in needed if not path.exists()]
    if missing:
        return "Nella consegna manca: " + ", ".join(missing)
    return None


def _shim_dir(release: Path) -> Optional[Path]:
    for candidate in (release / "shims", release / "runtime" / "shims"):
        if (candidate / "catalogo.json").is_file():
            return candidate
    return None


def resolve_shims(info: GameInfo, release: Path, log: Optional[Log] = None) -> list:
    directory = _shim_dir(release)
    catalog = None
    if directory:
        try:
            catalog = load_json_file(directory / "catalogo.json")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            _log(log, f"     Catalogo shims illeggibile ({exc}); uso l'elenco di riserva.")
    if not catalog:
        rows = []
        for index, filename in enumerate(FALLBACK_SHIMS):
            rows.append({
                "name": filename, "file": filename, "load": "preload",
                "where": "lib", "order": 10 + index * 10, "mkxp": None, "by_family": False,
            })
        if info.family in ("ruby18", "rgss1"):
            rows.append({
                "name": "ruby18", "file": "nx-ruby18.rb", "load": "preload",
                "where": "lib", "order": 40, "mkxp": None, "by_family": True,
            })
        return rows

    table = _get(catalog, "shims") or {}
    requested = _as_list(_get(info.profile, "shims"))
    for name in requested:
        if name not in table:
            _log(log, f"     Il profilo chiede lo shim '{name}', il catalogo non lo ha.")
    rows = []
    for name, spec in table.items():
        families = _as_list(_get(spec, "familias"))
        by_family = bool(families) and info.family in families
        if not (_get(spec, "siempre") or by_family or name in requested):
            continue
        order = _get(spec, "orden")
        if order is None:
            order = 100
        load = _get(spec, "carga") or "preload"
        where = _get(spec, "en") or "shims"
        for index, filename in enumerate(_as_list(_get(spec, "ficheros"))):
            rows.append({
                "name": name,
                "file": filename,
                "load": load,
                "where": where,
                "order": float(order) + index / 100.0,
                "mkxp": _get(spec, "mkxp"),
                "by_family": by_family,
            })
    rows.sort(key=lambda row: row["order"])
    return rows


def _ascii_json(value):
    if isinstance(value, str):
        folded = unicodedata.normalize("NFKD", value)
        return "".join(char for char in folded if ord(char) < 128)
    if isinstance(value, list):
        return [_ascii_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _ascii_json(item) for key, item in value.items()}
    return value


def compose_mkxp(
    info: GameInfo,
    release: Path,
    shims: list,
    log: Optional[Log] = None,
    scala: str = "intera",
    proporzioni: str = "fisse",
) -> str:
    base_path = release / "mkxp.base.json"
    config = dict(load_json_file(base_path))
    taken = []
    own = info.folder / "mkxp.json"
    if own.is_file():
        try:
            game_cfg = load_json_file(own)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            _log(log, f"     mkxp.json del gioco illeggibile ({exc}); si ignora.")
            game_cfg = None
        if isinstance(game_cfg, dict):
            for key, value in game_cfg.items():
                if key not in GAME_JSON_KEYS:
                    continue
                if key == "midiSoundFont" and value:
                    sound = info.folder / str(value).replace("\\", "/")
                    if not sound.is_file():
                        _log(log, f"     midiSoundFont '{value}' non è nella cartella; chiave omessa.")
                        continue
                config[key] = value
                taken.append(key)
    for shim in shims:
        mkxp = shim.get("mkxp") or {}
        if isinstance(mkxp, dict):
            config.update(mkxp)
    profile_mkxp = _get(info.profile, "mkxp") or {}
    if isinstance(profile_mkxp, dict):
        config.update(profile_mkxp)

    preload = []
    postload = []
    for shim in shims:
        if shim["load"] == "require":
            continue
        if shim["where"] == "lib" and shim["by_family"] and not (release / "lib" / shim["file"]).is_file():
            _log(log, f"     Manca lib/{shim['file']} per la famiglia {info.family}.")
            continue
        target = "lib/" + shim["file"]
        if shim["load"] == "postload":
            postload.append(target)
        else:
            preload.append(target)
    for filename in _as_list(_get(info.profile, "preload")):
        preload.append("lib/" + filename)
    if (info.folder / "preload.rb").is_file():
        preload.append("preload.rb")
    preload.append("lib/nx-porter.rb")
    # La famiglia decisa sopra vince sul catalogo: un gioco Ruby 3 non deve
    # mai caricare nx-ruby18, un gioco 1.8 non deve partire senza.
    if info.family in ("ruby18", "rgss1"):
        if "lib/nx-ruby18.rb" not in preload:
            preload.insert(preload.index("lib/nx-porter.rb"), "lib/nx-ruby18.rb")
    else:
        preload = [item for item in preload if not item.endswith("nx-ruby18.rb")]
    config["preloadScript"] = preload
    if postload:
        config["postloadScript"] = postload
        _log(log, "     postloadScript è scritto ma questo motore lo ignora.")

    load_path = ["lib"]
    for extra in _as_list(_get(info.profile, "rubyLoadpath")):
        if extra not in load_path:
            load_path.append(extra)
    config["rubyLoadpath"] = load_path
    if not config.get("windowTitle"):
        config["windowTitle"] = info.title or info.name
    # Il motore indovina la codifica di mkxp.json con uchardet. Un titolo con
    # l'accento (Pokémon) in un file corto lo manda in crash prima di Ruby.
    config = _ascii_json(config)
    apply_grafica(config, scala, proporzioni)
    if taken:
        _log(log, "     dal mkxp del gioco: " + ", ".join(taken))
    return json.dumps(config, ensure_ascii=True, indent=2) + "\n"


def apply_grafica(config: dict, scala: str, proporzioni: str) -> dict:
    """I nomi delle chiavi sono quelli di mkxp.base.json. vsync non si tocca."""
    chosen = GRAFICA.get(scala) or GRAFICA["intera"]
    config.update(chosen)
    config["fixedAspectRatio"] = proporzioni != "libere"
    return config


def _put_cstr(buf: bytearray, offset: int, size: int, text: str) -> None:
    encoded = text.encode("utf-8")
    if len(encoded) >= size:
        raise PrepareError(f"Il testo '{text}' non entra in {size} byte del NACP.")
    buf[offset:offset + size] = b"\x00" * size
    buf[offset:offset + len(encoded)] = encoded


def rewrite_nacp(nacp: bytearray, name: str, author: str, version: str) -> None:
    for index in range(16):
        offset = index * 0x300
        if nacp[offset] == 0 and index not in (0, 5, 6):
            continue
        _put_cstr(nacp, offset, 0x200, name)
        _put_cstr(nacp, offset + 0x200, 0x100, author)
    if version:
        _put_cstr(nacp, 0x3060, 0x10, version[:15])


def _aset_slices(blob: bytes, size: int):
    if len(blob) <= size or blob[size:size + 4] != b"ASET":
        return None, b"", b""
    nacp_off, nacp_sz, rom_off, rom_sz = struct.unpack_from("<QQQQ", blob, size + 0x18)
    icon_off, icon_sz = struct.unpack_from("<QQ", blob, size + 0x08)
    nacp = bytearray(0x4000)
    romfs = b""
    icon = b""
    if nacp_sz == 0x4000 and size + nacp_off + nacp_sz <= len(blob):
        nacp[:] = blob[size + nacp_off:size + nacp_off + 0x4000]
    if rom_sz and size + rom_off + rom_sz <= len(blob):
        romfs = blob[size + rom_off:size + rom_off + rom_sz]
    if icon_sz and size + icon_off + icon_sz <= len(blob):
        icon = blob[size + icon_off:size + icon_off + icon_sz]
    return (nacp, romfs, icon)


def patch_archive_name(blob: bytes) -> bytes:
    """Point the motor at data.zip. The byte length of datos.zip stays the same."""
    if FANPORTER_MOTOR_MARK in blob:
        return blob
    out = bytearray(blob)
    start = 0
    while True:
        index = out.find(MOTOR_ARCHIVE, start)
        if index < 0:
            break
        nxt = out[index + len(MOTOR_ARCHIVE)] if index + len(MOTOR_ARCHIVE) < len(out) else 0
        if nxt == 0:
            out[index:index + len(MOTOR_ARCHIVE)] = b"data.zip\x00"
        else:
            out[index:index + len(MOTOR_ARCHIVE)] = b"data.zip "
        start = index + len(MOTOR_ARCHIVE)
    return bytes(out)


def lz4_decompress(src: bytes, size: int) -> bytes:
    """LZ4 block, the kind an NSO stores. size is the decompressed length."""
    out = bytearray()
    index = 0
    while len(out) < size:
        token = src[index]
        index += 1
        literals = token >> 4
        if literals == 15:
            while True:
                extra = src[index]
                index += 1
                literals += extra
                if extra != 255:
                    break
        out += src[index:index + literals]
        index += literals
        if len(out) >= size:
            break
        offset = src[index] | (src[index + 1] << 8)
        index += 2
        match = (token & 0x0F) + 4
        if (token & 0x0F) == 15:
            while True:
                extra = src[index]
                index += 1
                match += extra
                if extra != 255:
                    break
        start = len(out) - offset
        for step in range(match):
            out.append(out[start + step])
    if len(out) != size:
        raise PrepareError("Il motore NSP non si decomprime: lunghezza diversa da quella dichiarata.")
    return bytes(out)


def _lz4_emit(out: bytearray, src: bytes, lit_start: int, lit_end: int, match_len: int, offset: int) -> None:
    literals = lit_end - lit_start
    token_at = len(out)
    out.append(0)
    if literals >= 15:
        out[token_at] |= 0xF0
        left = literals - 15
        while left >= 255:
            out.append(255)
            left -= 255
        out.append(left)
    else:
        out[token_at] |= literals << 4
    out += src[lit_start:lit_end]
    if match_len <= 0:
        return
    out.append(offset & 0xFF)
    out.append((offset >> 8) & 0xFF)
    code = match_len - 4
    if code >= 15:
        out[token_at] |= 0x0F
        left = code - 15
        while left >= 255:
            out.append(255)
            left -= 255
        out.append(left)
    else:
        out[token_at] |= code


def lz4_compress(data: bytes) -> bytes:
    """LZ4 block. Correct, not the smallest: enough to put a patched NSO back together."""
    src = data
    size = len(src)
    out = bytearray()
    if size < 13:
        _lz4_emit(out, src, 0, size, 0, 0)
        return bytes(out)
    table: dict[int, int] = {}
    anchor = 0
    pos = 0
    limit = size - 12
    while pos < limit:
        value = int.from_bytes(src[pos:pos + 4], "little")
        slot = (value * 2654435761) & 0xFFFF
        ref = table.get(slot)
        table[slot] = pos
        offset = 0 if ref is None else pos - ref
        if ref is None or offset <= 0 or offset >= 65536 or src[ref:ref + 4] != src[pos:pos + 4]:
            pos += 1
            continue
        match_len = 4
        max_len = size - 5 - pos
        while match_len < max_len and src[ref + match_len] == src[pos + match_len]:
            match_len += 1
        _lz4_emit(out, src, anchor, pos, match_len, offset)
        pos += match_len
        anchor = pos
    _lz4_emit(out, src, anchor, size, 0, 0)
    return bytes(out)


def patch_nso_archive(blob: bytes) -> bytes:
    """The NSP's main is a compressed NSO. It still says datos.zip; the card has data.zip."""
    if blob[:4] != b"NSO0":
        return patch_archive_name(blob)
    flags = struct.unpack_from("<I", blob, 0x0C)[0]
    layout = (
        (0x10, 0x60, 0xA0, 1, 8),
        (0x20, 0x64, 0xC0, 2, 16),
        (0x30, 0x68, 0xE0, 4, 32),
    )
    pieces = []
    cursor = 0x100
    out = bytearray(blob[:0x100])
    for file_at, size_at, hash_at, compress_bit, hash_bit in layout:
        file_off, _memory, decoded = struct.unpack_from("<III", blob, file_at)
        stored = struct.unpack_from("<I", blob, size_at)[0]
        chunk = blob[file_off:file_off + stored]
        compressed = bool(flags & compress_bit)
        plain = lz4_decompress(chunk, decoded) if compressed else chunk
        fixed = patch_archive_name(plain) if MOTOR_ARCHIVE in plain else plain
        if fixed != plain:
            plain = fixed
            chunk = lz4_compress(plain) if compressed else plain
            if flags & hash_bit:
                out[hash_at:hash_at + 32] = hashlib.sha256(plain).digest()
        struct.pack_into("<I", out, file_at, cursor)
        struct.pack_into("<I", out, size_at, len(chunk))
        pieces.append(chunk)
        cursor += len(chunk)
    return bytes(out) + b"".join(pieces)


def rebuild_nro(source: Path, dest: Path, icon: bytes, name: str, author: str, version: str) -> None:
    blob = patch_archive_name(source.read_bytes())
    if blob[0x10:0x14] != b"NRO0":
        raise PrepareError("motor/rgss-switch.nro non è un NRO (manca NRO0).")
    size = struct.unpack_from("<I", blob, 0x18)[0]
    if size <= 0 or size > len(blob):
        raise PrepareError("La dimensione dichiarata nell'NRO non torna con il file.")
    if icon[:2] != b"\xff\xd8":
        raise PrepareError("L'icona deve essere un JPEG.")
    slices = _aset_slices(blob, size)
    nacp = slices[0] if slices and slices[0] is not None else bytearray(0x4000)
    romfs = slices[1] if slices else b""
    rewrite_nacp(nacp, name, author, version)

    header = bytearray(0x38)
    header[0:4] = b"ASET"
    struct.pack_into("<Q", header, 0x08, 0x38)
    struct.pack_into("<Q", header, 0x10, len(icon))
    struct.pack_into("<Q", header, 0x18, 0x38 + len(icon))
    struct.pack_into("<Q", header, 0x20, len(nacp))
    if romfs:
        struct.pack_into("<Q", header, 0x28, 0x38 + len(icon) + len(nacp))
        struct.pack_into("<Q", header, 0x30, len(romfs))
    partial = dest.with_suffix(dest.suffix + ".parcial")
    with partial.open("wb") as handle:
        handle.write(blob[:size])
        handle.write(header)
        handle.write(icon)
        handle.write(nacp)
        if romfs:
            handle.write(romfs)
    partial.replace(dest)


def _version_of(release: Path) -> str:
    path = release / "VERSION.txt"
    if not path.is_file():
        path = release / "VERSION"
    if not path.is_file():
        return "1.0.0"
    token = read_text(path).strip().split()
    version = token[0] if token else "1.0.0"
    return version[:15]


def _choose_icon(info: GameInfo, release: Path, source_nro: Path) -> bytes:
    from icona import exe_icon, jpeg_icon
    custom = getattr(info, "icon_path", None)
    if custom:
        path = Path(custom)
        if path.is_file():
            data = path.read_bytes()
            if data[:2] == b"\xff\xd8":
                return data
            try:
                from PIL import Image
                return jpeg_icon(Image.open(path))
            except Exception:
                pass
    image = exe_icon(info.folder)
    if image is not None:
        try:
            return jpeg_icon(image)
        except Exception:
            pass
    candidates = []
    if info.profile_dir:
        candidates.append(info.profile_dir / "icono.jpg")
    candidates.append(release / "motor" / "icono.jpg")
    for path in candidates:
        if path.is_file():
            data = path.read_bytes()
            if data[:2] == b"\xff\xd8":
                return data
    size = struct.unpack_from("<I", source_nro.read_bytes()[:0x1C], 0x18)[0]
    blob = source_nro.read_bytes()
    slices = _aset_slices(blob, size)
    if slices and slices[2][:2] == b"\xff\xd8":
        return slices[2]
    raise PrepareError("Nella consegna non c'è un'icona JPEG (motor/icono.jpg).")


def _dos_time(timestamp: float) -> tuple:
    import datetime as _dt
    when = _dt.datetime.fromtimestamp(timestamp)
    if when.year < 1980:
        when = _dt.datetime(1980, 1, 1)
    return (when.year, when.month, when.day, when.hour, when.minute, when.second)


def write_stored_zip(
    dest: Path,
    game: Path,
    folders: list,
    banned: set,
    log: Optional[Log] = None,
    progress: Optional[Progress] = None,
    span: tuple = (8, 78),
) -> tuple:
    """Zip metodo 0. PhysFS sulla Switch non deve inflare ogni PNG e ogni OGG."""
    partial = dest.with_name(dest.name + ".parcial")
    if partial.exists():
        partial.unlink()
    files = 0
    total = 0
    entries = 0
    expected = _zip_payload_bytes(game, folders, banned)
    last_report = [0.0, -1]
    lo, hi = span
    _tick(progress, lo, "progress_zip")

    def report_zip() -> None:
        if not progress or expected <= 0:
            return
        pct = lo + int((hi - lo) * min(total, expected) / expected)
        now = time.monotonic()
        if pct <= last_report[1] and now - last_report[0] < 0.12 and pct < hi:
            return
        last_report[0] = now
        last_report[1] = pct
        _tick(progress, pct, "progress_zip")

    def add_dir(zf: zipfile.ZipFile, rel: str) -> None:
        nonlocal entries
        name = rel.replace("\\", "/").rstrip("/") + "/"
        info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_STORED
        info.external_attr = 0x10
        info.create_system = 0
        if any(b > 127 for b in name.encode("utf-8")):
            info.flag_bits |= 0x800
        entries += 1
        if entries > ZIP_LIMIT_ENTRIES:
            raise PrepareError("Troppe voci per un zip classico. Ripeti con le cartelle sciolte.")
        zf.writestr(info, b"")

    def add_tree(zf: zipfile.ZipFile, rel: str) -> None:
        nonlocal files, total, entries
        key = rel.replace("\\", "/").strip("/").lower()
        if key in banned:
            return
        rel = rel.replace("\\", "/").strip("/")
        absolute = game / rel
        add_dir(zf, rel)
        children = sorted(absolute.iterdir(), key=lambda p: p.name.lower())
        for child in children:
            if child.is_file():
                if skipped_name(child.name):
                    continue
                arc = rel + "/" + child.name
                size = child.stat().st_size
                extra_name = _dat_case_alias(rel + "/" + child.name)
                extra_slots = 1 if extra_name else 0
                header = 96 + len(arc.encode("utf-8")) * 2
                if (
                    size >= 0xFFFFFFFF
                    or total + size * (1 + extra_slots) + header > ZIP_LIMIT_BYTES
                    or entries + 1 + extra_slots > ZIP_LIMIT_ENTRIES
                ):
                    raise PrepareError(
                        "Il contenitore supera i limiti dello zip classico (2 GB o 65534 voci). "
                        "Ripeti con le cartelle sciolte."
                    )
                info = zipfile.ZipInfo(arc, date_time=_dos_time(child.stat().st_mtime))
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = 0x20
                info.file_size = size
                if any(b > 127 for b in arc.encode("utf-8")):
                    info.flag_bits |= 0x800
                with child.open("rb") as src, zf.open(info, "w") as out:
                    shutil.copyfileobj(src, out, length=1024 * 1024)
                files += 1
                total += size
                entries += 1
                extra = extra_name
                if extra:
                    alias = zipfile.ZipInfo(extra, date_time=_dos_time(child.stat().st_mtime))
                    alias.compress_type = zipfile.ZIP_STORED
                    alias.external_attr = 0x20
                    alias.file_size = size
                    if any(b > 127 for b in extra.encode("utf-8")):
                        alias.flag_bits |= 0x800
                    with child.open("rb") as src, zf.open(alias, "w") as out:
                        shutil.copyfileobj(src, out, length=1024 * 1024)
                    files += 1
                    total += size
                    entries += 1
                    _log(log, f"     also {extra} (same as {arc})")
                if files % 2500 == 0:
                    _log(log, f"     {files:6} file, {total // (1024 * 1024):5} MB")
                report_zip()
            elif child.is_dir():
                add_tree(zf, rel + "/" + child.name)

    try:
        with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as zf:
            for folder in folders:
                if not (game / folder).is_dir():
                    continue
                _log(log, f"     {folder}")
                add_tree(zf, folder)
    except zipfile.LargeZipFile as exc:
        if partial.exists():
            partial.unlink()
        raise PrepareError(
            "Il contenitore supera i limiti dello zip classico (2 GB o 65534 voci). "
            "Ripeti con le cartelle sciolte."
        ) from exc
    partial.replace(dest)
    _log(log, f"     {files} file, {total // (1024 * 1024)} MB dentro {dest.name}")
    _tick(progress, hi, "progress_zip")
    return files, total


def _zip_payload_bytes(game: Path, folders: list, banned: set) -> int:
    total = 0
    for folder in folders:
        root = game / folder
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            rel = Path(dirpath).relative_to(game).as_posix()
            if rel.lower() in banned:
                dirnames[:] = []
                continue
            dirnames[:] = [
                name for name in dirnames
                if (rel + "/" + name).lower() not in banned and not skipped_name(name)
            ]
            for name in filenames:
                if skipped_name(name):
                    continue
                try:
                    size = (Path(dirpath) / name).stat().st_size
                except OSError:
                    continue
                total += size
                arc = rel + "/" + name
                if _dat_case_alias(arc):
                    total += size
    return total


def _dat_case_alias(arc: str) -> Optional[str]:
    """Realidea chiede Data/english.dat; il file sul PC è spesso English.dat."""
    name = arc.replace("\\", "/")
    if not re.match(r"(?i)^Data/[^/]+\.dat$", name):
        return None
    folder, base = name.rsplit("/", 1)
    lower = f"{folder}/{base.lower()}"
    if lower == name:
        return None
    return lower


def verify_stored_zip(path: Path, files: int, total: int) -> None:
    with zipfile.ZipFile(path) as zf:
        members = [info for info in zf.infolist() if not info.filename.endswith("/")]
        if not members:
            raise PrepareError("Il contenitore non ha file dentro.")
        if len(members) != files:
            raise PrepareError(f"Il contenitore ha {len(members)} file, ne erano stati messi {files}.")
        size = sum(info.file_size for info in members)
        if size != total:
            raise PrepareError(f"Il contenitore somma {size} byte, l'originale {total}.")
        for info in zf.infolist():
            if "\\" in info.filename:
                raise PrepareError("Nome con barra rovescia nel contenitore: " + info.filename)
            if info.compress_type != zipfile.ZIP_STORED or info.compress_size != info.file_size:
                raise PrepareError("Voce compressa nel contenitore: " + info.filename)


def copy_tree(source: Path, dest: Path, log: Optional[Log] = None) -> None:
    if not source.is_dir():
        return
    dest.mkdir(parents=True, exist_ok=True)
    for dirpath, dirnames, filenames in os.walk(source):
        dirnames.sort()
        current = Path(dirpath)
        relative = current.relative_to(source)
        target_dir = dest / relative
        target_dir.mkdir(parents=True, exist_ok=True)
        for filename in sorted(filenames):
            if skipped_name(filename):
                continue
            shutil.copy2(current / filename, target_dir / filename)


def _exec_name(info: GameInfo) -> str:
    mkxp = _get(info.profile, "mkxp") or {}
    name = _get(mkxp, "execName") if isinstance(mkxp, dict) else None
    return str(name) if name else "Game"


_LOADER_CALL = re.compile(
    r"""load_scripts_from_folder\s*\(\s*["']([^"']+)["']\s*\)"""
)


def _loader_folders(game: Path) -> list:
    """Cartelle che il Main apre con Dir. I byte sono compressi dentro il rxdata."""
    rx = game / "Data" / "Scripts.rxdata"
    if not rx.is_file() or rx.stat().st_size > 80 * 1024 * 1024:
        return []
    blob = rx.read_bytes()
    found = []
    i = 0
    seen_streams = 0
    while seen_streams < 40:
        j = blob.find(b"\x78", i)
        if j < 0 or j + 1 >= len(blob):
            break
        if blob[j + 1] not in (0x01, 0x5E, 0x9C, 0xDA):
            i = j + 1
            continue
        i = j + 1
        try:
            out = zlib.decompressobj().decompress(blob[j:], 2_000_000)
        except zlib.error:
            continue
        if b"load_scripts_from_folder" not in out:
            continue
        seen_streams += 1
        text = out.decode("utf-8", "replace")
        for match in _LOADER_CALL.finditer(text):
            rel = match.group(1).replace("\\", "/").strip().strip("/")
            if rel and rel not in found:
                found.append(rel)
    return found


def _loose_and_banned(info: GameInfo) -> tuple:
    loose = [item.replace("\\", "/") for item in _as_list(_get(info.profile, "sueltos"))]
    exclude = list(EXCLUDE_DEFAULT)
    for item in _as_list(_get(info.profile, "excluir")):
        if item not in exclude:
            exclude.append(item)
    # Il Main spesso non contiene il gioco: chiama load_scripts_from_folder e
    # Dir.foreach legge la scheda, non data.zip. Il percorso sta scritto nello
    # Scripts.rxdata (Essentials: Data/Scripts, Reminiscence: Data/export).
    # Se il lettore non lo trova, restano le due cartelle già viste, purché
    # contengano degli .rb.
    named = _loader_folders(info.folder)
    for rel in named:
        folder = info.folder / rel
        if rel not in loose and folder.is_dir():
            loose.append(rel)
    if not named:
        for name in ("Scripts", "export"):
            folder = info.folder / "Data" / name
            rel = f"Data/{name}"
            if rel in loose or not folder.is_dir():
                continue
            if any(folder.rglob("*.rb")):
                loose.append(rel)
    banned = {item.strip("/").lower() for item in loose}
    banned.update(item.replace("\\", "/").strip("/").lower() for item in exclude)
    return loose, exclude, banned


def write_porter_cfg(
    dest: Path,
    info: GameInfo,
    scala: str = "intera",
    proporzioni: str = "fisse",
    lingua: str = "en",
) -> None:
    lines = [
        "menu=1",
        f"slug={info.slug}",
        f"titolo={info.name}",
        f"versione={info.version}",
        f"autore={info.author}",
        "volume=100",
        f"scala={scala if scala in GRAFICA else 'intera'}",
        f"proporzioni={proporzioni}",
        "fps=auto",
        f"lingua={lingua if lingua in ('en', 'it') else 'en'}",
        "accetta=C",
        "indietro=B",
        "corsa=A",
        "tasto_a=X",
        "tasto_s=Y",
        "tasto_d=Z",
        "elle=L",
        "erre=R",
        "tasto_f7=Z",
        "turbo=0",
        "menu_apri=stick",
        "tema=chiaro",
        "contatore=0",
        "registro=0",
        "croce=0",
        "pc=C:C,B:X,A:Z",
        "assi=1",
        f"profilo={info.input_profile}",
        f"tasti={info.tasti}",
        "",
    ]
    (dest / "porter.cfg").write_text("\n".join(lines), encoding="utf-8")


def _guard_zip_budget(game: Path, folders: list, banned: set) -> None:
    """Prima di scrivere: lo zip classico di Python non regge oltre 2 GB o 65534 voci."""
    files = 0
    total = 0

    def walk(rel: str) -> None:
        nonlocal files, total
        key = rel.replace("\\", "/").strip("/").lower()
        if key in banned:
            return
        files += 1
        absolute = game / rel
        for child in absolute.iterdir():
            if child.is_file():
                if skipped_name(child.name):
                    continue
                files += 1
                size = child.stat().st_size
                name = (rel + "/" + child.name).encode("utf-8")
                total += size + 96 + len(name) * 2
                if size >= 0xFFFFFFFF:
                    total = ZIP_LIMIT_BYTES + 1
            elif child.is_dir():
                walk(rel + "/" + child.name)
            if files > ZIP_LIMIT_ENTRIES or total > ZIP_LIMIT_BYTES:
                raise PrepareError(
                    "Il gioco supera i limiti dello zip classico (2 GB o 65534 file). "
                    "Non ho iniziato a prepararlo. Ripeti con le cartelle sciolte."
                )

    for folder in folders:
        if (game / folder).is_dir():
            walk(folder)


KEEP_DIRS = {"backups", "backup"}


def kept_file(name: str) -> bool:
    """File che un aggiornamento non deve riscrivere."""
    low = name.lower()
    if low in {
        "porter.cfg",
        "teclas.cfg",
        "lastsave.dat",
        "game.rxdata",
        "global.rxdata",
        "mkxp-boot.log",
        "mkxp-ruby.log",
        "mkxp-debug.log",
        "errorlog.txt",
        "porter-errore.txt",
    }:
        return True
    if low.startswith("save") and low.endswith(".rxdata"):
        return True
    if low.startswith("file ") and low.endswith(".rxdata"):
        return True
    return False


def kept_dir(name: str) -> bool:
    return name.lower() in KEEP_DIRS


ACTION_CODES = ("accetta", "indietro", "corsa", "tasto_a", "tasto_s", "tasto_d", "elle", "erre")
PAD_CODES = {"C", "B", "X", "A", "Y", "Z", "L", "R"}
CLICK_CODES = {"L3", "R3"}


def button_updates(
    comandi: Optional[dict],
    pc: Optional[str],
    turbo: Optional[str] = None,
    contatore: Optional[str] = None,
    registro: Optional[str] = None,
    menu_apri: Optional[str] = None,
    croce: Optional[str] = None,
    tema: Optional[str] = None,
) -> dict:
    """Righe di porter.cfg per i tasti. I codici sono quelli del motore (A della Switch è C)."""
    updates = {}
    for key in ACTION_CODES:
        value = (comandi or {}).get(key)
        if value in PAD_CODES:
            updates[key] = value
    if pc is not None:
        updates["pc"] = pc
    if turbo in PAD_CODES or turbo in CLICK_CODES or turbo in ("0", "+"):
        updates["turbo"] = turbo
    if contatore in ("0", "1"):
        updates["contatore"] = contatore
    if registro in ("0", "1"):
        updates["registro"] = registro
    if menu_apri in (
        "stick", "spalle", "meno", "piu",
        "C", "B", "A", "X", "Y", "Z", "L", "R",
        "L3", "R3", "UP", "DOWN", "LEFT", "RIGHT", "PLUS", "MINUS",
    ):
        updates["menu_apri"] = menu_apri
    if croce in ("0", "1"):
        updates["croce"] = croce
    if tema in ("chiaro", "scuro"):
        updates["tema"] = tema
    return updates


def read_cfg(path: Path) -> dict:
    out = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def patch_cfg_keys(path: Path, updates: dict) -> None:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.is_file() else []
    seen = set()
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def backup_kept(game_dir: Path, dest: Path) -> list:
    names = []
    if not game_dir.is_dir():
        return names
    for item in sorted(game_dir.iterdir(), key=lambda path: path.name.lower()):
        if not (kept_file(item.name) or (item.is_dir() and kept_dir(item.name))):
            continue
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
        names.append(item.name)
    return names


def save_entries(game_dir: Path) -> list:
    found = []
    if not game_dir.is_dir():
        return found
    for item in sorted(game_dir.iterdir(), key=lambda path: path.name.lower()):
        low = item.name.lower()
        if low in {"porter.cfg", "teclas.cfg"} or low.endswith(".log") or low.endswith(".txt"):
            continue
        if kept_file(item.name) or (item.is_dir() and kept_dir(item.name)):
            found.append(item)
    return found


def settings_path() -> Path:
    override = os.environ.get("FDP_IMPOSTAZIONI")
    if override:
        return Path(override)
    return support_dir() / "impostazioni.json"


def load_settings() -> tuple:
    path = settings_path()
    empty = {"games": {}, "by_path": {}}
    if not path.is_file():
        return empty, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        bak = path.with_name("impostazioni.json.bak")
        try:
            shutil.copy2(path, bak)
        except OSError:
            pass
        return empty, (
            "Le impostazioni erano illeggibili. Ho tenuto una copia .bak "
            "e riparto dai valori di base."
        )
    if not isinstance(data, dict):
        return empty, "Le impostazioni non erano un oggetto. Riparto dai valori di base."
    data.setdefault("games", {})
    data.setdefault("by_path", {})
    return data, None


def save_settings(data: dict) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("impostazioni.json.parcial")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def newer_motor_note() -> Optional[str]:
    """Confronta il motore in uso con l'ultima release. Non scarica niente."""
    url = "https://api.github.com/repos/randygil/rgss-switch/releases/latest"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "FanDPorter", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    tag = str(payload.get("tag_name") or "").lstrip("v")
    if tag and tag != MOTOR_VERSION:
        return (
            f"Il motore in uso è {MOTOR_VERSION}. Su GitHub c'è {tag}. "
            "Non lo sostituisco da solo: questa app è provata con 0.2.4."
        )
    return f"Il motore in uso è {MOTOR_VERSION}, ed è l'ultima release pubblicata."


def _remember_game(info: GameInfo, scala: Optional[str], log: Optional[Log]) -> None:
    data, warn = load_settings()
    if warn:
        _log(log, warn)
    key = str(info.folder.resolve())
    previous = (data.get("by_path") or {}).get(key)
    if previous and previous != info.slug:
        _log(
            log,
            f"Lo slug resta {previous}. Con {info.slug} sarebbe un altro gioco "
            "e i salvataggi non si ritrovano.",
        )
        info.slug = previous
        info.titleid = title_id(previous)
    slot = data.setdefault("games", {}).setdefault(info.slug, {})
    forced = slot.get("famiglia")
    if forced in ("ruby18", "ruby31", "rgss1"):
        info.family = forced
        _log(log, f"Famiglia scelta a mano: {forced}.")
    data.setdefault("by_path", {})[key] = info.slug
    slot["nome"] = info.name
    slot["motore"] = MOTOR_VERSION
    if scala in GRAFICA:
        slot["grafica"] = scala
    save_settings(data)


def _commit_game(staging: Path, dest: Path) -> None:
    """Sposta il gioco pronto solo alla fine. Un aggiornamento non tocca salvataggi e cfg."""
    if not dest.exists():
        staging.rename(dest)
        return
    for item in list(staging.iterdir()):
        target = dest / item.name
        if target.exists() and (kept_file(item.name) or (item.is_dir() and kept_dir(item.name))):
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            continue
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
        shutil.move(str(item), str(target))
    staging.rmdir()


def bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent


def _place_motor(
    info: GameInfo,
    release: Path,
    dest: Path,
    log: Optional[Log],
    scala: str = "intera",
    proporzioni: str = "fisse",
    lingua: str = "en",
) -> None:
    from icona import exe_icon
    from splash import stamp_loading_screen
    shown = info.version or "1.0"
    source = release / "motor" / "rgss-switch.nro"
    icon = _choose_icon(info, release, source)
    nro_path = dest / f"{info.slug}.nro"
    rebuild_nro(source, nro_path, icon, info.name, info.author, shown)
    mark = exe_icon(info.folder)
    try:
        stamped = stamp_loading_screen(nro_path, info.name, mark, APP_VERSION, lingua)
    except Exception as exc:
        stamped = False
        _log(log, f"     schermata di caricamento non ridisegnata ({exc}).")
    if stamped:
        _log(log, "     caricamento con l'icona del gioco" if mark is not None else "     caricamento Fan Porter")
    _log(log, f"     {nro_path.name}  (trova il gioco nella propria cartella)")
    shims = resolve_shims(info, release, log)
    (dest / "mkxp.json").write_text(
        compose_mkxp(info, release, shims, log, scala, proporzioni),
        encoding="utf-8",
    )
    _log(log, f"     mkxp.json (base + gioco + profilo {info.profile_name}, grafica {scala})")

    lib_dest = dest / "lib"
    lib_dest.mkdir(parents=True, exist_ok=True)
    for old in lib_dest.glob("nx-*.rb"):
        old.unlink()
    copy_tree(release / "lib", lib_dest, log)
    shim_root = _shim_dir(release)
    copied = []
    for shim in shims:
        if shim["where"] != "shims":
            continue
        origin = (shim_root / shim["file"]) if shim_root else None
        if origin and origin.is_file():
            shutil.copy2(origin, lib_dest / origin.name)
            copied.append(origin.name)
        else:
            _log(log, f"     Manca lo shim {shim['file']}.")
    if copied:
        _log(log, "     shims: " + ", ".join(copied))
    if info.profile_dir and (info.profile_dir / "lib").is_dir():
        for script in sorted((info.profile_dir / "lib").glob("*.rb")):
            shutil.copy2(script, lib_dest / script.name)
        _log(log, "     shims del profilo copiati in lib/")
    ruby18 = bundle_root() / "runtime" / "nx-ruby18.rb"
    if info.family in ("ruby18", "rgss1"):
        if not ruby18.is_file():
            raise PrepareError("Manca runtime/nx-ruby18.rb per un gioco Ruby 1.8.")
        shutil.copy2(ruby18, lib_dest / ruby18.name)
        _log(log, "     lib/nx-ruby18.rb (lettere, StringInput, Missions)")
    else:
        leftover = lib_dest / "nx-ruby18.rb"
        if leftover.is_file():
            leftover.unlink()
        _log(log, "     senza nx-ruby18: gli script sono già Ruby 3.")
    porter = bundle_root() / "runtime" / "nx-porter.rb"
    if not porter.is_file():
        raise PrepareError("Manca runtime/nx-porter.rb.")
    shutil.copy2(porter, lib_dest / porter.name)
    mark = bundle_root() / "runtime" / "fan-porter-mark.png"
    if mark.is_file():
        shutil.copy2(mark, lib_dest / mark.name)
    write_porter_cfg(dest, info, scala, proporzioni, lingua)
    _log(log, "     opzioni: grafica, volume e tasti. Il menu si apre al primo avvio, poi con L3+R3.")


def prepare(
    info: GameInfo,
    release: Path,
    output: Path,
    mode: str = "zip",
    log: Optional[Log] = None,
    remember: bool = False,
    scala: Optional[str] = None,
    proporzioni: Optional[str] = None,
    explicit: bool = False,
    lingua: Optional[str] = None,
    explicit_lingua: bool = False,
    comandi: Optional[dict] = None,
    pc: Optional[str] = None,
    explicit_comandi: bool = False,
    turbo: Optional[str] = None,
    contatore: Optional[str] = None,
    registro: Optional[str] = None,
    menu_apri: Optional[str] = None,
    croce: Optional[str] = None,
    tema: Optional[str] = None,
    progress: Optional[Progress] = None,
) -> Path:
    if mode not in ("zip", "cartelle"):
        raise PrepareError("Modo sconosciuto: usa zip o cartelle.")
    _tick(progress, 2, "progress_checks")
    problem = check_game(info.folder)
    if problem:
        raise PrepareError(problem)
    problem = check_release(release)
    if problem:
        raise PrepareError(problem)
    info.input_profile, info.tasti = detect_tasti(info.folder, info.title)
    _tick(progress, 6, "progress_profile")
    _log(log, f"This game: command profile {info.input_profile} ({info.tasti}).")
    for warning in info.warnings:
        _log(log, warning)
    if remember:
        _remember_game(info, scala, log)

    loose, exclude, banned = _loose_and_banned(info)
    present = [name for name in RESOURCE_DIRS if (info.folder / name).is_dir()]
    if mode == "zip" and present:
        try:
            _guard_zip_budget(info.folder, present, banned)
        except PrepareError as exc:
            _log(log, str(exc))
            _log(log, "Classic zip stops at 2 GB. This game is copied as loose folders.")
            mode = "cartelle"
    output = output.expanduser().resolve()
    switch_root = output / "switch"
    final = switch_root / info.slug
    existing = read_cfg(final / "porter.cfg")
    if existing.get("scala") in GRAFICA and not explicit:
        scala = existing["scala"]
        proporzioni = existing.get("proporzioni") or "fisse"
        _log(log, f"Graphics already on the card: {scala}. Keeping it.")
    else:
        scala = scala if scala in GRAFICA else "intera"
        proporzioni = proporzioni if proporzioni in ("fisse", "libere") else "fisse"
    lingua = lingua if lingua in ("en", "it") else "en"
    if existing.get("lingua") in ("en", "it") and not explicit_lingua:
        lingua = existing["lingua"]
    had_cfg = (final / "porter.cfg").is_file()
    updating = final.exists()
    if updating:
        stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
        backed = backup_kept(final, output / "backup" / f"{info.slug}-{stamp}")
        if backed:
            _log(log, "Backup before updating: " + ", ".join(backed))
        else:
            _log(log, "Updating. There were no saves to copy.")
        _log(log, "Existing saves and porter.cfg stay where they are.")
    dest = switch_root / f".{info.slug}.preparo"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    try:
        try:
            _fill_game(
                info, release, dest, mode, log, loose, exclude, banned, present,
                scala, proporzioni, lingua, progress,
            )
        except PrepareError as exc:
            if mode != "zip" or "zip classico" not in str(exc):
                raise
            _log(log, str(exc))
            _log(log, "Classic zip stops at 2 GB. This game is copied as loose folders.")
            if dest.exists():
                shutil.rmtree(dest)
            dest.mkdir(parents=True)
            mode = "cartelle"
            _fill_game(
                info, release, dest, mode, log, loose, exclude, banned, present,
                scala, proporzioni, lingua, progress,
            )
        staged_buttons = button_updates(comandi, pc, turbo, contatore, registro, menu_apri, croce, tema) if explicit_comandi else {}
        if staged_buttons and not had_cfg:
            patch_cfg_keys(dest / "porter.cfg", staged_buttons)
        _commit_game(dest, final)
        leftover = final / "datos.zip"
        if (final / ARCHIVE_NAME).is_file() and leftover.is_file():
            leftover.unlink()
        updates = {}
        if explicit and had_cfg:
            updates["scala"] = scala
            updates["proporzioni"] = proporzioni
            _log(log, "Only the graphics line in porter.cfg was updated. The rest stayed.")
        if explicit_lingua and had_cfg:
            updates["lingua"] = lingua
            _log(log, f"Interface language on the card: {lingua}.")
        if explicit_comandi and had_cfg:
            updates.update(button_updates(comandi, pc, turbo, contatore, registro, menu_apri, croce, tema))
            _log(log, "Button lines in porter.cfg were updated. Saves stayed.")
        updates["profilo"] = info.input_profile
        updates["tasti"] = info.tasti
        if updates:
            patch_cfg_keys(final / "porter.cfg", updates)
        _log(log, f"Command profile: {info.input_profile} ({info.tasti}).")
        _adapt_prepared_game(info, final, mode, log)
        _tick(progress, 100, "progress_done")
    except Exception:
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        raise

    _log(log, "")
    _log(log, f"Ready: {final}")
    _log(log, "Copy the switch folder to the root of the SD card.")
    _log(log, f"The game is sdmc:/switch/{info.slug}/{info.slug}.nro")
    _log(log, "Open it from the homebrew menu by holding R on an installed game, not from the album alone:")
    _log(log, "an applet does not have enough memory for Ruby and the resources.")
    return final


def _fill_game(
    info, release, dest, mode, log, loose, exclude, banned, present,
    scala, proporzioni, lingua="en", progress=None,
) -> None:
    exec_name = _exec_name(info)
    if mode == "zip":
        _log(log, f"1/4 Resources in {ARCHIVE_NAME}")
        if present:
            files, total = write_stored_zip(
                dest / ARCHIVE_NAME, info.folder, present, banned, log, progress, (8, 78),
            )
            verify_stored_zip(dest / ARCHIVE_NAME, files, total)
        else:
            _log(log, "     No Data/Graphics/Audio folder to put in the container.")
    else:
        _log(log, "1/4 Resources as loose folders")
        for name in present:
            _log(log, f"     {name}")
            copy_tree(info.folder / name, dest / name, log)
        for name in exclude:
            leftover = dest / name.replace("/", os.sep)
            if leftover.exists():
                shutil.rmtree(leftover)

    _tick(progress, 80, "progress_files")
    _log(log, "2/4 Loose files")
    archive_dest = exec_name + ".rgssad"
    count = 0
    for path in sorted((p for p in info.folder.iterdir() if p.is_file()), key=lambda p: p.name.lower()):
        if skipped_name(path.name) or path.name.lower() == "mkxp.json":
            continue
        target_name = path.name
        if info.archive_name and path.name.lower() == info.archive_name.lower():
            target_name = archive_dest
            if target_name != path.name:
                _log(log, f"     {path.name} -> {target_name}")
        shutil.copy2(path, dest / target_name)
        count += 1
    _log(log, f"     {count} files at the root")
    if info.ini_name and info.ini_name.lower() != (exec_name + ".ini").lower():
        shutil.copy2(info.folder / info.ini_name, dest / f"{exec_name}.ini")
        _log(log, f"     {info.ini_name} also copied as {exec_name}.ini")

    unknown = []
    for directory in sorted((p for p in info.folder.iterdir() if p.is_dir()), key=lambda p: p.name.lower()):
        if directory.name in exclude:
            _log(log, f"     (excluded {directory.name}: development files)")
            continue
        if directory.name in RESOURCE_DIRS:
            continue
        if directory.name not in loose and directory.name.replace("\\", "/") not in loose:
            unknown.append(directory.name)
        _log(log, f"     {directory.name}/ (loose)")
        copy_tree(directory, dest / directory.name, log)
    if mode == "zip":
        for item in loose:
            if "/" not in item and "\\" not in item:
                continue
            origin = info.folder / item
            if origin.is_dir():
                _log(log, f"     {item}/ kept out of the container")
                copy_tree(origin, dest / item, log)
    if unknown:
        _log(log, "     Unexpected folders, copied loose: " + ", ".join(unknown))

    _tick(progress, 88, "progress_engine")
    _log(log, "3/4 Container key and engine")
    key_path = dest / archive_dest
    if mode == "zip":
        if info.archive_name:
            _log(log, f"     {archive_dest}: the game already has its archive, no empty key.")
        else:
            key_path.write_bytes(RGSSAD_KEY)
            _log(log, f"     {archive_dest} (8 bytes): the game then reads inside {ARCHIVE_NAME}.")
    elif key_path.is_file() and key_path.stat().st_size == 8 and key_path.read_bytes() == RGSSAD_KEY:
        key_path.unlink()
        _log(log, "     Empty key removed: loose folders do not need it.")

    _place_motor(info, release, dest, log, scala, proporzioni, lingua)

    _tick(progress, 94, "progress_adapt")
    _log(log, "4/4 Check")
    required = [f"{info.slug}.nro", "mkxp.json", "lib/nx-compat.rb", f"{exec_name}.ini"]
    if mode == "zip" and present:
        required.append(ARCHIVE_NAME)
    missing = [name for name in required if not (dest / name).exists()]
    if missing:
        raise PrepareError("Mancano in uscita: " + ", ".join(missing))
    if mode == "zip" and (dest / "Data").is_dir() and (dest / ARCHIVE_NAME).is_file():
        script_roots = set()
        for item in loose:
            norm = item.replace("\\", "/").strip("/")
            if norm.lower().startswith("data/"):
                script_roots.add(norm.split("/", 1)[1].split("/")[0])
        only_scripts = True
        for dirpath, dirnames, filenames in os.walk(dest / "Data"):
            rel = Path(dirpath).relative_to(dest / "Data").as_posix()
            first = "." if rel == "." else rel.split("/")[0]
            if first not in script_roots and first != "." and filenames:
                only_scripts = False
        if not only_scripts:
            _log(log, f"     Both {ARCHIVE_NAME} and Data/ are present. The engine reads the zip.")


def _adapt_prepared_game(info: GameInfo, dest: Path, mode: str, log: Optional[Log]) -> None:
    """Controlli che dipendono dal gioco: tasti, shim, file lingua nel zip."""
    porter = dest / "lib" / "nx-porter.rb"
    ruby18 = dest / "lib" / "nx-ruby18.rb"
    if not porter.is_file():
        raise PrepareError("Manca lib/nx-porter.rb dopo la preparazione.")
    cfg = read_cfg(dest / "porter.cfg")
    if cfg.get("tasti") != info.tasti or cfg.get("profilo") != info.input_profile:
        raise PrepareError("porter.cfg non ha il profilo comandi di questo gioco.")
    _log(log, f"     {info.name}: tasti={info.tasti}, family={info.family}")
    if info.family in ("ruby18", "rgss1") and not ruby18.is_file():
        raise PrepareError("Manca lib/nx-ruby18.rb per un gioco Ruby 1.8.")
    if ruby18.is_file():
        body = ruby18.read_text(encoding="utf-8", errors="replace")
        if "def self.misiones" not in body:
            raise PrepareError("nx-ruby18.rb senza la patch Missions.")
        if info.input_profile == "realidea":
            _log(log, "     Realidea Missions: A del menu pausa non apre da solo la scheda.")
    if mode == "zip" and (dest / ARCHIVE_NAME).is_file():
        with zipfile.ZipFile(dest / ARCHIVE_NAME) as zf:
            names = {info_zip.filename.replace("\\", "/") for info_zip in zf.infolist()}
        langs = sorted(
            name for name in names
            if re.match(r"(?i)^Data/[^/]+\.dat$", name)
        )
        if langs:
            _log(log, "     Language files in the zip: " + ", ".join(langs))
        if info.input_profile == "realidea":
            has_en = any(name.lower() == "data/english.dat" for name in names)
            if not has_en:
                _log(log, "     Realidea: no english.dat in the zip; Spanish still loads.")


def describe(info: GameInfo) -> str:
    lines = [
        f"Title: {info.title or '(no Title)'}",
        f"Name: {info.name}",
        f"Slug: {info.slug}",
        f"SD folder: switch/{info.slug}/{info.slug}.nro",
        f"Profile: {info.profile_name}",
        f"Commands: {info.input_profile} ({info.tasti})",
        f"Interpreter on PC: {info.family_seen}",
        f"Family used: {info.family}",
        f"Ini: {info.ini_name or '(none)'}",
        f"Archive: {info.archive_name or '(none, an 8-byte key will be used)'}",
    ]
    lines.extend(info.warnings)
    return "\n".join(lines)
