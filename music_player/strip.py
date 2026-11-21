import os
import sys
import time
import random
import bisect
import threading
import tkinter as tk

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from music_player.audio_engine import AudioEngine
from music_player.visualizer import Visualizer
from music_player.animator import FrameAnimator
from music_player.settings_window import SettingsWindow
from music_player import config

BG = "#0d0d0d"
SURFACE = "#1a1012"
TEXT = "#e0e0e0"
TEXT_DIM = "#666666"
BORDER = "#2a1518"
ACCENT = "#c0392b"
STRIP_W = 400
VIZ_H = 44
MID_H = 220
STRIP_H = 40
SUPPORTED = (".mp3", ".wav", ".ogg", ".flac", ".m4a")
PANEL_W = 180


class Strip:
    def __init__(self):
        self.cfg = config.load()
        self._apply_accent_globals(self.cfg.get("accent", ACCENT))
        self.root = tk.Tk()
        self.root.title("PANTH3R")
        self._app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._icon_path = os.path.join(self._app_dir, "panth3r icon.ico")
        if not os.path.exists(self._icon_path):
            self._icon_path = os.path.join(
                self._app_dir,
                "assets",
                "icon.ico",
            )
        if os.path.exists(self._icon_path):
            self.root.iconbitmap(self._icon_path)
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.root.attributes("-topmost", self.cfg.get("always_on_top", True))

        self.engine = AudioEngine()
        self.playlist = []
        self._all_playlists = {}
        self._active_playlist = None
        self._scanned = False
        self.current_index = -1
        self._favorites = set(self.cfg.get("favorites", []))
        self._shuffle = self.cfg.get("shuffle", False)
        self._active_view = None
        self._sliding = False
        self._pl_open = False
        self._searching = False
        self._search_results = []
        self._queue = None
        self._queue_pos = -1
        self._playing_path = None
        self._panther_pause_job = None
        self._settle_ticks = 0
        self._dividers = []
        self._bottom_btns = []

        self._build_strip()
        self._restore_volume()
        self._restore_position()
        self._update_timer()
        self.root.after(50, self._init_boot)

    def _apply_accent_globals(self, color):
        global ACCENT, SURFACE, BORDER
        ACCENT = color
        SURFACE = Strip._blend(color, BG, 0.07)
        BORDER = Strip._blend(color, BG, 0.16)

    def _init_boot(self):
        self._scan_folders(done=self._restore_last_track)

    def _restore_position(self):
        wx = self.cfg.get("window_x")
        wy = self.cfg.get("window_y")
        self.root.update_idletasks()
        h = self.root.winfo_reqheight()
        if wx is not None and wy is not None:
            self.root.geometry(f"{STRIP_W}x{h}+{wx}+{wy}")
        else:
            sx = self.root.winfo_screenwidth()
            sy = self.root.winfo_screenheight()
            x = sx // 2 - STRIP_W // 2
            y = sy // 2 - h // 2
            self.root.geometry(f"{STRIP_W}x{h}+{x}+{y}")

    def _restore_volume(self):
        vol = self.cfg.get("volume", 0.7)
        self.engine.volume = vol
        if vol <= 0:
            self._vol_icon.config(text="🔇")

    def _restore_last_track(self):
        path = self.cfg.get("last_track")
        position = self.cfg.get("last_position", 0)
        if not path or not os.path.isfile(path):
            return
        try:
            if path in self.playlist:
                self.current_index = self.playlist.index(path)
            self.engine.load(path)
            self._playing_path = path
            if position > 0 and self.engine.duration > 0:
                self.engine._pending_seek = min(position, self.engine.duration)
            self.play_btn.config(text="▶")
            meta = self.engine.get_metadata(path)
            label = meta["title"]
            if meta["artist"]:
                label += f"  -  {meta['artist']}"
            self._set_title(label)
            self._refresh_track_list(center=False)
        except Exception:
            self.current_index = -1
            self._playing_path = None

    def _divider(self, parent, side=tk.TOP, pady=(2, 2)):
        f = tk.Frame(parent, bg=BORDER, height=1)
        f.pack(fill=tk.X, padx=8, side=side, pady=pady)
        self._dividers.append(f)

    def _build_strip(self):
        self.root.bind("<Button-1>", self._on_global_click, add="+")
        self._build_top()
        self._build_bottom()
        self._build_middle()

    def _on_global_click(self, event):
        if event.widget is self._search_entry:
            return
        if self.root.focus_get() is self._search_entry:
            self._search_entry.selection_clear()
            self.root.focus_set()

    def _build_top(self):
        top = tk.Frame(self.root, bg=BG)
        top.pack(fill=tk.X)

        row1 = tk.Frame(top, bg=BG)
        row1.pack(fill=tk.X, padx=8, pady=(4, 0))

        panther_x = 35
        self.visualizer = Visualizer(row1, self.engine, 400, VIZ_H,
                                     bar_count=self.cfg.get("viz_bars", 20),
                                     accent=self.cfg.get("accent", ACCENT),
                                     dip_center=panther_x, dip_sigma=22,
                                     dip_depth=0.9)
        self.visualizer.canvas.pack(fill=tk.X, padx=6, pady=3)

        self.animator = FrameAnimator(
            self.visualizer.canvas, width=70, height=70, fps=8,
            accent=self.cfg.get("accent", ACCENT),
            frame_dir=os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "assets",
            ),
            x=panther_x, y=VIZ_H // 2,
        )

        self._divider(top)

        row2 = tk.Frame(top, bg=BG)
        row2.pack(fill=tk.X, padx=8)

        btn_kw = {"font": ("Segoe UI", 8), "bg": BG, "fg": TEXT_DIM,
                   "activebackground": SURFACE, "activeforeground": ACCENT,
                   "relief": "flat", "bd": 0, "cursor": "hand2"}
        self._tab_btns = {}
        for label, val in [("Playlists", "playlists"), ("Favorites", "favorites")]:
            b = tk.Button(row2, text=label, command=lambda v=val: self._toggle_panel(v), **btn_kw)
            b.pack(side=tk.RIGHT, padx=(2, 6))
            self._tab_btns[val] = b
        self._update_tab_btn_colors()

        self._build_seek_bar(row2)
        self._divider(self.root, pady=(0, 2))

    def _build_middle(self):
        mid = tk.Frame(self.root, bg=BG)
        mid.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 2))

        self._search_var = tk.StringVar()

        self._view_host = tk.Frame(mid, bg=BG, height=MID_H)
        self._view_host.pack(fill=tk.BOTH, expand=True)
        self._view_host.pack_propagate(False)

        self._view_tracks = tk.Frame(self._view_host, bg=BG)

        search_bg = self._blend(ACCENT, BG, 0.03)
        search_ring = "#454545"
        self._search_row = search_row = tk.Frame(
            self._view_tracks, bg=search_bg, highlightthickness=1,
            highlightbackground=search_ring,
        )
        search_row.pack(fill=tk.X, pady=(0, 4))
        self._search_icon_lbl = tk.Label(
            search_row, text="🔍", font=("Segoe UI", 8),
            bg=search_bg, fg=TEXT_DIM,
        )
        self._search_icon_lbl.pack(side=tk.LEFT, padx=(6, 4))
        self._search_entry = tk.Entry(
            search_row, textvariable=self._search_var, font=("Segoe UI", 8),
            bg=search_bg, fg=TEXT, insertbackground=TEXT, relief="flat", bd=0,
        )
        self._search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True,
                                pady=3, padx=(0, 6))
        self._search_entry.bind(
            "<FocusIn>",
            lambda e: search_row.config(highlightbackground=ACCENT),
        )
        self._search_entry.bind(
            "<FocusOut>",
            lambda e: search_row.config(highlightbackground=search_ring),
        )
        self._search_entry.bind("<KeyRelease>", self._on_search_key)

        self._ROW_H = 20
        self._track_canvas = tk.Canvas(
            self._view_tracks, bg=SURFACE, highlightthickness=0, cursor="hand2",
        )
        self._track_canvas.pack(fill=tk.BOTH, expand=True)
        self._track_canvas.bind("<Button-1>", self._on_track_click)
        self._track_canvas.bind("<Double-Button-1>", self._on_track_double_click)
        self._track_canvas.bind("<Button-3>", self._on_track_right_click)
        self._track_canvas.bind("<MouseWheel>", self._on_track_scroll)
        self._track_canvas.bind("<Configure>", self._on_track_resize)
        self._track_canvas.bind("<Motion>", self._on_track_hover)
        self._track_canvas.bind("<Leave>", lambda e: self._track_canvas.config(cursor=""))

        self._track_scroll = 0
        self._track_selected = -1
        self._track_items = []
        self._track_row_h = []
        self._track_last_w = None

        self._view_favs = tk.Frame(self._view_host, bg=SURFACE)
        self._build_favorites_view()

        self._panel_pls = tk.Frame(self._view_host, bg=SURFACE, width=PANEL_W)
        self._build_playlists_view()

        self._view_tracks.place(relwidth=1, relheight=1)
        self._active_view = None
        self._sliding = False
        self._pl_open = False

    def _toggle_panel(self, name):
        if self._sliding:
            return
        if name == "playlists":
            if self._active_view == "favorites":
                self._switch_view(None, done=self._open_pl_panel)
                self._pl_open = True
            else:
                self._pl_open = not self._pl_open
                self._slide_playlists()
        else:
            target = None if self._active_view == name else name
            if target != self._active_view:
                if self._pl_open:
                    self._pl_open = False
                    self._slide_playlists()
                self._switch_view(target)
        self._update_tab_btn_colors()

    def _open_pl_panel(self):
        self._refresh_pl_list()
        self._pl_open = True
        self._slide_playlists()
        self._update_tab_btn_colors()

    def _slide_playlists(self):
        host_w = self._view_host.winfo_width()
        if host_w <= 1:
            host_w = STRIP_W - 16
        self._sliding = True
        self.visualizer.suspend()
        if self._pl_open:
            self._refresh_pl_list()
            self._panel_pls.place(x=host_w, y=0, width=PANEL_W, relheight=1)
            self._panel_pls.lift()
            self._anim_slide(host_w, host_w - PANEL_W)
        else:
            self._anim_slide(host_w - PANEL_W, host_w,
                             done=self._panel_pls.place_forget)

    def _set_tracks_width(self, w):
        self._view_tracks.place(x=0, relwidth=0, width=max(int(w), 1))

    def _anim_slide(self, x0, x1, done=None, step=0):
        total = 8
        if step > total:
            self._panel_pls.place(x=int(x1), y=0, width=PANEL_W, relheight=1)
            self._set_tracks_width(x1)
            self._sliding = False
            self.root.after_idle(self._remeasure_tracks)
            self.visualizer.resume()
            if done:
                done()
            return
        t = step / total
        ease = 1 - (1 - t) ** 2
        px = int(x0 + (x1 - x0) * ease)
        self._panel_pls.place(x=px, y=0, width=PANEL_W, relheight=1)
        self._set_tracks_width(px)
        self.root.after(16, lambda: self._anim_slide(x0, x1, done, step + 1))

    def _switch_view(self, name, done=None):
        views = {"tracks": self._view_tracks,
                 "favorites": self._view_favs}
        old_name = self._active_view or "tracks"
        new_name = name or "tracks"
        if old_name == new_name:
            if done:
                done()
            return
        if new_name == "favorites":
            self._refresh_fav_list()
        old_v = views[old_name]
        new_v = views[new_name]
        self._active_view = name
        self._sliding = True
        self.visualizer.suspend()
        self._animate_view_slide(old_v, new_v,
                                 reverse=(new_name == "tracks"), done=done)

    def _animate_view_slide(self, old_v, new_v, reverse=False, done=None, step=0):
        d = -1 if reverse else 1
        host_w = self._view_host.winfo_width()
        if host_w <= 1:
            host_w = STRIP_W - 16
        total = 8
        if step > total:
            try:
                old_v.place_forget()
            except tk.TclError:
                pass
            new_v.place(relwidth=1, relheight=1, x=0)
            self._sliding = False
            self.visualizer.resume()
            if done:
                done()
            return
        t = step / total
        ease = 1 - (1 - t) ** 2
        new_v.place(relwidth=1, relheight=1, x=int(d * host_w * (1 - ease)))
        if old_v is not new_v:
            old_v.place(relwidth=1, relheight=1, x=int(-d * host_w * ease))
        new_v.lift()
        self.root.after(16, lambda: self._animate_view_slide(
            old_v, new_v, reverse, done, step + 1))

    def _update_tab_btn_colors(self):
        for name, btn in self._tab_btns.items():
            on = ((name == "playlists" and self._pl_open)
                  or self._active_view == name)
            btn.config(fg=ACCENT if on else TEXT_DIM)

    def _build_playlists_view(self):
        self._pl_list = tk.Listbox(
            self._panel_pls, bg=BG, fg=TEXT_DIM, selectbackground=BORDER, selectforeground=ACCENT,
            font=("Consolas", 8), relief="flat", highlightthickness=0,
            activestyle="none", borderwidth=0, cursor="hand2",
        )
        self._pl_list.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self._pl_list.bind("<Button-1>", self._on_pl_select)

    def _build_favorites_view(self):
        self._fav_list = tk.Listbox(
            self._view_favs, bg=BG, fg=TEXT_DIM, selectbackground=BORDER, selectforeground=ACCENT,
            font=("Consolas", 8), relief="flat", highlightthickness=0,
            activestyle="none", borderwidth=0, cursor="hand2",
        )
        self._fav_list.pack(fill=tk.BOTH, expand=True, padx=2, pady=(2, 0))
        self._fav_list.bind("<Double-Button-1>", self._on_fav_double_click)

        self._fav_btn_row = tk.Frame(self._view_favs, bg=SURFACE)
        self._fav_btn_row.pack(fill=tk.X, padx=2, pady=(2, 2))
        bkw = {"font": ("Segoe UI", 7), "bg": BG, "fg": TEXT_DIM,
               "activebackground": BORDER, "activeforeground": ACCENT,
               "relief": "flat", "padx": 4, "cursor": "hand2"}
        self._fav_remove_btn = tk.Button(self._fav_btn_row, text="Remove", command=self._fav_remove, **bkw)
        self._fav_remove_btn.pack(side=tk.LEFT)

    def _on_search_key(self, event):
        if getattr(self, "_search_after", None):
            self.root.after_cancel(self._search_after)
        self._search_after = self.root.after(150, self._on_search)

    def _on_search(self, event=None):
        self._search_after = None
        query = self._search_var.get().strip().lower()
        if not query:
            self._searching = False
            self._search_results = []
            self._refresh_track_list()
            return
        self._searching = True
        self._search_results = []
        for folder_tracks in self._all_playlists.values():
            for path in folder_tracks:
                basename = os.path.splitext(os.path.basename(path))[0].lower()
                if query in basename:
                    self._search_results.append(path)
        self._refresh_track_list()

    def _get_music_dir(self):
        d = self.cfg.get("music_dir")
        return d if d else config.DEFAULT_CONFIG["music_dir"]

    def _scan_folders(self, done=None):
        self._scan_gen = getattr(self, "_scan_gen", 0) + 1
        gen = self._scan_gen
        music_dir = self._get_music_dir()

        def worker():
            result = self._collect_library(music_dir)
            try:
                self.root.after(0, lambda: self._apply_scan(gen, result, done))
            except tk.TclError:
                pass

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _walk_error(err):
        print(f"[pulse] skipping unreadable folder: {err}")

    def _collect_library(self, music_dir):
        playlists = {}
        root_tracks = []
        if not os.path.isdir(music_dir):
            return {"playlists": playlists, "root_tracks": [], "error": "missing"}
        try:
            entries = os.listdir(music_dir)
        except OSError as err:
            print(f"[pulse] cannot read music folder ({err}): {music_dir}")
            return {"playlists": playlists, "root_tracks": [], "error": str(err)}
        for entry in entries:
            folder_path = os.path.join(music_dir, entry)
            if os.path.isdir(folder_path):
                tracks = []
                for dirpath, _dirs, files in os.walk(
                        folder_path, onerror=Strip._walk_error):
                    for f in files:
                        if os.path.splitext(f)[1].lower() in SUPPORTED:
                            tracks.append(os.path.join(dirpath, f))
                tracks.sort()
                if tracks:
                    playlists[entry] = tracks
            elif os.path.splitext(entry)[1].lower() in SUPPORTED:
                root_tracks.append(folder_path)
        root_tracks.sort()
        return {"playlists": playlists, "root_tracks": root_tracks,
                "error": None}

    def _apply_scan(self, gen, result, done=None):
        if gen != getattr(self, "_scan_gen", 0):
            return
        playlists = result["playlists"]
        if result["root_tracks"]:
            root_name = os.path.basename(
                os.path.normpath(self._get_music_dir())) or "Music"
            merged = set(playlists.get(root_name, [])) | set(result["root_tracks"])
            playlists[root_name] = sorted(merged)
        self._all_playlists = playlists
        saved = self.cfg.get("active_playlist")
        if saved and saved in playlists:
            self._active_playlist = saved
            self.playlist = list(playlists[saved])
        elif playlists:
            self._active_playlist = next(iter(playlists))
            self.playlist = list(playlists[self._active_playlist])
        else:
            self._active_playlist = None
            self.playlist = []
        self.current_index = -1
        self._scanned = True
        self._prune_stale_favorites()
        self._refresh_pl_list()
        self._refresh_track_list()
        self._refresh_fav_list()
        if done:
            done()

    def _prune_stale_favorites(self):
        favs = [p for p in self._favorites if os.path.isfile(p)]
        if len(favs) != len(self._favorites):
            self._favorites = set(favs)
            self.cfg["favorites"] = sorted(favs)
            config.save(self.cfg)

    def _refresh_pl_list(self):
        self._pl_list.delete(0, tk.END)
        for name, tracks in self._all_playlists.items():
            prefix = "▶ " if name == self._active_playlist else "  "
            self._pl_list.insert(tk.END, f"{prefix}{name} ({len(tracks)} tracks)")
            idx = self._pl_list.size() - 1
            fg = ACCENT if name == self._active_playlist else TEXT_DIM
            self._pl_list.itemconfig(idx, fg=fg)

    def _on_pl_select(self, event):
        sel = self._pl_list.nearest(event.y)
        if sel < 0:
            return
        names = list(self._all_playlists.keys())
        if sel < len(names) and names[sel] != self._active_playlist:
            self.switch_playlist(names[sel])

    def switch_playlist(self, name):
        if name not in self._all_playlists:
            return
        self._active_playlist = name
        self.cfg["active_playlist"] = name
        config.save(self.cfg)
        self.playlist = list(self._all_playlists[name])
        try:
            self.current_index = self.playlist.index(self._playing_path)
        except (ValueError, TypeError):
            self.current_index = -1
        self._refresh_pl_list()
        self._refresh_track_list()

    def _refresh_track_list(self, center=True):
        source = self._search_results if self._searching else self.playlist
        sig = (self._searching, tuple(source))
        if sig != getattr(self, "_track_src_sig", None):
            self._track_scroll = 0
            self._track_selected = -1
            self._track_src_sig = sig
        fav_fg = self._blend(ACCENT, BG, 0.65)
        self._track_items = []
        for i, path in enumerate(source):
            basename = os.path.splitext(os.path.basename(path))[0]
            if path == self._playing_path:
                icon = "▶ "
                fg = ACCENT
            elif path in self._favorites:
                icon = "♥ "
                fg = fav_fg
            else:
                icon = "♪ "
                fg = TEXT_DIM
            self._track_items.append((icon, basename, fg))
        self._track_row_h = []
        self._draw_tracks()
        if center and self.current_index >= 0 and not self._searching:
            self._scroll_to_track(self.current_index)

    def _scroll_to_track(self, idx):
        if idx < 0 or idx >= len(self._track_items):
            return
        ch = self._track_canvas.winfo_height()
        if ch <= 0:
            return
        y = 0
        for i in range(idx):
            y += self._track_row_h[i] if i < len(self._track_row_h) else self._ROW_H
        row_h = self._track_row_h[idx] if idx < len(self._track_row_h) else self._ROW_H
        total_h = sum(self._track_row_h) if self._track_row_h else len(self._track_items) * self._ROW_H
        self._track_scroll = max(0, min(y - ch // 2 + row_h // 2, total_h - ch))
        self._draw_tracks()

    def _on_track_hover(self, event):
        idx = self._track_y_to_index(event.y + self._track_scroll)
        hover = 0 <= idx < len(self._track_items)
        self._track_canvas.config(cursor="hand2" if hover else "")

    def _on_track_resize(self, event):
        if event.widget is not self._track_canvas:
            return
        if event.width != getattr(self, "_track_last_w", None):
            self._track_last_w = event.width
            self._track_row_h = []
            self._draw_tracks()

    def _remeasure_tracks(self):
        self._track_row_h = []
        self._draw_tracks()

    def _measure_row_height(self, label, text_w):
        cache = getattr(self, "_row_h_cache", None)
        if cache is None:
            cache = self._row_h_cache = {}
        if len(cache) > 24:
            cache.clear()
        bucket = cache.setdefault(text_w, {})
        h = bucket.get(label)
        if h is None:
            tmp = self._track_canvas.create_text(
                0, 0, text=label,
                font=("Consolas", 9), anchor="nw", width=text_w,
            )
            bbox = self._track_canvas.bbox(tmp)
            self._track_canvas.delete(tmp)
            h = max(self._ROW_H, bbox[3] - bbox[1] + 6) if bbox else self._ROW_H
            bucket[label] = h
        return h

    def _draw_tracks(self):
        self._track_canvas.delete("all")
        cw = self._track_canvas.winfo_width()
        if cw <= 1:
            cw = 300
        ch = self._track_canvas.winfo_height()
        text_w = cw - 16
        if text_w < 50:
            text_w = 50

        if not self._track_items:
            if self._searching:
                msg = "No matches"
            elif not self._scanned:
                msg = "Scanning…"
            elif not os.path.isdir(self._get_music_dir()):
                msg = "Music folder not found — choose one in Settings (⚙)"
            elif not self._all_playlists:
                msg = "No audio files found in music folder"
            else:
                msg = ""
            if msg:
                self._track_canvas.create_text(
                    cw // 2, max(ch // 2, 10), text=msg,
                    fill=TEXT_DIM, font=("Segoe UI", 8),
                )
            return

        if len(self._track_row_h) != len(self._track_items):
            self._track_row_h = []
            for icon, name, fg in self._track_items:
                label = f"{icon}{name}"
                self._track_row_h.append(
                    self._measure_row_height(label, text_w))
        cum = [0]
        for h in self._track_row_h:
            cum.append(cum[-1] + h)
        self._track_cum = cum

        y = 0
        for i in range(len(self._track_items)):
            row_h = self._track_row_h[i] if i < len(self._track_row_h) else self._ROW_H
            if y + row_h < 0:
                y += row_h
                continue
            if y > ch:
                break
            if y >= -row_h:
                icon, name, fg = self._track_items[i]
                ry = y - self._track_scroll
                if ry + row_h < 0 or ry > ch:
                    y += row_h
                    continue
                if i == self._track_selected:
                    self._track_canvas.create_rectangle(
                        0, ry, cw, ry + row_h, fill=BORDER, outline="",
                    )
                self._track_canvas.create_text(
                    8, ry + 3, text=f"{icon}{name}",
                    font=("Consolas", 9), fill=fg, anchor="nw", width=text_w,
                )
            y += row_h

    def _track_y_to_index(self, y):
        cum = getattr(self, "_track_cum", None)
        if not cum or len(cum) < 2:
            return -1
        idx = bisect.bisect_right(cum, y) - 1
        if idx < 0 or idx >= len(self._track_items):
            return -1
        return idx

    def _on_track_click(self, event):
        idx = self._track_y_to_index(event.y + self._track_scroll)
        if 0 <= idx < len(self._track_items):
            self._track_selected = idx
            self._draw_tracks()

    def _on_track_double_click(self, event):
        idx = self._track_y_to_index(event.y + self._track_scroll)
        if 0 <= idx < len(self._track_items):
            if self._searching:
                if idx < len(self._search_results):
                    self._play_from_list(self._search_results, idx)
            else:
                self._play_index(idx)

    def _on_track_scroll(self, event):
        delta = -1 if event.delta > 0 else 1
        self._track_scroll = max(0, self._track_scroll + delta * self._ROW_H * 3)
        total_h = sum(self._track_row_h) if self._track_row_h else len(self._track_items) * self._ROW_H
        max_scroll = max(0, total_h - self._track_canvas.winfo_height())
        self._track_scroll = min(self._track_scroll, max_scroll)
        self._draw_tracks()

    def _build_seek_bar(self, parent):
        self._seek_dragging = False
        self._seek_last_time = 0
        self._seek_time = 0
        self._seek_settle = 0

        self._ts_cur = tk.Label(parent, text="0:00", font=("Consolas", 8), fg=TEXT_DIM, bg=BG, width=5, anchor="w")
        self._ts_cur.pack(side=tk.LEFT, padx=(6, 0))

        self._ts_dur = tk.Label(parent, text="0:00", font=("Consolas", 8), fg=TEXT_DIM, bg=BG, width=5, anchor="e")
        self._ts_dur.pack(side=tk.RIGHT)

        self._seek_canvas = tk.Canvas(parent, bg=BG, highlightthickness=0, height=16, cursor="hand2")
        self._seek_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4))
        self._seek_canvas.bind("<Button-1>", self._on_seek_click)
        self._seek_canvas.bind("<B1-Motion>", self._on_seek_drag)
        self._seek_canvas.bind("<ButtonRelease-1>", self._on_seek_release)

    def _on_seek_click(self, event):
        self._seek_dragging = True
        self._seek_to(event)
        self.root.bind("<B1-Motion>", self._on_seek_motion)
        self.root.bind("<ButtonRelease-1>", self._on_seek_release_root)

    def _on_seek_motion(self, event):
        if not getattr(self, "_seek_dragging", False):
            return
        x = event.x_root - self._seek_canvas.winfo_rootx()
        w = self._seek_canvas.winfo_width()
        if w <= 0:
            return
        dur = self.engine.duration
        if dur <= 0:
            return
        ratio = max(0.0, min(1.0, x / w))
        self._seek_time = ratio * dur
        self.engine.seek(self._seek_time)

    def _on_seek_release_root(self, event):
        self._on_seek_release(event)
        try:
            self.root.unbind("<B1-Motion>")
            self.root.unbind("<ButtonRelease-1>")
        except tk.TclError:
            pass

    def _on_seek_drag(self, event):
        now = time.monotonic()
        if now - self._seek_last_time < 0.05:
            return
        self._seek_last_time = now
        self._seek_to(event)

    def _on_seek_release(self, event):
        self._seek_to(event)
        self._seek_dragging = False
        self._seek_settle = time.monotonic()

    def _seek_to(self, event):
        dur = self.engine.duration
        if dur <= 0:
            return
        w = self._seek_canvas.winfo_width()
        if w <= 0:
            return
        ratio = max(0.0, min(1.0, event.x / w))
        self._seek_time = ratio * dur
        self.engine.seek(self._seek_time)

    def _update_seek_bar(self):
        w = self._seek_canvas.winfo_width()
        if w <= 0:
            return
        self._seek_canvas.delete("all")
        bar_y = 6
        bar_h = 2
        self._seek_canvas.create_rectangle(2, bar_y, w - 2, bar_y + bar_h, fill=SURFACE, outline="")
        dur = self.engine.duration
        if self._seek_dragging:
            pos = self._seek_time
        elif self._seek_settle and time.monotonic() - self._seek_settle < 0.5:
            pos = self._seek_time
        else:
            pos = self.engine.get_position() if dur > 0 else 0
        ratio = max(0.0, min(1.0, pos / dur)) if dur > 0 else 0
        fill_x = 2 + ratio * (w - 4)
        if fill_x > 2:
            self._seek_canvas.create_rectangle(2, bar_y, fill_x, bar_y + bar_h, fill=ACCENT, outline="")
        handle_r = 4
        cx = max(2 + handle_r, min(w - 2 - handle_r, fill_x))
        self._seek_canvas.create_oval(cx - handle_r, bar_y + bar_h // 2 - handle_r,
                                       cx + handle_r, bar_y + bar_h // 2 + handle_r,
                                       fill=TEXT, outline="")

    def _build_bottom(self):
        bottom = tk.Frame(self.root, bg=BG)
        bottom.pack(fill=tk.X, side=tk.BOTTOM, padx=8, pady=(0, 4))
        self._divider(self.root, side=tk.BOTTOM, pady=(2, 3))

        btn_kw = {
            "font": ("Segoe UI", 13), "bg": BG, "fg": TEXT,
            "activebackground": SURFACE, "activeforeground": ACCENT,
            "relief": "flat", "bd": 0, "cursor": "hand2", "width": 2,
        }
        for text, cmd, pad in (("⏮", self._prev, (6, 2)),
                               ("▶", self._toggle_play, (2, 2)),
                               ("⏭", self._next, (2, 2))):
            b = tk.Button(bottom, text=text, command=cmd, **btn_kw)
            b.pack(side=tk.LEFT, padx=pad)
            self._bottom_btns.append(b)
        self.play_btn = self._bottom_btns[1]

        self._shuffle_btn = tk.Button(
            bottom, text="🔀", command=self._toggle_shuffle,
            font=("Segoe UI", 13), bg=BG,
            fg=ACCENT if self._shuffle else TEXT_DIM,
            activebackground=SURFACE, activeforeground=ACCENT,
            relief="flat", bd=0, cursor="hand2", width=2,
        )
        self._shuffle_btn.pack(side=tk.LEFT, padx=(5, 0))
        self._bottom_btns.append(self._shuffle_btn)

        self._vol_icon = tk.Label(
            bottom, text="🔊", font=("Segoe UI", 13), bg=BG, fg=TEXT_DIM,
            cursor="hand2", width=2,
        )
        self._vol_icon.pack(side=tk.RIGHT, padx=(0, 6))
        self._vol_icon.bind("<Button-1>", self._toggle_mute)

        self._vol_canvas = tk.Canvas(
            bottom, bg=BG, highlightthickness=0, width=60, height=16, cursor="hand2",
        )
        self._vol_canvas.pack(side=tk.RIGHT, padx=(0, 4))
        self._vol_canvas.bind("<Button-1>", self._on_vol_click)
        self._vol_canvas.bind("<B1-Motion>", self._on_vol_drag)
        self.root.after(50, self._draw_vol_bar)

        self._settings_btn = tk.Button(
            bottom, text="⚙", command=self._open_settings,
            font=("Segoe UI", 11), bg=BG, fg=TEXT_DIM,
            activebackground=SURFACE, activeforeground=ACCENT,
            relief="flat", bd=0, cursor="hand2", width=2,
        )
        self._settings_btn.pack(side=tk.RIGHT, padx=(0, 4))
        self._bottom_btns.append(self._settings_btn)

    def _open_settings(self):
        win = getattr(self, "_settings_win", None)
        if win and win.win.winfo_exists():
            win.win.lift()
            win.win.focus_set()
            return
        self._settings_win = SettingsWindow(self)

    def _set_music_dir(self, path, done=None):
        path = os.path.normpath(path)
        if not os.path.isdir(path):
            return False
        if os.path.normcase(path) == os.path.normcase(self._get_music_dir()):
            if done:
                done()
            return True
        playing = self._playing_path
        self.cfg["music_dir"] = path
        config.save(self.cfg)

        def after_scan():
            if playing:
                try:
                    self.current_index = self.playlist.index(playing)
                    self._refresh_track_list()
                except ValueError:
                    pass
            if done:
                done()

        self._scan_folders(done=after_scan)
        return True

    def _set_viz_bars(self, n):
        n = max(10, min(64, int(n)))
        if n == self.cfg.get("viz_bars"):
            return
        self.cfg["viz_bars"] = n
        self.visualizer.bar_count = n
        if getattr(self, "_viz_save_job", None):
            self.root.after_cancel(self._viz_save_job)
        self._viz_save_job = self.root.after(600, self._save_viz_bars)

    def _save_viz_bars(self):
        self._viz_save_job = None
        config.save(self.cfg)

    def _set_accent(self, color):
        self._apply_accent_globals(color)
        self.cfg["accent"] = color
        config.save(self.cfg)
        self.visualizer.set_accent(color)
        self.animator.set_accent(color)
        self._sync_accent_surfaces()
        self._shuffle_btn.config(fg=ACCENT if self._shuffle else TEXT_DIM)
        self._update_tab_btn_colors()
        self._update_seek_bar()
        self._draw_vol_bar()
        self._refresh_track_list()
        self._refresh_fav_list()
        self._refresh_pl_list()

    def _sync_accent_surfaces(self):
        for d in self._dividers:
            d.config(bg=BORDER)
        self._view_favs.config(bg=SURFACE)
        self._panel_pls.config(bg=SURFACE)
        self._track_canvas.config(bg=SURFACE)
        self._fav_list.config(selectbackground=BORDER, selectforeground=ACCENT)
        self._pl_list.config(selectbackground=BORDER, selectforeground=ACCENT)
        if getattr(self, "_fav_btn_row", None):
            self._fav_btn_row.config(bg=SURFACE)
        for b in self._tab_btns.values():
            b.config(activebackground=SURFACE, activeforeground=ACCENT)
        for b in self._bottom_btns:
            b.config(activebackground=SURFACE, activeforeground=ACCENT)
        if getattr(self, "_fav_remove_btn", None):
            self._fav_remove_btn.config(activebackground=BORDER,
                                        activeforeground=ACCENT)
        search_bg = self._blend(ACCENT, BG, 0.03)
        self._search_row.config(bg=search_bg)
        self._search_entry.config(bg=search_bg)
        self._search_icon_lbl.config(bg=search_bg)

    def _on_vol_click(self, event):
        self._vol_dragging = True
        self._set_vol_from_x(event.x)
        self.root.bind("<B1-Motion>", self._on_vol_motion)
        self.root.bind("<ButtonRelease-1>", self._on_vol_release)

    def _on_vol_motion(self, event):
        if not getattr(self, "_vol_dragging", False):
            return
        x = event.x_root - self._vol_canvas.winfo_rootx()
        self._set_vol_from_x(x)

    def _on_vol_release(self, event):
        self._vol_dragging = False
        try:
            self.root.unbind("<B1-Motion>")
            self.root.unbind("<ButtonRelease-1>")
        except tk.TclError:
            pass

    def _on_vol_drag(self, event):
        self._set_vol_from_x(event.x)

    def _set_vol_from_x(self, x):
        w = self._vol_canvas.winfo_width()
        if w <= 0:
            return
        ratio = max(0.0, min(1.0, x / w))
        self.engine.volume = ratio
        self._vol_icon.config(text="🔇" if ratio <= 0 else "🔊")
        self._draw_vol_bar()

    def _draw_vol_bar(self):
        c = self._vol_canvas
        c.delete("all")
        w = c.winfo_width()
        if w <= 0:
            w = 60
        bar_y = 6
        bar_h = 4
        c.create_rectangle(2, bar_y, w - 2, bar_y + bar_h, fill=SURFACE, outline="")
        ratio = self.engine.volume
        fill_x = 2 + ratio * (w - 4)
        if fill_x > 2:
            c.create_rectangle(2, bar_y, fill_x, bar_y + bar_h, fill=ACCENT, outline="")
        handle_r = 4
        cx = max(2 + handle_r, min(w - 2 - handle_r, fill_x))
        c.create_oval(cx - handle_r, bar_y + bar_h // 2 - handle_r,
                      cx + handle_r, bar_y + bar_h // 2 + handle_r,
                      fill=TEXT, outline="")

    def _toggle_mute(self, event=None):
        if self.engine.volume > 0:
            self._prev_vol = self.engine.volume
            self.engine.volume = 0
            self._vol_icon.config(text="🔇")
        else:
            prev = getattr(self, "_prev_vol", 0.7)
            self.engine.volume = prev
            self._vol_icon.config(text="🔊")
        self._draw_vol_bar()

    def _on_track_right_click(self, event):
        idx = self._track_y_to_index(event.y + self._track_scroll)
        source = self._search_results if self._searching else self.playlist
        if not (0 <= idx < len(source)):
            return
        path = source[idx]
        menu = tk.Menu(self.root, tearoff=0, bg=BG, fg=TEXT,
                       activebackground=SURFACE, activeforeground=ACCENT,
                       font=("Segoe UI", 8), bd=0)
        label = ("Remove from Favorites" if path in self._favorites
                 else "Add to Favorites")
        menu.add_command(label=label, command=lambda p=path: self._fav_toggle(p))
        menu.tk_popup(event.x_root, event.y_root)

    def _fav_toggle(self, path):
        if path in self._favorites:
            self._favorites.discard(path)
        else:
            self._favorites.add(path)
        self.cfg["favorites"] = sorted(self._favorites)
        config.save(self.cfg)
        self._refresh_track_list()
        self._refresh_fav_list()

    def _refresh_fav_list(self):
        self._fav_list.delete(0, tk.END)
        favs = self.cfg.get("favorites", [])
        for path in favs:
            name = os.path.splitext(os.path.basename(path))[0]
            if path == self._playing_path:
                self._fav_list.insert(tk.END, f"▶ {name}")
                self._fav_list.itemconfig(self._fav_list.size() - 1, fg=ACCENT)
            else:
                self._fav_list.insert(tk.END, f"♥ {name}")
                self._fav_list.itemconfig(self._fav_list.size() - 1, fg=TEXT_DIM)
        if self._playing_path in favs:
            self._fav_list.see(favs.index(self._playing_path))

    def _on_fav_double_click(self, event):
        sel = self._fav_list.curselection()
        if not sel:
            return
        favs = self.cfg.get("favorites", [])
        if sel[0] < len(favs):
            self._play_from_list(favs, sel[0])

    def _fav_remove(self):
        sel = self._fav_list.curselection()
        if not sel:
            return
        favs = self.cfg.get("favorites", [])
        if sel[0] < len(favs):
            favs.pop(sel[0])
            self.cfg["favorites"] = favs
            config.save(self.cfg)
            self._favorites = set(favs)
            self._refresh_fav_list()

    def _set_title(self, text):
        pass

    def get_all_playlist_names(self):
        return list(self._all_playlists.keys())

    def get_playlist(self, name):
        return list(self._all_playlists.get(name, []))

    def _toggle_play(self):
        if self.engine.is_playing:
            self.engine.pause()
            self.play_btn.config(text="▶")
            self._defer_panther_pause()
        elif self.engine.is_paused:
            self._cancel_panther_pause()
            self.engine.resume()
            self.play_btn.config(text="⏸")
            self.animator.play()
        else:
            if self.engine.is_loaded:
                self._cancel_panther_pause()
                self.engine.play()
                self.play_btn.config(text="⏸")
                self.animator.play()
            elif 0 <= self.current_index < len(self.playlist):
                self._play_index(self.current_index)
            elif self.playlist:
                self._play_index(0)

    def _defer_panther_pause(self):
        self._cancel_panther_pause()
        self._settle_ticks = 0
        self._panther_settle_poll()

    def _cancel_panther_pause(self):
        if getattr(self, "_panther_pause_job", None):
            try:
                self.root.after_cancel(self._panther_pause_job)
            except tk.TclError:
                pass
            self._panther_pause_job = None

    def _panther_settle_poll(self):
        self._panther_pause_job = None
        if self.engine.is_playing:
            return
        try:
            peak = float(np.max(self.visualizer._smoothed))
        except Exception:
            peak = 0.0
        self._settle_ticks += 1
        if peak < 0.06 or self._settle_ticks > 50:
            self.animator.pause()
            return
        self._panther_pause_job = self.root.after(80, self._panther_settle_poll)

    def _toggle_shuffle(self):
        self._shuffle = not self._shuffle
        self._shuffle_btn.config(fg=ACCENT if self._shuffle else TEXT_DIM)
        self.cfg["shuffle"] = self._shuffle
        config.save(self.cfg)

    def _play_index(self, index):
        if index < 0 or index >= len(self.playlist):
            return
        self._queue = None
        self.current_index = index
        self._play_path(self.playlist[index])

    def _play_from_list(self, pool, idx):
        if idx < 0 or idx >= len(pool):
            return
        self._queue = list(pool)
        self._queue_pos = idx
        self._play_path(pool[idx])

    def _play_path(self, path):
        if not os.path.isfile(path):
            self._handle_bad_track(path, "file not found")
            return
        try:
            self.engine.load(path)
            self.engine.play()
        except Exception as err:
            self._handle_bad_track(path, err)
            return
        self._fail_streak = 0
        self._playing_path = path
        self.play_btn.config(text="⏸")
        self.animator.play()
        meta = self.engine.get_metadata(path)
        label = meta["title"]
        if meta["artist"]:
            label += f"  -  {meta['artist']}"
        self._set_title(label)
        self._refresh_track_list()
        self._refresh_fav_list()

    def _handle_bad_track(self, path, err):
        print(f"[pulse] skipping unplayable track ({err}): {path}")
        self._playing_path = None
        self._fail_streak = getattr(self, "_fail_streak", 0) + 1
        self.play_btn.config(text="▶")
        self.animator.pause()
        self._refresh_fav_list()
        if self._fail_streak < 3:
            self.root.after(200, self._next)
        else:
            self._fail_streak = 0

    def _active_pool(self):
        if self._queue is not None:
            return self._queue, self._queue_pos
        return self.playlist, self.current_index

    def _next(self):
        pool, pos = self._active_pool()
        if not pool:
            return
        if self._shuffle:
            idx = random.randint(0, len(pool) - 1)
            if len(pool) > 1 and idx == pos:
                idx = (idx + 1) % len(pool)
        else:
            idx = (pos + 1) % len(pool)
        if self._queue is not None:
            self._queue_pos = idx
            self._play_path(pool[idx])
        else:
            self._play_index(idx)

    def _prev(self):
        if self.engine.get_position() > 3:
            self.engine.seek(0)
            return
        pool, pos = self._active_pool()
        if not pool:
            return
        if self._shuffle:
            idx = random.randint(0, len(pool) - 1)
            if len(pool) > 1 and idx == pos:
                idx = (idx + 1) % len(pool)
        else:
            idx = (pos - 1) % len(pool)
        if self._queue is not None:
            self._queue_pos = idx
            self._play_path(pool[idx])
        else:
            self._play_index(idx)

    @staticmethod
    def _blend(fg_hex, bg_hex, t):
        fr, fgc, fb = (int(fg_hex[i:i + 2], 16) for i in (1, 3, 5))
        br, bgc, bb = (int(bg_hex[i:i + 2], 16) for i in (1, 3, 5))
        return "#{:02x}{:02x}{:02x}".format(
            round(br + (fr - br) * t),
            round(bgc + (fgc - bgc) * t),
            round(bb + (fb - bb) * t),
        )

    @staticmethod
    def _fmt_time(sec):
        sec = max(0, int(sec))
        return f"{sec // 60}:{sec % 60:02d}"

    def _update_timer(self):
        if self.engine.is_playing or self.engine.is_paused:
            dur = self.engine.duration
            if self._seek_dragging:
                pos = self._seek_time
            elif self._seek_settle and time.monotonic() - self._seek_settle < 0.5:
                pos = self._seek_time
            else:
                pos = self.engine.get_position()
            self._ts_cur.config(text=self._fmt_time(pos))
            self._ts_dur.config(text=self._fmt_time(dur))
            self._update_seek_bar()
            if dur > 0 and pos >= dur - 0.1 and self.engine.is_playing:
                self._next()
        elif self.engine.is_loaded:
            self._ts_cur.config(text=self._fmt_time(self.engine.get_position()))
            self._ts_dur.config(text=self._fmt_time(self.engine.duration))
            self._update_seek_bar()
            self.animator.pause()
        else:
            self._ts_cur.config(text="0:00")
            self._ts_dur.config(text="0:00")
            self._seek_canvas.delete("all")
            self.animator.pause()
        self.root.after(100, self._update_timer)

    def _quit(self):
        self.animator.destroy()
        self.cfg["window_x"] = self.root.winfo_x()
        self.cfg["window_y"] = self.root.winfo_y()
        self.cfg["volume"] = self.engine.volume
        self.cfg["shuffle"] = self._shuffle
        self.cfg["active_playlist"] = self._active_playlist
        if self._playing_path:
            self.cfg["last_track"] = self._playing_path
            self.cfg["last_position"] = self.engine.get_position()
        else:
            self.cfg["last_track"] = None
            self.cfg["last_position"] = 0
        config.save(self.cfg)
        self.visualizer.destroy()
        self.engine.cleanup()
        self.root.destroy()

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._quit)
        self.root.mainloop()
