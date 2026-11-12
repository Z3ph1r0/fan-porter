"""Aggiornamento del programma da una cartella pubblica di Google Drive.

Accanto ad app.py:
  versione.txt       numero di build installato, per esempio 202610271630
  aggiornamento.txt  link di condivisione di fdp-aggiornamento.zip su Drive

Il pacchetto è un solo zip con dentro il suo versione.txt. Su Drive si sostituisce
con "Gestisci versioni", così il link non cambia. Contiene solo i file del
programma: i .py, runtime/ e assets/.
Il motore, Python, i giochi e le impostazioni non si toccano.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import ssl
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

BUILD_FILE = "versione.txt"
SOURCE_FILE = "aggiornamento.txt"
MANIFEST_NAME = "fdp-versione.json"
PACKAGE_NAME = "fdp-aggiornamento.zip"
BACKUP_DIR = "aggiornamento-precedente"
TOP_FILES = ("app.py", "ui.py", "i18n.py", "engine.py", "splash.py", "nsp.py", "icona.py", "updater.py", BUILD_FILE)
TOP_DIRS = ("runtime", "assets")
TIMEOUT = 20
MAX_PACKAGE = 64 * 1024 * 1024


class UpdateError(Exception):
    pass


def app_dir() -> Path:
    return Path(__file__).resolve().parent


def installed_build(folder: Path | None = None) -> int:
    path = (folder or app_dir()) / BUILD_FILE
    try:
        return int(path.read_text(encoding="utf-8").strip() or 0)
    except (OSError, ValueError):
        return 0


def source_ref(folder: Path | None = None) -> str:
    path = (folder or app_dir()) / SOURCE_FILE
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line
    except OSError:
        pass
    return ""


def drive_id(ref: str) -> str:
    ref = ref.strip()
    for pattern in (r"/file/d/([A-Za-z0-9_-]{10,})", r"[?&]id=([A-Za-z0-9_-]{10,})"):
        found = re.search(pattern, ref)
        if found:
            return found.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", ref):
        return ref
    return ""


def download_url(ref: str) -> str:
    """Un id o un link di condivisione di Drive diventa il download diretto."""
    if ref.startswith(("file:", "http://127.0.0.1", "http://localhost")):
        return ref
    ident = drive_id(ref)
    if ident:
        return f"https://drive.usercontent.google.com/download?id={ident}&export=download&confirm=t"
    if ref.startswith("https://"):
        return ref
    raise UpdateError(f"Link di aggiornamento non valido: {ref}")


def fetch(ref: str, limit: int = MAX_PACKAGE) -> bytes:
    url = download_url(ref)
    request = urllib.request.Request(url, headers={"User-Agent": "FanDPorter-updater"})
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT, context=context) as answer:
            kind = answer.headers.get("Content-Type", "")
            data = answer.read(limit + 1)
    except OSError as exc:
        raise UpdateError(f"Non raggiungo il server degli aggiornamenti: {exc}") from exc
    if len(data) > limit:
        raise UpdateError("Il file di aggiornamento è troppo grande.")
    if "text/html" in kind:
        raise UpdateError("Drive ha risposto con una pagina web: il file non è condiviso con chiunque abbia il link.")
    return data


def package_build(data: bytes) -> int:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return int(archive.read(BUILD_FILE).decode("utf-8").strip())
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise UpdateError("Il pacchetto su Drive non ha un numero di versione.") from exc


def newer(folder: Path | None = None) -> dict | None:
    """Cosa installare se su Drive c'è una build più nuova di quella installata.

    Il link può puntare al pacchetto zip (un solo file, caricato dal browser)
    oppure a fdp-versione.json.
    """
    ref = source_ref(folder)
    if not ref:
        return None
    data = fetch(ref)
    if data.startswith(b"PK"):
        manifest = {"build": package_build(data), "versione": "", "data": data}
    else:
        try:
            manifest = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise UpdateError("Il file della versione non è leggibile.") from exc
        if not isinstance(manifest, dict) or not isinstance(manifest.get("build"), int) or not manifest.get("file") or not manifest.get("sha256"):
            raise UpdateError("Il file della versione è incompleto.")
    if manifest["build"] <= installed_build(folder):
        return None
    return manifest


def allowed(name: str) -> bool:
    if not name or name.startswith("/") or "\\" in name or ".." in name.split("/"):
        return False
    if name in TOP_FILES:
        return True
    head = name.split("/", 1)[0]
    return head in TOP_DIRS and "/" in name


def apply(manifest: dict, folder: Path | None = None) -> list[str]:
    """Scarica, controlla l'impronta e sostituisce i file. I vecchi vanno in aggiornamento-precedente/."""
    folder = folder or app_dir()
    if manifest.get("data"):
        data = manifest["data"]
    else:
        data = fetch(str(manifest["file"]))
        if hashlib.sha256(data).hexdigest() != str(manifest["sha256"]).lower():
            raise UpdateError("Il pacchetto scaricato non corrisponde: non lo installo.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UpdateError("Il pacchetto scaricato non è uno zip valido.") from exc
    with archive:
        names = [info.filename for info in archive.infolist() if not info.is_dir()]
        bad = [name for name in names if not allowed(name)]
        if bad or BUILD_FILE not in names:
            raise UpdateError("Il pacchetto contiene file che non appartengono al programma: non lo installo.")
        backup = folder / BACKUP_DIR
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        for name in names:
            target = folder / name
            if target.is_file():
                saved = backup / name
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, saved)
        for name in names:
            target = folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(target.name + ".nuovo")
            temp.write_bytes(archive.read(name))
            temp.replace(target)
    return names


def restart(folder: Path | None = None) -> None:
    folder = folder or app_dir()
    launcher = folder / "Fan D Porter.exe"
    if sys.platform == "win32" and launcher.is_file():
        subprocess.Popen([str(launcher)], cwd=str(folder), close_fds=True)
    else:
        subprocess.Popen([sys.executable, str(folder / "app.py")], cwd=str(folder), close_fds=True)
