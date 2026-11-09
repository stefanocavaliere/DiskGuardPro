"""DiskGuard Pro - tema condiviso, font e widget (Ring, Spark)."""
import tkinter as tk

import customtkinter as ctk

# ---------- tema stile Magician ----------
BG = "#0e1013"        # sfondo app
SIDEBAR = "#14171c"   # sidebar
CARD = "#191d24"      # card
CARD2 = "#1f242e"     # card interna
TXT = "#e8ecf3"
MUTED = "#8b95a5"
ACCENT = "#2f7bff"    # blu Samsung-ish
GREEN = "#00c853"
ORANGE = "#ff9100"
RED = "#ff4d5e"

APP_TITLE = "DiskGuard Pro — Drive Manager"

FONTS = {"title": ("Segoe UI", 20, "bold"),
         "h": ("Segoe UI", 14, "bold"),
         "h2": ("Segoe UI", 12, "bold"),
         "body": ("Segoe UI", 11),
         "small": ("Segoe UI", 10),
         "mono": ("Consolas", 10)}


# ---------- widget: anello di avanzamento ----------
class Ring(ctk.CTkFrame):
    """Indicatore circolare stile Magician (canvas)."""
    def __init__(self, master, size=150, width=14, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.size, self.width = size, width
        self.cv = tk.Canvas(self, width=size, height=size, bg=CARD,
                            highlightthickness=0)
        self.cv.pack()
        self._val = 0
        self._color = GREEN
        self._center = ""
        self._sub = ""
        self.draw(0)

    def draw(self, val, color=None, center=None, sub=None):
        self._val = max(0, min(100, val))
        if color:
            self._color = color
        if center is not None:
            self._center = center
        if sub is not None:
            self._sub = sub
        c = self.cv
        c.delete("all")
        pad = self.width // 2 + 4
        c.create_oval(pad, pad, self.size - pad, self.size - pad,
                      outline="#2b313c", width=self.width)
        if self._val > 0:
            extent = self._val * 3.6
            c.create_arc(pad, pad, self.size - pad, self.size - pad,
                         start=90, extent=-extent, outline=self._color,
                         width=self.width, style="arc")
        c.create_text(self.size // 2, self.size // 2 - 8, text=self._center,
                      fill="white", font=("Segoe UI", 22, "bold"))
        c.create_text(self.size // 2, self.size // 2 + 20, text=self._sub,
                      fill=MUTED, font=("Segoe UI", 10))


class Spark(ctk.CTkFrame):
    """Mini-grafico temperatura (canvas)."""
    def __init__(self, master, w=240, h=64, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.cv = tk.Canvas(self, width=w, height=h, bg=CARD,
                            highlightthickness=0)
        self.cv.pack()
        self.w, self.h = w, h

    def plot(self, values, alert=55):
        c = self.cv
        c.delete("all")
        if not values:
            c.create_text(self.w // 2, self.h // 2, text="—",
                          fill=MUTED, font=("Segoe UI", 12))
            return
        vmin = min(min(values) - 2, 30)
        vmax = max(max(values) + 2, alert + 2)

        def y(v):
            return self.h - 6 - (v - vmin) / max(1, vmax - vmin) * (self.h - 14)

        ya = y(alert)
        c.create_line(0, ya, self.w, ya, fill=RED, dash=(4, 3))
        pts = []
        n = len(values)
        for i, v in enumerate(values):
            x = 6 + i / max(1, n - 1) * (self.w - 12) if n > 1 else self.w / 2
            pts += [x, y(v)]
        if len(pts) >= 4:
            c.create_line(*pts, fill=ACCENT, width=2, smooth=True)
