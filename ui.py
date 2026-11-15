"""Finestra di Fan Porter. Controlli nativi, non un disegno stirato."""

from __future__ import annotations

import sys
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import ttk

from engine import APP_VERSION
from i18n import tr

BG = "#D6E8FA"
SIDE = "#EAF4FF"
CARD = "#FFFFFF"
FIELD = "#FFFFFF"
LINE = "#C5D9EE"
INK = "#183058"
MUTED = "#6080A8"
ACCENT = "#3FA9FF"
ON_INK = "#FFFFFF"
NAV_TOP = "#3FA9FF"
NAV_BOT = "#2A8CE6"
BTN_TOP = "#52B5FF"
BTN_BOT = "#2A8CE6"
BTN_INK = "#04132E"
HOVER = "#D7EBFC"
RAIL_BTN = "#FFFFFF"
RAIL_HOT = "#CDE4F8"
NAV_HI = "#7CC6FF"
DISABLED = "#D7E4F2"

LIGHT = {
    "BG": BG, "SIDE": SIDE, "CARD": CARD, "FIELD": FIELD, "LINE": LINE,
    "INK": INK, "MUTED": MUTED, "ACCENT": ACCENT, "ON_INK": ON_INK,
    "NAV_TOP": NAV_TOP, "NAV_BOT": NAV_BOT, "BTN_TOP": BTN_TOP, "BTN_BOT": BTN_BOT,
    "BTN_INK": BTN_INK, "HOVER": HOVER, "RAIL_BTN": RAIL_BTN, "RAIL_HOT": RAIL_HOT,
    "NAV_HI": NAV_HI, "DISABLED": DISABLED,
}
DARK = {
    "BG": "#0C1424", "SIDE": "#101E34", "CARD": "#162640", "FIELD": "#1C304E",
    "LINE": "#284878", "INK": "#EAF1FF", "MUTED": "#8FA3C7", "ACCENT": "#3FA9FF",
    "ON_INK": "#FFFFFF", "NAV_TOP": "#3FA9FF", "NAV_BOT": "#2A8CE6",
    "BTN_TOP": "#52B5FF", "BTN_BOT": "#2A8CE6", "BTN_INK": "#04132E",
    "HOVER": "#1C4070", "RAIL_BTN": "#1C304E", "RAIL_HOT": "#284878",
    "NAV_HI": "#7CC6FF", "DISABLED": "#1A283C",
}


def _install_palette(name: str) -> None:
    pack = DARK if name == "scuro" else LIGHT
    module = globals()
    for key, value in pack.items():
        module[key] = value


def _palette_map(src: str, dst: str) -> dict:
    before = DARK if src == "scuro" else LIGHT
    after = DARK if dst == "scuro" else LIGHT
    return {before[key]: after[key] for key in before}


def _style_chrome(style, family: str) -> None:
    style.configure(".", background=BG, foreground=INK, fieldbackground=CARD, bordercolor=LINE)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=INK)
    style.configure("TButton", background=RAIL_BTN, foreground=INK, borderwidth=0, focuscolor=BG, padding=6, font=(family, 12))
    style.map("TButton", background=[("active", RAIL_HOT), ("disabled", DISABLED)], foreground=[("disabled", MUTED)])
    style.configure("TRadiobutton", background=BG, foreground=INK, font=(family, 12))
    style.map("TRadiobutton", background=[("active", BG)], foreground=[("active", INK)])
    style.configure("TCheckbutton", background=BG, foreground=INK, font=(family, 12))
    style.map("TCheckbutton", background=[("active", BG)], foreground=[("active", INK)])
    style.configure("TCombobox", fieldbackground=FIELD, background=CARD, foreground=INK, arrowcolor=ACCENT, font=(family, 12))
    style.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", INK)])
    style.configure("TMenubutton", background=FIELD, foreground=INK, arrowcolor=ACCENT, padding=4, font=(family, 12))
    style.configure("TScrollbar", background=CARD, troughcolor=BG, arrowcolor=ACCENT)
    style.configure(
        "Fan.Horizontal.TProgressbar",
        troughcolor=FIELD,
        background=ACCENT,
        darkcolor=NAV_BOT,
        lightcolor=BTN_TOP,
        bordercolor=LINE,
        thickness=12,
    )


def _recolor_tree(widget, mapping: dict) -> None:
    if isinstance(widget, ChromeButton) and widget._outer in mapping:
        widget._outer = mapping[widget._outer]
    for opt in (
        "bg", "fg", "highlightbackground", "highlightcolor", "insertbackground",
        "selectbackground", "selectforeground", "activebackground", "activeforeground",
        "troughcolor",
    ):
        try:
            value = str(widget.cget(opt))
        except tk.TclError:
            continue
        if value in mapping:
            try:
                widget.configure({opt: mapping[value]})
            except tk.TclError:
                pass
    spec = getattr(widget, "_soften", None)
    if spec:
        radius, fill, outer = spec
        widget._soften = (radius, mapping.get(fill, fill), mapping.get(outer, outer))
        _apply_soften(widget)
    if isinstance(widget, (NavItem, ChromeButton, PadMark)):
        widget.redraw()
    for child in widget.winfo_children():
        _recolor_tree(child, mapping)

# Codice del motore, nome sul pad. Guida di rgss-switch: A/B = C/B, Y = A, ZL/ZR = Y/Z.
PAD = (
    ("C", "A"),
    ("B", "B"),
    ("X", "X"),
    ("A", "Y"),
    ("Y", "ZL"),
    ("Z", "ZR"),
    ("L", "L"),
    ("R", "R"),
)
PAD_NAME = dict(PAD)
PAD_CODE = {name: code for code, name in PAD}
DPAD = (("UP", "↑"), ("DOWN", "↓"), ("LEFT", "←"), ("RIGHT", "→"))
DPAD_NAME = dict(DPAD)
ACTIONS = (
    ("accetta", "act_confirm", "C"),
    ("indietro", "act_back", "B"),
    ("corsa", "act_run", "A"),
    ("tasto_a", "act_key_a", "X"),
    ("tasto_s", "act_key_s", "Y"),
    ("tasto_d", "act_key_d", "Z"),
    ("elle", "act_l", "L"),
    ("erre", "act_r", "R"),
)
KEY_GROUPS = (
    ("keys_function", [f"F{number}" for number in range(1, 13)]),
    ("keys_am", [chr(code) for code in range(ord("A"), ord("M") + 1)]),
    ("keys_nz", [chr(code) for code in range(ord("N"), ord("Z") + 1)]),
    ("keys_editing", ["Esc", "Enter", "Space", "Shift", "Ctrl", "Alt", "Tab"]),
)
ALL_KEYS = [key for _name, keys in KEY_GROUPS for key in keys]
# Default dei fan game: A è la lettera C, B è la X, X è la Z. Si possono cambiare.
SUGGESTED = {"C": "C", "B": "X", "X": "Z"}
FAMILIES = (("", "family_auto"), ("ruby18", "family_ruby18"), ("ruby31", "family_ruby31"), ("rgss1", "family_rgss1"))


def _asset_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / "assets"
    here = Path(__file__).resolve().parent
    if (here / "assets").is_dir():
        return here / "assets"
    return here / "forwarder" / "assets"


def register_fonts() -> None:
    """Load Inter and Bebas Neue before Tk starts. Tk does not see fonts added later."""
    folder = _asset_dir() / "fonts"
    if not folder.is_dir():
        return
    paths = [path for path in folder.glob("*.ttf") if path.is_file()]
    if not paths:
        return
    try:
        import ctypes
        import ctypes.util
        if sys.platform == "darwin":
            core_f = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
            core_t = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreText"))
            core_f.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
            core_f.CFURLCreateFromFileSystemRepresentation.argtypes = [
                ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_bool,
            ]
            core_t.CTFontManagerRegisterFontsForURL.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
            core_t.CTFontManagerRegisterFontsForURL.restype = ctypes.c_bool
            for path in paths:
                data = str(path).encode()
                url = core_f.CFURLCreateFromFileSystemRepresentation(None, data, len(data), False)
                core_t.CTFontManagerRegisterFontsForURL(url, 1, None)
        elif sys.platform == "win32":
            gdi = ctypes.windll.gdi32
            for path in paths:
                gdi.AddFontResourceExW(str(path), 0x10, 0)
    except Exception:
        return


def _family() -> str:
    names = set(tkfont.families())
    for candidate in ("Inter", ".AppleSystemUIFont", "Segoe UI", "Helvetica Neue", "Helvetica"):
        if candidate in names:
            return candidate
    return "TkDefaultFont"


def _semibold() -> str:
    names = set(tkfont.families())
    if "Inter SemiBold" in names:
        return "Inter SemiBold"
    return _family()


def _display() -> str:
    names = set(tkfont.families())
    for candidate in ("Bebas Neue", "BebasNeue", "Impact", "Arial Narrow"):
        if candidate in names:
            return candidate
    return _family()


def _rgb(color: str) -> tuple:
    text = color.lstrip("#")
    return tuple(int(text[index:index + 2], 16) for index in (0, 2, 4))


_PLATES: dict = {}


def _plate(width: int, height: int, radius: int, top: str, bottom: str, bar: str = "", highlight: str = ""):
    from PIL import Image, ImageTk
    key = (width, height, radius, top, bottom, bar, highlight)
    cached = _PLATES.get(key)
    if cached is not None:
        return cached
    image = Image.new("RGBA", (max(width, 1), max(height, 1)), (0, 0, 0, 0))
    pixels = image.load()
    start = _rgb(top)
    end = _rgb(bottom)
    bar_rgb = _rgb(bar) if bar else None
    hi_rgb = _rgb(highlight) if highlight else None
    wide, tall = image.size
    curve = min(radius, wide // 2, tall // 2)
    for y in range(tall):
        blend = 0 if tall == 1 else y / (tall - 1)
        color = tuple(int(start[channel] + (end[channel] - start[channel]) * blend) for channel in range(3))
        inset = 0
        if curve and (y < curve or y >= tall - curve):
            dy = curve - y if y < curve else y - (tall - 1 - curve)
            inside = curve * curve - dy * dy
            inset = curve if inside <= 0 else curve - int(inside ** 0.5)
        for x in range(inset, wide - inset):
            if hi_rgb and y == inset:
                pixels[x, y] = hi_rgb + (255,)
            elif bar_rgb and x < inset + 3:
                pixels[x, y] = bar_rgb + (255,)
            else:
                pixels[x, y] = color + (255,)
    photo = ImageTk.PhotoImage(image)
    if len(_PLATES) > 48:
        _PLATES.clear()
    _PLATES[key] = photo
    return photo


def _corner(radius: int, fill: str, outer: str, corner: str):
    from PIL import Image, ImageTk
    image = Image.new("RGB", (radius, radius), _rgb(outer))
    pixels = image.load()
    ink = _rgb(fill)
    for y in range(radius):
        for x in range(radius):
            if corner == "nw":
                dx, dy = radius - 1 - x, radius - 1 - y
            elif corner == "ne":
                dx, dy = x, radius - 1 - y
            elif corner == "sw":
                dx, dy = radius - 1 - x, y
            else:
                dx, dy = x, y
            if dx * dx + dy * dy <= radius * radius:
                pixels[x, y] = ink
    return ImageTk.PhotoImage(image)


def soften(widget, radius: int, fill: str, outer: str) -> None:
    """Square widget, round silhouette. The caps only cover the corner padding."""
    widget._soften = (radius, fill, outer)
    _apply_soften(widget)


def _apply_soften(widget) -> None:
    spec = getattr(widget, "_soften", None)
    if spec is None:
        return
    radius, fill, outer = spec
    widget.configure(highlightthickness=0)
    for cap in getattr(widget, "_round_cap_widgets", ()):
        cap.destroy()
    photos = []
    caps = []
    spots = {
        "nw": {"x": 0, "y": 0},
        "ne": {"relx": 1.0, "x": -radius, "y": 0, "anchor": "nw"},
        "sw": {"x": 0, "rely": 1.0, "y": -radius, "anchor": "nw"},
        "se": {"relx": 1.0, "rely": 1.0, "x": -radius, "y": -radius, "anchor": "nw"},
    }
    for corner, spot in spots.items():
        photo = _corner(radius, fill, outer, corner)
        photos.append(photo)
        cap = tk.Label(widget, image=photo, bd=0, bg=fill, highlightthickness=0)
        cap.place(width=radius, height=radius, **spot)
        caps.append(cap)
    widget._round_caps = photos
    widget._round_cap_widgets = caps


class NavItem(tk.Canvas):
    def __init__(self, parent, command, ui_font: str):
        super().__init__(parent, height=32, bg=SIDE, highlightthickness=0, bd=0, cursor="hand2")
        self._command = command
        self._font = ui_font
        self._label = ""
        self._on = False
        self._hot = False
        self._photo = None
        self.pack(fill="x", pady=1)
        self.bind("<Configure>", lambda _event: self.redraw())
        self.bind("<Button-1>", lambda _event: self._command())
        self.bind("<Enter>", lambda _event: self._hover(True))
        self.bind("<Leave>", lambda _event: self._hover(False))

    def _hover(self, hot: bool) -> None:
        self._hot = hot
        self.redraw()

    def configure(self, cnf=None, **kw):
        if cnf:
            kw.update(cnf)
        text = kw.pop("text", None)
        if kw:
            super().configure(**kw)
        if text is not None:
            self._label = text
        self.redraw()

    config = configure

    def set_on(self, on: bool) -> None:
        self._on = on
        self.redraw()

    def redraw(self) -> None:
        width = self.winfo_width()
        if width < 20:
            return
        height = 36
        self.delete("all")
        super().configure(bg=SIDE)
        if self._on:
            self._photo = _plate(width, height, 8, NAV_TOP, NAV_BOT, bar=ACCENT, highlight=NAV_HI)
            self.create_image(0, 0, image=self._photo, anchor="nw")
            ink = ON_INK
        elif self._hot:
            self._photo = _plate(width, height, 8, HOVER, HOVER)
            self.create_image(0, 0, image=self._photo, anchor="nw")
            ink = INK
        else:
            ink = MUTED
        self.create_text(16, height // 2, text=self._label, anchor="w", fill=ink, font=(self._font, 13))


class ChromeButton(tk.Canvas):
    def __init__(self, parent, command, role: str = "rail", outer: str = SIDE, stretch: bool = True):
        height = 44 if role == "primary" else 34
        super().__init__(
            parent, height=height, bg=outer, highlightthickness=0, bd=0,
            cursor="hand2", width=120,
        )
        self._command = command
        self._role = role
        self._outer = outer
        self._stretch = stretch
        self._label = ""
        self._enabled = True
        self._hot = False
        self._photo = None
        self.bind("<Configure>", lambda _event: self.redraw())
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", lambda _event: self._hover(True))
        self.bind("<Leave>", lambda _event: self._hover(False))

    def _hover(self, hot: bool) -> None:
        self._hot = hot
        self.redraw()

    def _click(self, _event=None) -> None:
        if self._enabled and self._command:
            self._command()

    def configure(self, cnf=None, **kw):
        if cnf:
            kw.update(cnf)
        text = kw.pop("text", None)
        state = kw.pop("state", None)
        if text is not None:
            self._label = text
            if not self._stretch:
                super().configure(width=max(108, len(text) * 8 + 36))
        if state is not None:
            self._enabled = state != "disabled"
            super().configure(cursor="hand2" if self._enabled else "arrow")
        if kw:
            super().configure(**kw)
        self.redraw()

    config = configure

    def redraw(self) -> None:
        width = self.winfo_width() if self._stretch else int(self.cget("width"))
        if width < 20:
            return
        height = 44 if self._role == "primary" else 34
        self.delete("all")
        super().configure(bg=self._outer)
        shown = self._label.upper() if self._role == "primary" else self._label
        if self._role == "primary" and self._enabled:
            top, bottom = (BTN_BOT, BTN_TOP) if self._hot else (BTN_TOP, BTN_BOT)
            self._photo = _plate(width, height, 10, top, bottom, highlight=NAV_HI)
            ink = BTN_INK
            font = (_display(), 20)
        elif self._role == "primary":
            self._photo = _plate(width, height, 10, LINE, LINE)
            ink = MUTED
            font = (_display(), 20)
        else:
            fill = RAIL_HOT if self._hot else RAIL_BTN
            self._photo = _plate(width, height, 8, fill, fill)
            ink = INK
            font = (_semibold(), 12)
        self.create_image(0, 0, image=self._photo, anchor="nw")
        self.create_text(width // 2, height // 2, text=shown, fill=ink, font=font)


class PadMark(tk.Canvas):
    """Cerchio = tasto Switch. Quadrato = tasto PC."""

    def __init__(self, parent, text: str, kind: str = "switch", size: int = 36):
        width = size if kind == "switch" else max(size + 12, 52)
        super().__init__(parent, width=width, height=size, bg=BG, highlightthickness=0, bd=0)
        self._text = text
        self._kind = kind
        self._size = size
        self._width = width
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        super().configure(bg=BG)
        size = self._size
        width = self._width
        if self._kind == "switch":
            self.create_oval(2, 2, size - 2, size - 2, outline=ACCENT, width=2, fill=CARD)
            self.create_text(size // 2, size // 2, text=self._text, fill=INK, font=(_semibold(), 11))
        else:
            self.create_rectangle(2, 2, width - 2, size - 2, outline=LINE, width=2, fill=CARD)
            self.create_text(width // 2, size // 2, text=self._text, fill=INK, font=(_family(), 11))


def _logo_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / "assets" / "logo-mark.png"
    here = Path(__file__).resolve().parent
    mark = here / "assets" / "logo-mark.png"
    return mark if mark.is_file() else here / "assets" / "logo-line.png"


def _wheel_steps(delta: int) -> int:
    if not delta:
        return 0
    if abs(delta) >= 120:
        return -int(delta / 120) or (-1 if delta > 0 else 1)
    return -int(delta)


def _inside(widget, parent) -> bool:
    while widget is not None:
        if widget is parent:
            return True
        widget = getattr(widget, "master", None)
    return False


def _badge_colors() -> tuple[str, str]:
    """Quadrato scuro e marchio chiaro. Sul tema scuro il riquadro si alza un poco."""
    if SIDE == DARK["SIDE"]:
        return "#1C4070", "#C5E4FF"
    return "#0C1424", "#8FD0FF"


def _logo_badge(source, size: int, fill: str, tint: str):
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    radius = max(size // 5, 6)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=_rgb(fill) + (255,))
    if source is None:
        return image
    pad = max(size // 6, 4)
    inner = max(size - pad * 2, 8)
    scale = min(inner / max(source.width, 1), inner / max(source.height, 1))
    mw = max(int(round(source.width * scale)), 1)
    mh = max(int(round(source.height * scale)), 1)
    resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)
    mark = source.resize((mw, mh), resample).convert("RGBA")
    rgb = _rgb(tint)
    pixels = mark.load()
    for y in range(mh):
        for x in range(mw):
            _, _, _, alpha = pixels[x, y]
            pixels[x, y] = (*rgb, alpha)
    image.paste(mark, ((size - mw) // 2, (size - mh) // 2), mark)
    return image


def _logo(parent, bg: str = BG) -> tk.Widget:
    """Marchio :D nella stessa altezza del nome, dentro un quadrato arrotondato."""
    row = tk.Frame(parent, bg=bg)
    path = _logo_path()
    source = None
    if path.is_file():
        try:
            from PIL import Image

            source = Image.open(path).convert("RGBA")
        except Exception:
            source = None
    title = tk.Label(row, text="Fan Porter", bg=bg, fg=INK, font=(_display(), 22), anchor="w")
    version = tk.Label(row, text=APP_VERSION, bg=bg, fg=MUTED, font=(_display(), 12), anchor="w")
    title.update_idletasks()
    size = max(min(int(title.winfo_reqheight() * 0.78), 30), 22)
    mark = tk.Label(row, bg=bg, bd=0, highlightthickness=0)
    mark.pack(side="left")
    title.pack(side="left", padx=(8, 0))
    version.pack(side="left", padx=(8, 0))

    def paint(bg_hex: str = "", ink_hex: str = "") -> None:
        from PIL import ImageTk

        bg_hex = bg_hex or SIDE
        ink_hex = ink_hex or INK
        fill, tint = _badge_colors()
        row.configure(bg=bg_hex)
        title.configure(bg=bg_hex, fg=ink_hex)
        version.configure(bg=bg_hex, fg=MUTED)
        photo = ImageTk.PhotoImage(_logo_badge(source, size, fill, tint))
        mark.configure(image=photo, bg=bg_hex)
        mark.image = photo

    row.paint = paint
    paint(bg, INK)
    return row


PAGES = (
    ("graphics", "graphics_title"),
    ("buttons", "buttons_title"),
    ("saves", "saves_title"),
    ("advanced", "advanced_title"),
)


def mount(root: tk.Misc, state: dict, output_var, actions: dict) -> dict:
    register_fonts()
    family = _family()
    strong = _semibold()
    display = _display()
    opening = state.get("tema") if state.get("tema") in ("chiaro", "scuro") else "scuro"
    _install_palette(opening)
    _PLATES.clear()
    root.configure(bg=BG)
    style = ttk.Style(root)
    style.theme_use("clam")
    _style_chrome(style, family)
    skin_menus = []
    ui_theme = {"now": opening, "busy": False}

    paned = tk.PanedWindow(
        root, orient="horizontal", bg=LINE, sashwidth=7, sashrelief="flat",
        opaqueresize=True, bd=0, sashcursor="sb_h_double_arrow",
    )
    paned.pack(fill="both", expand=True)
    rail = tk.Frame(paned, bg=SIDE)
    main = tk.Frame(paned, bg=BG)
    paned.add(rail, minsize=280, stretch="always")
    paned.add(main, minsize=380, stretch="always")
    rail_canvas = tk.Canvas(rail, bg=SIDE, highlightthickness=0, bd=0)
    rail_bar = ttk.Scrollbar(rail, orient="vertical", command=rail_canvas.yview)
    rail_canvas.configure(yscrollcommand=rail_bar.set)
    rail_canvas.pack(side="left", fill="both", expand=True)
    column = tk.Frame(rail_canvas, bg=SIDE)
    rail_window = rail_canvas.create_window((0, 0), window=column, anchor="nw")
    inset = tk.Frame(column, bg=SIDE)
    inset.pack(fill="both", expand=True, padx=18, pady=(18, 16))
    top = inset
    bottom = inset
    rail_scroll = {"on": False}

    def sync_rail(_event=None) -> None:
        if not rail_canvas.winfo_ismapped():
            return
        box = rail_canvas.bbox("all")
        rail_canvas.configure(scrollregion=box or (0, 0, 0, 0))
        if not box:
            return
        need = (box[3] - box[1]) > rail_canvas.winfo_height() + 2
        if need == rail_scroll["on"]:
            return
        rail_scroll["on"] = need
        if need:
            rail_bar.pack(side="right", fill="y")
        else:
            rail_bar.pack_forget()

    def fit_rail_canvas(event) -> None:
        rail_canvas.itemconfigure(rail_window, width=max(int(event.width), 1))
        sync_rail()

    rail_canvas.bind("<Configure>", fit_rail_canvas)
    column.bind("<Configure>", sync_rail)

    brand = _logo(top, SIDE)
    brand.pack(anchor="w")
    meta = tk.Frame(top, bg=SIDE)
    meta.pack(fill="x", pady=(4, 10))
    lang = ttk.Combobox(meta, width=11, state="readonly", values=("English", "Italiano"))
    lang.pack(side="right")

    current = {"page": "buttons"}
    nav_bits = {}

    def paint_nav() -> None:
        for key, item in nav_bits.items():
            item.set_on(key == current["page"])

    nav = tk.Frame(top, bg=SIDE)
    nav.pack(fill="x")

    holder = tk.Canvas(main, bg=BG, highlightthickness=0, bd=0)
    scrollbar = ttk.Scrollbar(main, orient="vertical", command=holder.yview)
    holder.configure(yscrollcommand=scrollbar.set)
    inner = tk.Frame(holder, bg=BG)
    window_id = holder.create_window((0, 0), window=inner, anchor="nw")
    pages = {}
    wrapping: list = []
    scroll_state = {"on": False}

    def reflow(width: int) -> None:
        span = max(320, int(width) - 56)
        for label in wrapping:
            label.configure(wraplength=span)

    def sync_scroll(_event=None) -> None:
        if not holder.winfo_ismapped():
            return
        box = holder.bbox("all")
        holder.configure(scrollregion=box or (0, 0, 0, 0))
        if not box:
            return
        need = (box[3] - box[1]) > holder.winfo_height() + 2
        if need == scroll_state["on"]:
            return
        scroll_state["on"] = need
        if need:
            scrollbar.pack(side="right", fill="y")
        else:
            scrollbar.pack_forget()

    def fit(event) -> None:
        holder.itemconfigure(window_id, width=event.width)
        reflow(event.width)

    holder.bind("<Configure>", fit)
    inner.bind("<Configure>", sync_scroll)

    def show_page(key: str) -> None:
        if key not in dict(PAGES):
            return
        current["page"] = key
        paint_nav()
        if not holder.winfo_ismapped():
            holder.pack(side="left", fill="both", expand=True)
        for name, frame in pages.items():
            if name == key:
                frame.pack(fill="x", padx=28, pady=(22, 28))
            elif frame.winfo_manager():
                frame.pack_forget()
        holder.yview_moveto(0)
        holder.after_idle(sync_scroll)

    def add_nav(key: str) -> None:
        nav_bits[key] = NavItem(nav, lambda picked=key: show_page(picked), family)

    for key, _name in PAGES:
        add_nav(key)

    def heading(parent) -> tk.Label:
        label = tk.Label(parent, text="", bg=BG, fg=INK, font=(display, 28), anchor="w")
        label.pack(anchor="w", pady=(0, 10))
        plain = label.configure

        def configure(cnf=None, **kw):
            if cnf:
                kw.update(cnf)
            if kw.get("text"):
                kw["text"] = str(kw["text"]).upper()
            return plain(**kw)

        label.configure = configure
        label.config = configure
        return label

    def note(parent) -> tk.Label:
        label = tk.Label(parent, text="", bg=BG, fg=MUTED, font=(family, 12), wraplength=640, justify="left")
        label.pack(anchor="w")
        wrapping.append(label)
        return label

    buttons_page = tk.Frame(inner, bg=BG)
    graphics_page = tk.Frame(inner, bg=BG)
    saves_page = tk.Frame(inner, bg=BG)
    advanced_page = tk.Frame(inner, bg=BG)
    pages["buttons"] = buttons_page
    pages["graphics"] = graphics_page
    pages["saves"] = saves_page
    pages["advanced"] = advanced_page

    buttons_title = heading(buttons_page)
    pad_grid = tk.Frame(buttons_page, bg=BG)
    pad_grid.pack(fill="x")
    loading = {"on": False}
    pad_keys: dict = dict(SUGGESTED)
    dpad_keys: dict[str, str] = {}
    faces = {}
    dpad_faces: dict[str, ttk.Menubutton] = {}

    def pick_key(code: str, value: str, face) -> None:
        store = dpad_keys if code in DPAD_NAME else pad_keys
        if value:
            store[code] = value
        else:
            store.pop(code, None)
        face.configure(text=value or tr(state["lingua"], "no_key"))
        if not loading["on"]:
            actions["controls"]()

    def fill_menu(menu, code: str, face) -> None:
        menu.delete(0, "end")
        for group_key, keys in KEY_GROUPS:
            sub = tk.Menu(menu, tearoff=0, bg=CARD, fg=INK, activebackground=ACCENT, activeforeground=ON_INK)
            skin_menus.append(sub)
            for name in keys:
                sub.add_command(label=name, command=lambda value=name, c=code, b=face: pick_key(c, value, b))
            menu.add_cascade(label=tr(state["lingua"], group_key), menu=sub)
        menu.add_separator()
        menu.add_command(label=tr(state["lingua"], "no_key"), command=lambda c=code, b=face: pick_key(c, "", b))

    def show_keys(refill: bool = False) -> None:
        for code, face in faces.items():
            face.configure(text=pad_keys.get(code) or tr(state["lingua"], "no_key"))
            if refill:
                fill_menu(face.nametowidget(face.cget("menu")), code, face)
        for code, face in dpad_faces.items():
            face.configure(text=dpad_keys.get(code) or tr(state["lingua"], "no_key"))
            if refill:
                fill_menu(face.nametowidget(face.cget("menu")), code, face)

    for index, (code, name) in enumerate(PAD + (("L3", "L3"), ("R3", "R3"))):
        row = tk.Frame(pad_grid, bg=BG)
        row.grid(row=index // 2, column=index % 2, sticky="w", padx=(0, 28), pady=6)
        PadMark(row, name, "switch").pack(side="left", padx=(0, 8))
        cap = tk.Frame(row, bg=CARD, highlightthickness=2, highlightbackground=LINE, bd=0)
        menu = tk.Menu(row, tearoff=0, bg=CARD, fg=INK, activebackground=ACCENT, activeforeground=ON_INK)
        skin_menus.append(menu)
        face = ttk.Menubutton(cap, text=tr(state["lingua"], "no_key"), menu=menu, direction="below", width=14)
        face.pack(padx=2, pady=2)
        cap.pack(side="left")
        faces[code] = face
        fill_menu(menu, code, face)

    dpad_frame = tk.Frame(buttons_page, bg=BG)
    for code, name in DPAD:
        row = tk.Frame(dpad_frame, bg=BG)
        row.pack(anchor="w", pady=2)
        PadMark(row, name, "switch").pack(side="left", padx=(0, 8))
        cap = tk.Frame(row, bg=CARD, highlightthickness=2, highlightbackground=LINE, bd=0)
        menu = tk.Menu(row, tearoff=0, bg=CARD, fg=INK, activebackground=ACCENT, activeforeground=ON_INK)
        skin_menus.append(menu)
        face = ttk.Menubutton(cap, text=tr(state["lingua"], "no_key"), menu=menu, direction="below", width=14)
        face.pack(padx=2, pady=2)
        cap.pack(side="left")
        dpad_faces[code] = face
        fill_menu(menu, code, face)

    extras = {
        "turbo": "0", "counter": False, "registro": False, "menu": "stick", "croce": False,
        "tema": state.get("tema") if state.get("tema") in ("chiaro", "scuro") else "scuro",
    }
    OPEN_MENU = (
        ("stick", "L3+R3"),
        ("spalle", "L+R+ZL"),
    ) + PAD + (("L3", "L3"), ("R3", "R3")) + DPAD + (("MINUS", "−"),)
    OPEN_CODES = {code for code, _label in OPEN_MENU}
    extra_row = tk.Frame(buttons_page, bg=BG)
    croce_var = tk.BooleanVar(value=False)

    def apply_croce() -> None:
        if extras["croce"]:
            dpad_frame.pack(fill="x", pady=(4, 0), before=extra_row)
        elif dpad_frame.winfo_ismapped():
            dpad_frame.pack_forget()
        holder.after_idle(sync_scroll)

    def on_croce() -> None:
        extras["croce"] = bool(croce_var.get())
        apply_croce()
        if not loading["on"]:
            actions["controls"]()

    croce = ttk.Checkbutton(buttons_page, variable=croce_var, command=on_croce)
    croce_help = note(buttons_page)
    extra_row.pack(fill="x", pady=(12, 0))
    croce.pack(anchor="w", pady=(10, 0), before=extra_row)
    croce_help.pack(anchor="w", before=extra_row)
    counter_var = tk.BooleanVar(value=False)

    def on_counter() -> None:
        extras["counter"] = bool(counter_var.get())
        if not loading["on"]:
            actions["controls"]()

    counter = ttk.Checkbutton(buttons_page, variable=counter_var, command=on_counter)
    counter.pack(anchor="w", pady=(8, 0))
    registro_var = tk.BooleanVar(value=False)

    def on_registro() -> None:
        extras["registro"] = bool(registro_var.get())
        if not loading["on"]:
            actions["controls"]()

    registro = ttk.Checkbutton(buttons_page, variable=registro_var, command=on_registro)
    registro.pack(anchor="w", pady=(4, 0))
    open_row = tk.Frame(buttons_page, bg=BG)
    open_row.pack(fill="x", pady=(8, 0))
    open_name = tk.Label(open_row, text="", bg=BG, fg=INK, font=(strong, 14), width=14, anchor="w")
    open_name.pack(side="left")
    open_menu = tk.Menu(open_row, tearoff=0, bg=CARD, fg=INK, activebackground=ACCENT, activeforeground=ON_INK)
    skin_menus.append(open_menu)
    open_face = ttk.Menubutton(open_row, text="−", menu=open_menu, direction="below", width=14)
    open_face.pack(side="left")

    def open_text() -> str:
        for code, label in OPEN_MENU:
            if code == extras["menu"]:
                return label
        return "L3+R3"

    def fill_open() -> None:
        open_menu.delete(0, "end")
        for code, label in OPEN_MENU:
            open_menu.add_command(label=label, command=lambda value=code: pick_open(value))

    def pick_open(code: str) -> None:
        extras["menu"] = code if code in OPEN_CODES else "stick"
        open_face.configure(text=open_text())
        if not loading["on"]:
            actions["controls"]()

    fill_open()

    gfx_title = heading(graphics_page)
    gfx_var = tk.StringVar(value=state.get("grafica") or "intera")

    def on_gfx() -> None:
        actions["grafica"](gfx_var.get())

    gfx_buttons = []
    for key in ("intera", "nitida", "morbida"):
        button = ttk.Radiobutton(graphics_page, value=key, variable=gfx_var, command=on_gfx)
        button.pack(anchor="w", pady=(6, 0))
        gfx_buttons.append((key, button))
    gfx_note = note(graphics_page)
    gfx_note.pack_configure(pady=(8, 0))
    theme_name = tk.Label(graphics_page, text="", bg=BG, fg=INK, font=(strong, 14), anchor="w")
    theme_name.pack(anchor="w", pady=(16, 4))
    theme_var = tk.StringVar(value=extras["tema"])
    theme_row = tk.Frame(graphics_page, bg=BG)
    theme_row.pack(anchor="w")
    theme_buttons = []

    def apply_app_theme(name: str) -> None:
        name = "scuro" if name == "scuro" else "chiaro"
        previous = ui_theme["now"]
        mapping = _palette_map(previous, name)
        ui_theme["busy"] = True
        try:
            _install_palette(name)
            ui_theme["now"] = name
            extras["tema"] = name
            if theme_var.get() != name:
                theme_var.set(name)
            _style_chrome(style, family)
            if previous != name:
                _recolor_tree(root, mapping)
            brand.paint(SIDE, INK)
            for menu in skin_menus:
                try:
                    menu.configure(bg=CARD, fg=INK, activebackground=ACCENT, activeforeground=ON_INK)
                except tk.TclError:
                    pass
            show_keys(True)
            fill_open()
        finally:
            ui_theme["busy"] = False

    def on_theme() -> None:
        if ui_theme["busy"]:
            return
        chosen = theme_var.get() if theme_var.get() in ("chiaro", "scuro") else "scuro"
        apply_app_theme(chosen)
        if not loading["on"]:
            actions["controls"]()
            saved = actions.get("save_theme")
            if saved:
                saved(chosen)

    for code in ("chiaro", "scuro"):
        button = ttk.Radiobutton(theme_row, value=code, variable=theme_var, command=on_theme)
        button.pack(side="left", padx=(0, 16))
        theme_buttons.append((code, button))

    saves_title = heading(saves_page)
    save_buttons = []
    for name in ("copy_saves", "restore_saves", "delete_saves"):
        button = ChromeButton(saves_page, actions[name], outer=BG, stretch=False)
        button.pack(anchor="w", pady=3)
        save_buttons.append(button)
    saves_note = note(saves_page)
    saves_note.pack_configure(pady=(6, 0))

    adv_title = heading(advanced_page)
    family_label = tk.Label(advanced_page, text="", bg=BG, fg=INK, font=(family, 13))
    family_label.pack(anchor="w")
    family_box = ttk.Combobox(advanced_page, state="readonly", width=18)
    family_box.pack(anchor="w", pady=(4, 8))

    def on_family(_event=None) -> None:
        label = family_box.get()
        for code, key in FAMILIES:
            if tr(state["lingua"], key) == label:
                actions["family"](code)
                return

    family_box.bind("<<ComboboxSelected>>", on_family)
    nsp_note = note(advanced_page)
    nsp_note.pack_configure(pady=(4, 4))
    nsp = ChromeButton(advanced_page, actions["nsp"], outer=BG, stretch=False)
    check = ChromeButton(advanced_page, actions["check"], outer=BG, stretch=False)
    check.pack(anchor="w", pady=3)
    keys_note = tk.Label(advanced_page, text="", bg=BG, fg=MUTED, font=(family, 11), wraplength=640, justify="left")
    keys_note.pack(anchor="w", pady=(8, 0))
    wrapping.append(keys_note)

    tk.Frame(bottom, bg=LINE, height=1).pack(fill="x", pady=(12, 10))
    card = tk.Frame(bottom, bg=CARD, highlightthickness=0)
    card.pack(fill="x")
    game_name = tk.Label(card, text="", bg=CARD, fg=INK, font=(strong, 14), anchor="w", justify="left", wraplength=300)
    game_name.pack(fill="x", padx=14, pady=(14, 0))
    game_hint = tk.Label(card, text="", bg=CARD, fg=MUTED, font=(family, 11), anchor="w", justify="left", wraplength=300)
    game_hint.pack(fill="x", padx=14, pady=(2, 0))
    game_meta = tk.Label(card, text="", bg=CARD, fg=MUTED, font=(family, 11), anchor="w", justify="left", wraplength=300)
    game_meta.pack(fill="x", padx=14, pady=(4, 0))
    game_buttons = tk.Frame(card, bg=CARD)
    game_buttons.pack(fill="x", padx=14, pady=(10, 14))
    choose = ChromeButton(game_buttons, actions["choose_game"], outer=CARD)
    choose.pack(fill="x")
    icon = ChromeButton(game_buttons, actions["choose_icon"], outer=CARD)
    icon.pack(fill="x", pady=(6, 0))
    soften(card, 12, CARD, SIDE)

    dest = tk.Frame(bottom, bg=SIDE)
    dest.pack(fill="x", pady=(12, 0))
    dest_label = tk.Label(dest, text="", bg=SIDE, fg=INK, font=(strong, 12))
    dest_label.pack(anchor="w")
    dest_row = tk.Frame(dest, bg=SIDE)
    dest_row.pack(fill="x", pady=(6, 0))
    path = tk.Label(
        dest_row, textvariable=output_var, bg=FIELD, fg=INK, anchor="e", width=16,
        font=(family, 11), padx=8, pady=6, highlightthickness=1, highlightbackground=LINE,
    )
    path.pack(side="left", fill="x", expand=True)
    browse = ChromeButton(dest_row, actions["choose_output"], outer=SIDE, stretch=False)
    browse.pack(side="left", padx=(8, 0))

    prepare = ChromeButton(bottom, actions["prepare"], role="primary", outer=SIDE)
    root.bind("<Return>", lambda _event: actions["prepare"]())
    prepare.pack(fill="x", pady=(12, 0))
    work = tk.Frame(bottom, bg=SIDE)
    work_label = tk.Label(work, text="", bg=SIDE, fg=INK, font=(family, 11), wraplength=312, justify="left", anchor="w")
    work_label.pack(fill="x", pady=(8, 4))
    work_bar = ttk.Progressbar(work, orient="horizontal", mode="determinate", maximum=100, style="Fan.Horizontal.TProgressbar")
    work_bar.pack(fill="x")
    work_pct = tk.Label(work, text="", bg=SIDE, fg=MUTED, font=(family, 11), anchor="e")
    work_pct.pack(fill="x", pady=(2, 0))
    log = tk.Text(
        bottom, height=3, wrap="word", bg=CARD, fg=INK, relief="flat",
        highlightthickness=1, highlightbackground=LINE, highlightcolor=LINE,
        font=(family, 11), padx=8, pady=6, borderwidth=0,
    )
    log.pack(fill="x", pady=(10, 0))
    log.configure(state="disabled")
    status = tk.Label(bottom, text="", bg=SIDE, fg=MUTED, font=(family, 11), wraplength=312, justify="left")
    status.pack(anchor="w", pady=(8, 0))

    def say(key: str) -> str:
        return tr(state["lingua"], key)

    def refresh_body() -> None:
        lang.set("Italiano" if state["lingua"] == "it" else "English")
        for key, i18n_key in PAGES:
            nav_bits[key].configure(text=say(i18n_key))
        paint_nav()
        info = state.get("info")
        if info is None:
            game_name.configure(text=state.get("title") or say("drop_here"))
            game_hint.configure(text=say("drop_hint"))
            game_meta.configure(text="")
        else:
            game_name.configure(text=info.name)
            game_hint.configure(text=str(info.folder))
            bits = [info.family or say("family_auto")]
            tasti_key = "tasti_essentials" if getattr(info, "tasti", "") == "essentials" else "tasti_rgss"
            bits.append(say(tasti_key))
            if state.get("size"):
                bits.append(state["size"])
            game_meta.configure(text="  ·  ".join(bits))
        choose.configure(text=say("choose_game"))
        icon_name = state["icon"].name if state.get("icon") else say("icon_from_exe")
        icon.configure(text=say("icon") + ": " + icon_name)
        dest_label.configure(text=say("sd_folder"))
        browse.configure(text=say("change"))
        gfx_title.configure(text=say("graphics_title"))
        for key, button in gfx_buttons:
            button.configure(text=say("gfx_" + key))
        if gfx_var.get() != state.get("grafica"):
            gfx_var.set(state.get("grafica") or "intera")
        gfx_note.configure(text=say("gfx_note"))
        theme_name.configure(text=say("theme"))
        for code, button in theme_buttons:
            button.configure(text=say("theme_light" if code == "chiaro" else "theme_dark"))
        buttons_title.configure(text=say("buttons_title"))
        croce.configure(text=say("croce"))
        croce_help.configure(text=say("croce_help"))
        if bool(croce_var.get()) != bool(extras["croce"]):
            croce_var.set(extras["croce"])
        apply_croce()
        counter.configure(text=say("frame_counter"))
        registro.configure(text=say("registro"))
        open_name.configure(text=say("menu_open"))
        open_face.configure(text=open_text())
        show_keys()
        saves_title.configure(text=say("saves_title"))
        for button, key in zip(save_buttons, ("copy_pc", "restore", "delete")):
            button.configure(text=say(key))
        slug = info.slug if info else "game-name"
        saves_note.configure(text=say("saves_stay").format(slug=slug))
        adv_title.configure(text=say("advanced_title"))
        family_label.configure(text=say("family"))
        family_box.configure(values=[say(key) for _code, key in FAMILIES])
        picked = state.get("famiglia") or ""
        family_box.set(say(dict(FAMILIES).get(picked, "family_auto")))
        nsp_note.configure(text=actions["nsp_line"]())
        if sys.platform == "win32":
            nsp.configure(text=say("build_nsp"))
            if not nsp.winfo_ismapped():
                nsp.pack(anchor="w", pady=3, before=check)
        elif nsp.winfo_ismapped():
            nsp.pack_forget()
        check.configure(text=say("check_engine"))
        keys_note.configure(text=say("no_keys"))
        ready = state.get("info") is not None and not state.get("busy")
        prepare.configure(text=actions["prepare_label"](), state="normal" if ready else "disabled")
        if state.get("busy"):
            step = state.get("progress_step") or "progress_working"
            work_label.configure(text=say(step))
            value = int(state.get("progress") or 0)
            work_bar["value"] = value
            work_pct.configure(text=f"{value} %")
            if not work.winfo_ismapped():
                work.pack(fill="x", after=prepare)
            status.configure(text=say("progress_wait"))
        else:
            if work.winfo_ismapped():
                work.pack_forget()
            work_bar["value"] = 0
            status.configure(text=say("footer"))

    def load_controls(cfg: dict) -> None:
        loading["on"] = True
        try:
            pad_keys.clear()
            dpad_keys.clear()
            if "pc" in cfg:
                for item in (cfg.get("pc") or "").split(","):
                    if ":" not in item:
                        continue
                    code, key = item.split(":", 1)
                    if code in PAD_NAME and key in ALL_KEYS:
                        pad_keys[code] = key
                    elif code in ("L3", "R3") and key in ALL_KEYS:
                        pad_keys[code] = key
                    elif code in DPAD_NAME and key in ALL_KEYS:
                        dpad_keys[code] = key
            elif not cfg:
                pad_keys.update(SUGGESTED)
            extras["turbo"] = "0"
            extras["croce"] = cfg.get("croce") == "1"
            extras["counter"] = cfg.get("contatore") == "1"
            extras["registro"] = cfg.get("registro") == "1"
            extras["menu"] = cfg["menu_apri"] if cfg.get("menu_apri") in OPEN_CODES else "stick"
            if cfg.get("tema") in ("chiaro", "scuro"):
                apply_app_theme(cfg["tema"])
            else:
                theme_var.set(extras["tema"])
            counter_var.set(extras["counter"])
            registro_var.set(extras["registro"])
            croce_var.set(extras["croce"])
            apply_croce()
            open_face.configure(text=open_text())
            show_keys()
        finally:
            loading["on"] = False

    def comandi() -> dict:
        return {key: default for key, _label, default in ACTIONS}

    def pc() -> str:
        parts = [f"{code}:{pad_keys[code]}" for code, _name in PAD if pad_keys.get(code) in ALL_KEYS]
        parts += [f"{code}:{pad_keys[code]}" for code in ("L3", "R3") if pad_keys.get(code) in ALL_KEYS]
        parts += [f"{code}:{dpad_keys[code]}" for code, _name in DPAD if dpad_keys.get(code) in ALL_KEYS]
        return ",".join(parts)

    def write_log(line: str) -> None:
        log.configure(state="normal")
        log.insert("end", (("\n" if log.index("end-1c") != "1.0" else "") + line))
        log.see("end")
        log.configure(state="disabled")

    def set_progress(pct, step: str = "progress_working") -> None:
        state["progress"] = max(0, min(100, int(pct)))
        state["progress_step"] = step
        refresh()

    def on_lang(_event=None) -> None:
        actions["language"]("it" if lang.get() == "Italiano" else "en")

    lang.bind("<<ComboboxSelected>>", on_lang)

    def on_wheel(event) -> str:
        steps = _wheel_steps(int(getattr(event, "delta", 0) or 0))
        if not steps:
            return "break"
        widget = event.widget
        if _inside(widget, log):
            log.yview_scroll(steps, "units")
            return "break"
        if _inside(widget, rail):
            rail_canvas.yview_scroll(steps, "units")
            return "break"
        if holder.winfo_ismapped() and _inside(widget, holder):
            holder.yview_scroll(steps, "units")
        return "break"

    def hook(widget) -> None:
        widget.bind("<MouseWheel>", on_wheel)
        for child in widget.winfo_children():
            hook(child)

    shown = {"lingua": None}

    def refresh() -> None:
        previous = refresh_body()
        if shown["lingua"] != state["lingua"]:
            shown["lingua"] = state["lingua"]
            show_keys(True)
            fill_open()
        return previous

    for line in state.get("lines") or []:
        write_log(line)

    def fit_rail(event=None) -> None:
        width = rail_canvas.winfo_width()
        if width <= 1 and event is not None:
            width = int(event.width)
        span = max(160, int(width) - 36)
        for label in (game_name, game_hint, game_meta, work_label, status, disclaimer):
            try:
                label.configure(wraplength=span)
            except tk.TclError:
                pass

    rail.bind("<Configure>", fit_rail)
    show_page("graphics")
    refresh()
    rail_canvas.after_idle(lambda: (fit_rail(), sync_rail()))
    if extras["tema"] != ui_theme["now"]:
        apply_app_theme(extras["tema"])
    saved_split = state.get("divisore")
    if isinstance(saved_split, int) and saved_split >= 280:
        root.after_idle(lambda: paned.sash_place(0, saved_split, 1))
    hook(holder)
    hook(rail)
    return {
        "refresh": refresh,
        "load_controls": load_controls,
        "comandi": comandi,
        "pc": pc,
        "turbo": lambda: "0",
        "contatore": lambda: "1" if extras["counter"] else "0",
        "registro": lambda: "1" if extras["registro"] else "0",
        "menu_apri": lambda: extras["menu"] if extras["menu"] in OPEN_CODES else "stick",
        "croce": lambda: "1" if extras["croce"] else "0",
        "tema": lambda: extras["tema"] if extras["tema"] in ("chiaro", "scuro") else "scuro",
        "divisore": lambda: paned.sash_coord(0)[0],
        "write_log": write_log,
        "set_progress": set_progress,
        "show": show_page,
        "drops": (card, rail, holder, root),
    }
