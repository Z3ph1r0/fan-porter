#!/usr/bin/env python3
"""Apri l'app, metti la cartella del gioco per PC, ottieni la cartella per la SD.

  python3 app.py
  python3 app.py --gioco CARTELLA
"""

from __future__ import annotations

import argparse
import ctypes
import os
import queue
import shutil
import subprocess
import sys
import threading
import traceback
from pathlib import Path


def _log_dir() -> Path:
    if sys.platform == "win32" and os.environ.get("APPDATA"):
        root = Path(os.environ["APPDATA"]) / "Fan Porter"
        old = Path(os.environ["APPDATA"]) / "Fan D Porter"
        if not root.exists() and old.exists():
            root = old
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / "Fan Porter"
        old = Path.home() / "Library" / "Application Support" / "Fan D Porter"
        if not root.exists() and old.exists():
            root = old
    else:
        root = Path.home() / ".fan-porter"
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        root = Path(__file__).resolve().parent
    return root


def report_crash(text: str) -> None:
    folder = _log_dir()
    try:
        (folder / "errore.txt").write_text(text, encoding="utf-8")
    except OSError:
        pass
    try:
        (Path(__file__).resolve().parent / "errore.txt").write_text(text, encoding="utf-8")
    except OSError:
        pass
    try:
        import tkinter as tk
        from tkinter import messagebox

        window = tk.Tk()
        window.withdraw()
        messagebox.showerror(
            "Fan Porter",
            "The app could not start.\nThe detail is in errore.txt, next to the app and in:\n" + str(folder),
        )
        window.destroy()
    except Exception:
        pass


def _hook(kind, value, tb) -> None:
    report_crash("".join(traceback.format_exception(kind, value, tb)))


sys.excepthook = _hook


def enable_windows_dpi() -> None:
    """Tell Windows not to stretch the window. A stretched window looks soft."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

def _here() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent


sys.path.insert(0, str(_here() / "vendor"))


def motor_zip():
    """Lo zip del motore messo nel pacchetto, così non serve scaricarlo."""
    here = _here()
    found = [
        here / "motore" / "rgss-switch.zip",
        here / "rgss-switch.zip",
    ]
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        if len(exe.parents) >= 3:
            found.append(exe.parents[2].parent / "motore" / "rgss-switch.zip")
    else:
        found.append(here.parent / "motore" / "rgss-switch.zip")
    for path in found:
        if path.is_file() and path.stat().st_size > 1_000_000:
            return path
    return None

from engine import (
    GRAFICA,
    PrepareError,
    check_game,
    check_release,
    default_output_dir,
    describe,
    detect_game,
    ensure_release,
    load_settings,
    newer_motor_note,
    button_updates,
    patch_cfg_keys,
    APP_VERSION,
    prepare,
    read_cfg,
    save_entries,
    save_settings,
    support_dir,
)
from i18n import lang_name, tr
from nsp import create_nsp, nsp_line


def reveal(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", str(path)], check=False)
    elif sys.platform == "win32":
        subprocess.run(["explorer", "/select,", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path.parent)], check=False)


def run_cli(argv: list) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a PC fan game so Fan Porter can open it on the Switch."
    )
    parser.add_argument("--gioco", required=True, help="PC game folder (the one with Game.ini).")
    parser.add_argument("--uscita", help="Where to create switch/. Without it, Desktop/Fan Porter.")
    parser.add_argument("--consegna", help="Engine folder, if you do not want the bundled one.")
    parser.add_argument("--modo", choices=("zip", "cartelle"), default="zip")
    parser.add_argument("--grafica", choices=tuple(GRAFICA), default="intera")
    parser.add_argument("--solo-rileva", action="store_true")
    args = parser.parse_args(argv)

    game = Path(args.gioco)
    problem = check_game(game)
    if problem:
        print(problem, file=sys.stderr)
        return 1
    if args.consegna:
        release = Path(args.consegna)
        problem = check_release(release)
        if problem:
            print(problem, file=sys.stderr)
            return 1
    else:
        release = ensure_release(support_dir() / "motore", print, zip_path=motor_zip())
    info = detect_game(game, release)
    print(describe(info))
    if args.solo_rileva:
        return 0
    output = Path(args.uscita) if args.uscita else default_output_dir()
    prepare(info, release, output, args.modo, print, remember=True, scala=args.grafica, explicit=True)
    return 0


def _drop_paths(widget, data: str) -> list:
    try:
        items = list(widget.tk.splitlist(data))
    except Exception:
        items = [data]
    paths = []
    for item in items:
        text = str(item).strip()
        if text.startswith("{") and text.endswith("}"):
            text = text[1:-1]
        if text.startswith("file://"):
            from urllib.parse import unquote, urlparse
            text = unquote(urlparse(text).path)
        if text:
            paths.append(Path(text))
    return paths


def run_gui() -> None:
    enable_windows_dpi()
    from ui import register_fonts
    register_fonts()
    import tkinter as tk
    from tkinter import filedialog, messagebox

    try:
        from tkinterdnd2 import DND_FILES, TkinterDnD
        root = TkinterDnD.Tk()
        can_drop = True
    except Exception:
        root = tk.Tk()
        can_drop = False
        DND_FILES = None

    root.title(f"Fan Porter {APP_VERSION}")
    try:
        here = Path(getattr(sys, "_MEIPASS")) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
        png = here / "fan-porter.png"
        if not png.is_file():
            png = here / "assets" / "fan-porter-app.png"
        if png.is_file():
            icon_img = tk.PhotoImage(file=str(png))
            root.iconphoto(True, icon_img)
            root._fan_porter_icon = icon_img
        ico = here / "fan-porter.ico"
        if sys.platform == "win32" and ico.is_file():
            root.iconbitmap(str(ico))
    except Exception:
        pass
    root.geometry("1120x860")
    root.minsize(860, 560)
    stored, stored_note = load_settings()
    lingua = stored.get("lingua") if stored.get("lingua") in ("en", "it") else "en"
    output_var = tk.StringVar(value=stored.get("uscita") or str(default_output_dir()))
    if stored.get("finestra"):
        try:
            root.geometry(stored["finestra"])
        except Exception:
            pass
    state = {
        "busy": False, "release": None, "waiting": None,
        "title": tr(lingua, "prepare_a_game"), "lines": [], "photo": None,
        "page": "prepara", "game": None, "info": None,
        "grafica": "intera", "explicit": False, "explicit_lingua": False,
        "explicit_comandi": False,
        "famiglia": "", "lingua": lingua,
        "tema": stored.get("tema") if stored.get("tema") in ("chiaro", "scuro") else "scuro",
        "divisore": stored.get("divisore") if isinstance(stored.get("divisore"), int) else 360,
        "size": "", "icon": None,
    }
    if stored_note:
        state["lines"].append(stored_note)
    events: queue.Queue = queue.Queue()
    ui_box = {}

    def paint(_event=None) -> None:
        refresh = ui_box.get("refresh")
        if refresh:
            refresh()

    def say(key: str) -> str:
        return tr(state["lingua"], key)

    def write(line: str) -> None:
        state["lines"].append(line)
        del state["lines"][:-40]
        sink = ui_box.get("write_log")
        if sink:
            sink(line)
        paint()

    def choose_output() -> None:
        chosen = filedialog.askdirectory(title=say("choose_output"))
        if chosen:
            output_var.set(chosen)
            paint()

    def set_drop_text(text: str) -> None:
        state["title"] = text.replace("\n", " ")
        paint()

    def pump() -> None:
        try:
            while True:
                kind, payload = events.get_nowait()
                if kind == "line":
                    write(payload)
                elif kind == "motor":
                    state["release"] = payload
                    set_drop_text(say("prepare_a_game"))
                    waiting = state["waiting"]
                    prepare_after = state.get("prepare_when_ready")
                    state["waiting"] = None
                    state["prepare_when_ready"] = False
                    if waiting:
                        select_game(waiting)
                        if prepare_after:
                            start_prepare(waiting)
                elif kind == "reveal":
                    reveal(Path(payload))
                elif kind == "size":
                    state["size"] = payload
                    paint()
                elif kind == "progress":
                    pct, step = payload
                    state["progress"] = pct
                    state["progress_step"] = step
                    setter = ui_box.get("set_progress")
                    if setter:
                        setter(pct, step)
                    else:
                        paint()
                elif kind == "done":
                    state["busy"] = False
                    state["progress"] = 0
                    state["progress_step"] = ""
                    set_drop_text(say("prepare_a_game"))
                    messagebox.showinfo(say("ready_title"), payload)
                elif kind == "error":
                    state["busy"] = False
                    state["progress"] = 0
                    state["progress_step"] = ""
                    set_drop_text(say("prepare_a_game"))
                    messagebox.showerror(say("not_prepared"), payload)
                elif kind == "app_update":
                    offer_update(payload)
                elif kind == "app_updated":
                    messagebox.showinfo(say("app_update_title"), say("app_updated"))
                    import updater
                    try:
                        updater.restart()
                    finally:
                        remember_window()
                    return
        except queue.Empty:
            pass
        root.after(80, pump)

    def set_page(name: str) -> None:
        state["page"] = name
        paint()

    def action_label() -> str:
        info = state.get("info")
        if info is None:
            return say("prepare")
        final = Path(output_var.get()) / "switch" / info.slug / f"{info.slug}.nro"
        return say("update") if final.is_file() else say("prepare")

    def game_dir():
        info = state.get("info")
        if info is None:
            return None
        return Path(output_var.get()) / "switch" / info.slug

    def select_game(path: Path) -> None:
        if path.is_file():
            path = path.parent
        if state["busy"]:
            return
        problem = check_game(path)
        if problem:
            messagebox.showerror(say("not_a_game"), problem)
            return
        release = state["release"]
        if release is None:
            state["waiting"] = path
            state["prepare_when_ready"] = False
            write(say("motor_wait_read"))
            return
        info = detect_game(path, release)
        state["game"] = path
        state["info"] = info
        state["page"] = "prepara"
        state["explicit"] = False
        state["icon"] = None
        data, _note = load_settings()
        slot = (data.get("games") or {}).get(info.slug) or {}
        state["famiglia"] = slot.get("famiglia") or ""
        state["grafica"] = slot.get("grafica") if slot.get("grafica") in GRAFICA else "intera"
        existing = read_cfg(Path(output_var.get()) / "switch" / info.slug / "porter.cfg")
        if existing.get("scala") in GRAFICA:
            state["grafica"] = existing["scala"]
        state["explicit_comandi"] = False
        loader = ui_box.get("load_controls")
        if loader:
            loader(existing)
        set_drop_text(info.name)
        write("")
        write(describe(info))
        for warning in info.warnings:
            write(warning)
        write(say("handheld_borders"))

        def measure() -> None:
            total = 0
            for base, _dirs, files in os.walk(path):
                for name in files:
                    try:
                        total += os.path.getsize(os.path.join(base, name))
                    except OSError:
                        pass
            events.put(("size", f"{total / (1024 * 1024):.0f} MB"))

        threading.Thread(target=measure, daemon=True).start()

    def start_from_button() -> None:
        if state.get("game") is None or state.get("busy"):
            return
        start_prepare(state["game"])

    def start_prepare(game: Path) -> None:
        release = state["release"]
        if release is None:
            state["waiting"] = game
            state["prepare_when_ready"] = True
            write(say("motor_wait_prepare"))
            return
        if state["busy"]:
            write(say("already_preparing"))
            return
        problem = check_game(game)
        if problem:
            messagebox.showerror(say("not_a_game"), problem)
            return
        info = state.get("info") or detect_game(game, release)
        if state.get("icon"):
            info.icon_path = Path(state["icon"])
        output = Path(output_var.get())
        state["busy"] = True
        state["progress"] = 0
        state["progress_step"] = "progress_working"
        set_drop_text(info.name)
        write("")
        write(describe(info))
        write("")
        paint()

        def work() -> None:
            try:
                dest = prepare(
                    info, release, output, "zip",
                    lambda line: events.put(("line", line)),
                    remember=True,
                    scala=state["grafica"],
                    explicit=state["explicit"],
                    lingua=state["lingua"],
                    explicit_lingua=state["explicit_lingua"],
                    pc=ui_box["pc"]() if ui_box.get("pc") else None,
                    explicit_comandi=bool(ui_box.get("pc")),
                    turbo=ui_box["turbo"]() if ui_box.get("turbo") else None,
                    contatore=ui_box["contatore"]() if ui_box.get("contatore") else None,
                    registro=ui_box["registro"]() if ui_box.get("registro") else None,
                    menu_apri=ui_box["menu_apri"]() if ui_box.get("menu_apri") else None,
                    croce=ui_box["croce"]() if ui_box.get("croce") else None,
                    tema=ui_box["tema"]() if ui_box.get("tema") else None,
                    progress=lambda pct, step: events.put(("progress", (pct, step))),
                )
                state["explicit_lingua"] = False
                switch_dir = dest.parent
                events.put(("reveal", switch_dir))
                events.put(("done", say("done_body").format(folder=switch_dir, slug=info.slug)))
                events.put(("line", say("folder_to_copy").format(folder=switch_dir)))
            except PrepareError as exc:
                events.put(("line", str(exc)))
                events.put(("error", str(exc)))
            except Exception:
                text = traceback.format_exc()
                (support_dir() / "ultimo-errore.txt").write_text(text, encoding="utf-8")
                events.put(("line", text))
                events.put(("error", say("went_wrong")))

        threading.Thread(target=work, daemon=True).start()

    def take_folder(path: Path) -> None:
        select_game(path)

    def choose_icon() -> None:
        chosen = filedialog.askopenfilename(
            title=say("choose_icon"),
            filetypes=[(say("images"), "*.png *.jpg *.jpeg"), (say("all_files"), "*.*")],
        )
        if chosen:
            state["icon"] = Path(chosen)
            paint()

    def pick_grafica(name: str) -> None:
        state["grafica"] = name
        state["explicit"] = True
        info = state.get("info")
        if info is not None:
            data, _note = load_settings()
            slot = data.setdefault("games", {}).setdefault(info.slug, {})
            slot["grafica"] = name
            save_settings(data)
        write(say("gfx_picked").format(name=name))
        paint()

    def save_theme(name: str) -> None:
        state["tema"] = name if name in ("chiaro", "scuro") else "scuro"
        data, _note = load_settings()
        data["tema"] = state["tema"]
        save_settings(data)

    def set_language(lang: str) -> None:
        if lang not in ("en", "it") or lang == state["lingua"]:
            return
        state["lingua"] = lang
        state["explicit_lingua"] = True
        data, _note = load_settings()
        data["lingua"] = lang
        save_settings(data)
        paint()

    def set_family(name: str) -> None:
        state["famiglia"] = name if name in ("ruby18", "ruby31", "rgss1") else ""
        info = state.get("info")
        if info is not None:
            data, _note = load_settings()
            slot = data.setdefault("games", {}).setdefault(info.slug, {})
            if state["famiglia"]:
                slot["famiglia"] = state["famiglia"]
            else:
                slot.pop("famiglia", None)
            save_settings(data)
        paint()

    def controls_changed() -> None:
        state["explicit_comandi"] = True
        info = state.get("info")
        if info is None:
            return
        path = Path(output_var.get()) / "switch" / info.slug / "porter.cfg"
        if path.is_file():
            patch_cfg_keys(path, {
                "pc": ui_box["pc"](),
                "turbo": ui_box["turbo"]() if ui_box.get("turbo") else "0",
                "contatore": ui_box["contatore"]() if ui_box.get("contatore") else "0",
                "registro": ui_box["registro"]() if ui_box.get("registro") else "0",
                "menu_apri": ui_box["menu_apri"]() if ui_box.get("menu_apri") else "meno",
                "croce": ui_box["croce"]() if ui_box.get("croce") else "0",
                "tema": ui_box["tema"]() if ui_box.get("tema") else "scuro",
            })

    def copy_saves() -> None:
        folder = game_dir()
        if folder is None:
            messagebox.showinfo(say("saves_title"), say("pick_a_game"))
            return
        entries = save_entries(folder)
        if not entries:
            messagebox.showinfo(say("saves_title"), say("no_save").format(folder=folder))
            return
        chosen = filedialog.askdirectory(title=say("copy_saves_to"))
        if not chosen:
            return
        dest = Path(chosen)
        for item in entries:
            target = dest / item.name
            if item.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
        messagebox.showinfo(say("saves_title"), say("copied_to").format(dest=dest))

    def restore_saves() -> None:
        info = state.get("info")
        folder = game_dir()
        if info is None or folder is None:
            messagebox.showinfo(say("saves_title"), say("pick_a_game"))
            return
        root_backup = Path(output_var.get()) / "backup"
        matches = sorted(root_backup.glob(info.slug + "-*")) if root_backup.is_dir() else []
        if not matches:
            messagebox.showinfo(say("saves_title"), say("no_backup"))
            return
        latest = matches[-1]
        if not messagebox.askyesno(say("restore_title"), say("restore_ask").format(name=latest.name)):
            return
        folder.mkdir(parents=True, exist_ok=True)
        for item in latest.iterdir():
            target = folder / item.name
            if item.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
        write(say("restored").format(name=latest.name))

    def delete_saves() -> None:
        folder = game_dir()
        if folder is None:
            messagebox.showinfo(say("saves_title"), say("pick_a_game"))
            return
        entries = save_entries(folder)
        if not entries:
            messagebox.showinfo(say("saves_title"), say("nothing_to_delete"))
            return
        names = "\n".join(item.name for item in entries)
        if not messagebox.askyesno(say("delete_title"), say("delete_ask").format(names=names)):
            return
        for item in entries:
            if item.is_dir():
                shutil.rmtree(item)
            elif item.is_file():
                item.unlink()
        write(say("deleted"))

    def check_motor() -> None:
        write(say("checking_engine"))

        def work() -> None:
            note = newer_motor_note()
            events.put(("line", note or say("github_down")))

        threading.Thread(target=work, daemon=True).start()

    def make_nsp() -> None:
        info = state.get("info")
        release = state["release"]
        if info is None or release is None:
            messagebox.showinfo("NSP", say("nsp_need_game"))
            return
        icon = release / "motor" / "icono.jpg"
        if state.get("icon"):
            icon = Path(state["icon"])

        def work() -> None:
            try:
                made = create_nsp(info, release, Path(output_var.get()), icon, lambda line: events.put(("line", line)))
                events.put(("line", f"NSP: {made}"))
                events.put(("done", say("nsp_made").format(path=made, slug=info.slug)))
            except PrepareError as exc:
                events.put(("error", str(exc)))
            except Exception:
                events.put(("error", say("nsp_failed")))

        threading.Thread(target=work, daemon=True).start()

    def remember_window() -> None:
        data, _note = load_settings()
        data["uscita"] = output_var.get()
        data["finestra"] = root.geometry()
        data["lingua"] = state["lingua"]
        data["tema"] = ui_box["tema"]() if ui_box.get("tema") else state.get("tema") or "scuro"
        split = ui_box.get("divisore")
        if split:
            try:
                data["divisore"] = int(split())
            except (TypeError, tk.TclError):
                pass
        save_settings(data)
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", remember_window)

    def choose_game(_event=None) -> None:
        if state["busy"]:
            return
        chosen = filedialog.askdirectory(title=say("choose_game_folder"))
        if chosen:
            take_folder(Path(chosen))

    def on_drop(event) -> None:
        paths = _drop_paths(root, event.data)
        if paths:
            take_folder(paths[0])

    from ui import mount
    ui_box.update(mount(root, state, output_var, {
        "prepare": start_from_button,
        "prepare_label": action_label,
        "choose_game": choose_game,
        "choose_output": choose_output,
        "choose_icon": choose_icon,
        "grafica": pick_grafica,
        "language": set_language,
        "family": set_family,
        "controls": controls_changed,
        "copy_saves": copy_saves,
        "restore_saves": restore_saves,
        "delete_saves": delete_saves,
        "nsp": make_nsp,
        "nsp_line": lambda: nsp_line(state["lingua"]),
        "check": check_motor,
        "save_theme": save_theme,
    }))
    if can_drop:
        for widget in ui_box["drops"]:
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", on_drop)
            except Exception:
                pass

    def load_motor() -> None:
        try:
            release = ensure_release(
                support_dir() / "motore",
                lambda line: events.put(("line", line)),
                zip_path=motor_zip(),
            )
            events.put(("motor", release))
        except Exception as exc:
            events.put(("line", str(exc)))
            events.put(("error", say("motor_fail").format(detail=exc)))

    def check_app_update() -> None:
        try:
            import updater
            found = updater.newer()
        except Exception as exc:
            events.put(("line", say("app_update_offline").format(detail=exc)))
            return
        if found:
            events.put(("app_update", found))

    def offer_update(manifest: dict) -> None:
        if state["busy"]:
            events.put(("line", say("app_update_later")))
            return
        ask = say("app_update_ask").format(version=manifest.get("versione", ""), build=manifest["build"])
        if not messagebox.askyesno(say("app_update_title"), ask):
            return
        state["busy"] = True
        write(say("app_updating"))

        def work() -> None:
            try:
                import updater
                updater.apply(manifest)
                events.put(("app_updated", manifest["build"]))
            except Exception as exc:
                events.put(("error", say("app_update_failed").format(detail=exc)))

        threading.Thread(target=work, daemon=True).start()

    if motor_zip():
        set_drop_text(say("motor_local"))
    else:
        set_drop_text(say("motor_download"))
    threading.Thread(target=load_motor, daemon=True).start()
    if sys.platform == "win32":
        threading.Thread(target=check_app_update, daemon=True).start()
    root.after(80, pump)
    root.after(30, paint)
    root.after(300, paint)
    root.mainloop()


def main() -> int:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if len(sys.argv) > 1:
        try:
            return run_cli(sys.argv[1:])
        except PrepareError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    try:
        run_gui()
    except Exception:
        text = traceback.format_exc()
        print(text, file=sys.stderr)
        report_crash(text)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
