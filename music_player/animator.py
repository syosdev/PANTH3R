import os
import tkinter as tk
from PIL import Image, ImageTk


class FrameAnimator:
    def __init__(self, canvas, width=40, height=40, fps=16,
                 accent="#c0392b", frame_dir=None, x=0, y=0):
        self.canvas = canvas
        self.width = width
        self.height = height
        self.fps = fps
        self.accent = accent
        self._frame_index = 0
        self._playing = False
        self._tick_id = None
        self._x = x
        self._y = y

        if frame_dir is None:
            frame_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "assets",
            )
        self._frame_dir = frame_dir

        self._photo_images = []
        self._load_frames()

        if self._photo_images:
            self._img_id = self.canvas.create_image(
                x, y, image=self._photo_images[0], anchor="center",
            )
        else:
            self._img_id = None

    def _tint_from_alpha(self, img):
        ar, ag, ab = (
            int(self.accent[1:3], 16),
            int(self.accent[3:5], 16),
            int(self.accent[5:7], 16),
        )
        pixels = img.load()
        w, h = img.size
        for y in range(h):
            for x in range(w):
                r, g, b, a = pixels[x, y]
                if a > 0:
                    t = a / 255.0
                    pixels[x, y] = (
                        int(ar * t),
                        int(ag * t),
                        int(ab * t),
                        a,
                    )
        return img

    def _load_frames(self):
        self._photo_images.clear()
        if not os.path.isdir(self._frame_dir):
            return
        files = sorted(
            f for f in os.listdir(self._frame_dir)
            if f.lower().endswith(".png")
        )
        for fname in files:
            path = os.path.join(self._frame_dir, fname)
            img = Image.open(path).convert("RGBA")
            img = img.resize((self.width, self.height), Image.LANCZOS)
            img = self._tint_from_alpha(img)
            self._photo_images.append(ImageTk.PhotoImage(img))

    def play(self):
        if self._playing or not self._photo_images:
            return
        self._playing = True
        self._tick()

    def pause(self):
        self._playing = False
        if self._tick_id is not None:
            self.canvas.after_cancel(self._tick_id)
            self._tick_id = None

    def _tick(self):
        if not self._playing or not self._photo_images:
            return
        if self._img_id is not None:
            self.canvas.itemconfig(
                self._img_id,
                image=self._photo_images[self._frame_index],
            )
        self._frame_index = (self._frame_index + 1) % len(self._photo_images)
        delay = max(1, 1000 // self.fps)
        self._tick_id = self.canvas.after(delay, self._tick)

    def set_accent(self, color):
        self.accent = color
        self._load_frames()
        if self._img_id is not None and self._photo_images:
            self.canvas.itemconfig(
                self._img_id, image=self._photo_images[0],
            )
        self._frame_index = 0

    def destroy(self):
        self.pause()
        self._photo_images.clear()
