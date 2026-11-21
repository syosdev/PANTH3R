import os
import tkinter as tk
from tkinter import filedialog

TEXT = "#e0e0e0"
TEXT_DIM = "#666666"

ACCENTS = [
    ("Crimson", "#c0392b"),
    ("Ember", "#e67e22"),
    ("Gold", "#d4ac0d"),
    ("Emerald", "#27ae60"),
    ("Teal", "#16a085"),
    ("Azure", "#2980b9"),
    ("Violet", "#8e44ad"),
    ("Rose", "#c2185b"),
]


class SettingsWindow:
    def __init__(self, app):
        import music_player.strip as sp
        bg = sp.BG
        surface = sp.SURFACE
        border = sp.BORDER
        self.app = app
        self.cfg = app.cfg
        self._swatches = []
        self._bg = bg
        self._surface = surface
        self._border = border
        self._help_panel = None
        self._help_body = None
        self._help_open = False
        self._help_sliding = False

        self.win = tk.Toplevel(app.root)
        self.win.title("Settings")
        self.win.configure(bg=bg, padx=12, pady=10)
        self.win.resizable(False, False)
        self.win.transient(app.root)

        self._build_general(bg, surface, border)
        self._divider(border)
        self._build_library(bg, border)
        self._divider(border)
        self._build_visualizer(bg, surface)
        self._divider(border)
        self._build_accent(bg)

        self.win.update_idletasks()
        w = self.win.winfo_reqwidth()
        h = self.win.winfo_reqheight()
        rx = app.root.winfo_x()
        ry = app.root.winfo_y()
        rw = app.root.winfo_width()
        rh = app.root.winfo_height()
        x = rx + (rw - w) // 2
        y = ry + (rh - h) // 2
        sx = self.win.winfo_screenwidth()
        sy = self.win.winfo_screenheight()
        x = max(0, min(x, sx - w))
        y = max(0, min(y, sy - h))
        self.win.geometry(f"+{x}+{y}")

    def _divider(self, border):
        tk.Frame(self.win, bg=border, height=1).pack(fill=tk.X, pady=(8, 8))

    def _section_label(self, text, bg):
        tk.Label(
            self.win, text=text, font=("Segoe UI", 7, "bold"),
            bg=bg, fg=TEXT_DIM, anchor="w",
        ).pack(fill=tk.X)

    def _build_general(self, bg, surface, border):
        self._section_label("GENERAL", bg)
        row = tk.Frame(self.win, bg=bg)
        row.pack(fill=tk.X, pady=(2, 0))
        btn = tk.Button(
            row, text="Help…", command=self._open_help,
            font=("Segoe UI", 8), bg=bg, fg=TEXT_DIM,
            activebackground=border, activeforeground=TEXT,
            relief="flat", bd=0, cursor="hand2",
        )
        btn.pack(side=tk.LEFT)

    def _open_help(self):
        if self._help_open or self._help_sliding:
            return
        if self._help_panel is None:
            self._build_help_panel()
        w = self.win.winfo_width()
        self._help_panel.place(x=w, y=0, relwidth=1, relheight=1)
        self._help_panel.lift()
        self._help_open = True
        self._help_sliding = True
        self._anim_help(w, 0)

    def _close_help(self):
        if not self._help_open or self._help_sliding:
            return
        w = self.win.winfo_width()
        self._help_open = False
        self._help_sliding = True
        self._anim_help(0, w, done=self._help_panel.place_forget)

    def _build_help_panel(self):
        bg, border = self._bg, self._border
        panel = tk.Frame(self.win, bg=bg,
                         highlightthickness=1, highlightbackground=border)
        head = tk.Frame(panel, bg=bg)
        head.pack(fill=tk.X, padx=12, pady=(10, 6))
        tk.Label(
            head, text="HELP", font=("Segoe UI", 7, "bold"),
            bg=bg, fg=TEXT_DIM, anchor="w",
        ).pack(side=tk.LEFT)
        back = tk.Button(
            head, text="Back", command=self._close_help,
            font=("Segoe UI", 8), bg=bg, fg=TEXT_DIM,
            activebackground=border, activeforeground=TEXT,
            relief="flat", bd=0, cursor="hand2",
        )
        back.pack(side=tk.RIGHT)
        self._help_body = tk.Frame(panel, bg=bg)
        self._help_body.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))
        self._help_panel = panel

    def _anim_help(self, x0, x1, done=None, step=0):
        try:
            total = 8
            if step > total:
                self._help_panel.place(x=int(x1), y=0,
                                       relwidth=1, relheight=1)
                self._help_sliding = False
                if done:
                    done()
                return
            t = step / total
            ease = 1 - (1 - t) ** 2
            px = int(x0 + (x1 - x0) * ease)
            self._help_panel.place(x=px, y=0, relwidth=1, relheight=1)
            self.win.after(16, lambda: self._anim_help(x0, x1, done, step + 1))
        except tk.TclError:
            pass

    def _build_library(self, bg, border):
        self._section_label("MUSIC FOLDER", bg)
        row = tk.Frame(self.win, bg=bg)
        row.pack(fill=tk.X, pady=(2, 0))
        self._dir_lbl = tk.Label(
            row, text=self._shorten(self.cfg.get("music_dir", "")),
            font=("Consolas", 7), bg=bg, fg=TEXT_DIM, anchor="w",
        )
        self._dir_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        btn = tk.Button(
            row, text="Browse…", command=self._pick_music_dir,
            font=("Segoe UI", 8), bg=bg, fg=TEXT_DIM,
            activebackground=border, activeforeground=TEXT,
            relief="flat", bd=0, cursor="hand2",
        )
        btn.pack(side=tk.RIGHT)
        self._info_lbl = tk.Label(
            self.win, text="", font=("Consolas", 7),
            bg=bg, fg=TEXT_DIM, anchor="w",
        )
        self._info_lbl.pack(fill=tk.X)
        self._update_lib_info()

    def _lib_summary(self):
        if not getattr(self.app, "_scanned", True):
            return "Scanning…"
        d = self.app._get_music_dir()
        if not os.path.isdir(d):
            return "Folder not found"
        pls = getattr(self.app, "_all_playlists", {})
        if not pls:
            return "No audio files found"
        n_folders = len(pls)
        n_tracks = sum(len(t) for t in pls.values())
        fs = "" if n_folders == 1 else "s"
        ts = "" if n_tracks == 1 else "s"
        return f"{n_folders} folder{fs} · {n_tracks} track{ts}"

    def _update_lib_info(self):
        try:
            self._info_lbl.config(text=self._lib_summary())
        except tk.TclError:
            pass

    @staticmethod
    def _shorten(path, max_len=36):
        if len(path) <= max_len:
            return path
        return "…" + path[-(max_len - 1):]

    def _pick_music_dir(self):
        cur = self.app._get_music_dir()
        initial = cur if os.path.isdir(cur) else os.path.expanduser("~")
        path = filedialog.askdirectory(
            parent=self.win, initialdir=initial,
            title="Choose music folder",
        )
        if not path:
            return
        self._info_lbl.config(text="Scanning…")
        if self.app._set_music_dir(path, done=self._update_lib_info):
            self._dir_lbl.config(text=self._shorten(self.app._get_music_dir()))

    def _build_visualizer(self, bg, surface):
        self._section_label("VISUALIZER", bg)
        row = tk.Frame(self.win, bg=bg)
        row.pack(fill=tk.X, pady=(2, 0))
        val = int(self.cfg.get("viz_bars", 20))
        self._bars_lbl = tk.Label(
            row, text=f"{val} bands", font=("Consolas", 8),
            bg=bg, fg=TEXT, width=8, anchor="e",
        )
        self._bars_lbl.pack(side=tk.RIGHT)
        scale = tk.Scale(
            row, from_=10, to=64, orient=tk.HORIZONTAL, showvalue=False,
            command=self._on_viz_bars, length=150,
            bg=bg, fg=TEXT_DIM, troughcolor=surface,
            highlightthickness=0, bd=0,
            activebackground=self.cfg.get("accent", "#c0392b"),
            sliderrelief="flat", cursor="hand2",
        )
        scale.set(val)
        scale.pack(side=tk.LEFT)

    def _on_viz_bars(self, raw):
        val = int(float(raw))
        self._bars_lbl.config(text=f"{val} bands")
        self.app._set_viz_bars(val)

    def _build_accent(self, bg):
        self._section_label("ACCENT", bg)
        row = tk.Frame(self.win, bg=bg)
        row.pack(fill=tk.X, pady=(4, 0))
        current = self.cfg.get("accent", "#c0392b")
        for name, hexc in ACCENTS:
            swatch = tk.Label(
                row, text="  ", bg=hexc, cursor="hand2",
                highlightthickness=2,
                highlightbackground=hexc if hexc == current else bg,
            )
            swatch.bind(
                "<Button-1>",
                lambda e, h=hexc: self._on_accent(h),
            )
            self._swatches.append(swatch)
            swatch.pack(side=tk.LEFT, padx=(0, 6))

    def _on_accent(self, hexc):
        import music_player.strip as sp
        self.cfg["accent"] = hexc
        for s in self._swatches:
            s.config(highlightbackground=sp.BG)
        for i, (_, h) in enumerate(ACCENTS):
            if h == hexc:
                self._swatches[i].config(highlightbackground=h)
                break
        self.app._set_accent(hexc)
