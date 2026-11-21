import tkinter as tk
import numpy as np


class Visualizer:
    def __init__(self, parent, engine, width=230, height=44,
                 bar_count=20, accent="#c0392b", trace_color=None,
                  dip_center=None, dip_depth=0.75, dip_sigma=8):
        self.engine = engine
        self.width = width
        self.height = height
        self.bar_count = bar_count
        self.accent = accent
        self._trace = trace_color or accent
        self._fixed_trace = trace_color is not None
        self.canvas = tk.Canvas(
            parent, width=width, height=height,
            bg="#0d0d0d", highlightthickness=0,
        )
        self.dip_center = dip_center if dip_center is not None else width * 0.09
        self.dip_depth = dip_depth
        self.dip_sigma = dip_sigma

        self._running = True
        self._suspended = False
        self._scroll_x = 0.0
        self._scroll_speed = 0.15
        self._grid_drift = 0.35
        self._setup_geometry(width, height)
        self._init_bars()
        self._animate()

    def _setup_geometry(self, width, height):
        self.width = width
        self.height = height
        self._margin = 4
        self._bar_w = 2
        self._bar_gap = 3
        self._baseline = height - 3
        self._usable_h = height - 8
        self._n_bars = max(10, int(
            (width - self._margin * 2 + self._bar_gap)
            // (self._bar_w + self._bar_gap)
        ))
        self._bar_x1 = [
            self._margin + i * (self._bar_w + self._bar_gap)
            for i in range(self._n_bars)
        ]
        xs = np.array([
            x + self._bar_w / 2 for x in self._bar_x1
        ])
        dip = self.dip_depth * np.exp(
            -((xs - self.dip_center) ** 2) / (2 * self.dip_sigma ** 2)
        )
        self._env = 1.0 - dip
        self._smoothed = np.zeros(self._n_bars)
        self._line_buf = np.zeros(self._n_bars)
        self._line_amp = 11.0

    def _dim_color(self, keep):
        base_r, base_g, base_b = 13, 13, 13
        hex_c = self._trace.lstrip("#")
        ar = int(hex_c[0:2], 16)
        ag = int(hex_c[2:4], 16)
        ab = int(hex_c[4:6], 16)
        r = int(base_r + (ar - base_r) * keep)
        g = int(base_g + (ag - base_g) * keep)
        b = int(base_b + (ab - base_b) * keep)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _glow_color(self, intensity):
        return self._dim_color(min(intensity * 0.18, 1.0))

    def _zone_color(self, i):
        t = i / max(self._n_bars - 1, 1)
        hex_c = self._trace.lstrip("#")
        r = int(hex_c[0:2], 16)
        g = int(hex_c[2:4], 16)
        b = int(hex_c[4:6], 16)
        if t < 0.33:
            zone_t = t / 0.33
            r2 = max(int(r * 0.4), 0)
            g2 = max(int(g * 0.15), 0)
            b2 = max(int(b * 0.15), 0)
            r = int(r2 + (r - r2) * zone_t)
            g = int(g2 + (g - g2) * zone_t)
            b = int(b2 + (b - b2) * zone_t)
        elif t > 0.66:
            zone_t = (t - 0.66) / 0.34
            r = min(r + int((255 - r) * zone_t * 0.6), 255)
            g = min(g + int((255 - g) * zone_t * 0.6), 255)
            b = min(b + int((255 - b) * zone_t * 0.6), 255)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _init_bars(self):
        self.canvas.delete("all")

        mid_y = self.height / 2
        self._glow_bands = []
        for half_h, base in ((16, 0.04), (10, 0.07), (5, 0.11)):
            rid = self.canvas.create_rectangle(
                0, mid_y - half_h, self.width, mid_y + half_h,
                fill=self._dim_color(base), outline="", tags="glow",
            )
            self._glow_bands.append((rid, base))

        self.canvas.create_rectangle(
            0, 0, self.width - 1, self.height - 1,
            outline=self._dim_color(0.16), width=1,
        )

        grid_c = self._dim_color(0.32)
        center_c = self._dim_color(0.48)
        self._grid_spacing = self.width / 10
        self._n_grid = int(self.width / self._grid_spacing) + 1
        self._grid_ids = []
        for _ in range(self._n_grid):
            top = self.canvas.create_line(0, 2, 0, 7, fill=grid_c)
            bot = self.canvas.create_line(
                0, self.height - 7, 0, self.height - 2, fill=grid_c,
            )
            notch = self.canvas.create_line(
                0, mid_y - 3, 0, mid_y + 3, fill=center_c,
            )
            self._grid_ids.append((top, bot, notch))

        flat = []
        for i in range(self._n_bars):
            flat.append(self._bar_x1[i] + self._bar_w / 2)
            flat.append(mid_y)
        self._scope_line = self.canvas.create_line(
            *flat, fill=center_c, width=1,
            capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True,
        )
        self._grid_off = 0.0

        self._bars = []
        for i in range(self._n_bars):
            x1 = self._bar_x1[i]
            bar = self.canvas.create_rectangle(
                x1, self._baseline, x1 + self._bar_w, self._baseline,
                fill=self._zone_color(i), outline="", tags="bar",
            )
            self._bars.append(bar)

        self.canvas.tag_lower("glow")

    def suspend(self):
        self._suspended = True

    def resume(self):
        self._suspended = False

    def _animate(self):
        if not self._running:
            return
        if self._suspended:
            self.canvas.after(33, self._animate)
            return

        fft = self.engine.get_fft_data()
        if len(fft) < self.bar_count:
            padded = np.zeros(self.bar_count)
            padded[: len(fft)] = fft
            fft = padded

        n = self._n_bars

        self._scroll_x += self._scroll_speed
        shift = int(self._scroll_x)
        if shift:
            self._smoothed = np.roll(self._smoothed, -shift)
            self._scroll_x -= shift

        self._smoothed[:-1] *= 0.999

        bass = float(np.mean(fft[:20]))
        mids = float(np.mean(fft[23:49]))
        treble = float(np.mean(fft[52:]))
        vocal = min(mids * 2.2, 1.0)
        kick = self.engine.get_percussion()
        level = min(kick * 1.6 + bass * 1.4 + mids * 0.25, 1.0)

        new_val = level * 0.98 + 0.015
        cur = self._smoothed[-1]
        rate = 0.8 if new_val > cur else 0.09
        self._smoothed[-1] = cur + (new_val - cur) * rate

        idxs = np.linspace(0, len(fft) - 1, n)
        centers = np.arange(len(fft))
        spec_raw = np.interp(idxs, centers, fft)
        w = 0.30 + 1.5 * np.exp(-((centers - 33.0) ** 2) / (2 * 11.0 ** 2))
        spec_voc = np.clip(np.interp(idxs, centers, fft * w), 0, 1)
        rates = np.where(spec_voc > self._line_buf, 0.5, 0.18)
        self._line_buf += (spec_voc - self._line_buf) * rates

        self._grid_off += (
            self._scroll_speed * (self._bar_w + self._bar_gap)
            * self._grid_drift * (0.35 + 1.65 * vocal)
        )
        if self._grid_off >= self._grid_spacing:
            self._grid_off -= self._grid_spacing
        tick_c = self._dim_color(min(0.32 + 0.55 * vocal, 0.95))
        notch_c = self._dim_color(min(0.48 + 0.45 * vocal, 1.0))
        mid_y = self.height / 2
        step = self._bar_w + self._bar_gap
        for k, (top, bot, notch) in enumerate(self._grid_ids):
            x = k * self._grid_spacing - self._grid_off
            idx = max(0, min(n - 1, int(round((x - self._margin) / step))))
            wy = mid_y - float(self._line_buf[idx]) * self._line_amp
            self.canvas.coords(top, x, 2, x, 7)
            self.canvas.coords(bot, x, self.height - 7, x, self.height - 2)
            self.canvas.coords(notch, x, wy - 3, x, wy + 3)
            self.canvas.itemconfig(top, fill=tick_c)
            self.canvas.itemconfig(bot, fill=tick_c)
            self.canvas.itemconfig(notch, fill=notch_c)

        flat = []
        for i in range(n):
            flat.append(self._bar_x1[i] + self._bar_w / 2)
            flat.append(mid_y - float(self._line_buf[i]) * self._line_amp)
        self.canvas.coords(self._scope_line, *flat)
        self.canvas.itemconfig(
            self._scope_line,
            fill=self._dim_color(min(0.45 + 0.5 * vocal, 1.0)),
        )

        for i in range(n):
            val = max(0.008, self._smoothed[i])
            bar_h = val * self._usable_h * 0.55 * self._env[i]
            top = self._baseline - bar_h
            x1 = self._bar_x1[i]
            self.canvas.coords(
                self._bars[i], x1, top, x1 + self._bar_w, self._baseline,
            )

        glevel = min(treble * 1.6, 1.0)
        for rid, base in self._glow_bands:
            self.canvas.itemconfig(
                rid, fill=self._dim_color(base + glevel * 0.20),
            )

        self.canvas.after(16, self._animate)

    def set_accent(self, color):
        self.accent = color
        if self._fixed_trace:
            return
        self._trace = color
        for i in range(self._n_bars):
            self.canvas.itemconfig(self._bars[i], fill=self._zone_color(i))

    def resize(self, width, height):
        self.canvas.config(width=width, height=height)
        self._setup_geometry(width, height)
        self._init_bars()

    def destroy(self):
        self._running = False
