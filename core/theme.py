"""DiskGuard Pro - tema condiviso, font e widget grafici (Ring, Spark, Donut,
AttrBars, MultiChart, TempGauge, HealthTimeline)."""
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
CYAN = "#22d3ee"
GREEN = "#00c853"
ORANGE = "#ff9100"
RED = "#ff4d5e"
PURPLE = "#a78bfa"

APP_TITLE = "DiskGuard Pro — Drive Manager"

FONTS = {"title": ("Segoe UI", 20, "bold"),
         "h": ("Segoe UI", 14, "bold"),
         "h2": ("Segoe UI", 12, "bold"),
         "body": ("Segoe UI", 11),
         "small": ("Segoe UI", 10),
         "mono": ("Consolas", 10)}


def fmt_gb(v):
    try:
        v = float(v)
    except Exception:
        return "—"
    if v >= 1000:
        return f"{v/1000:.2f} TB"
    return f"{v:.0f} GB"


def health_color(key):
    return {"green": GREEN, "orange": ORANGE, "red": RED}.get(key, GREEN)


# ---------- widget: anello di avanzamento ----------
class Ring(ctk.CTkFrame):
    """Indicatore circolare stile Magician (canvas) con tick e fascia."""
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
        import math
        cx = cy = self.size / 2
        # tick ogni 10
        for i in range(0, 101, 10):
            ang = math.radians(90 - i * 3.6)
            r1 = self.size / 2 - 2
            r0 = r1 - (7 if i % 25 == 0 else 4)
            c.create_line(cx + r0 * math.cos(ang), cy - r0 * math.sin(ang),
                          cx + r1 * math.cos(ang), cy - r1 * math.sin(ang),
                          fill="#3a4354", width=2 if i % 25 == 0 else 1)
        pad = self.width // 2 + 10
        c.create_oval(pad, pad, self.size - pad, self.size - pad,
                      outline="#2b313c", width=self.width)
        if self._val > 0:
            extent = self._val * 3.6
            c.create_arc(pad, pad, self.size - pad, self.size - pad,
                         start=90, extent=-extent, outline=self._color,
                         width=self.width, style="arc")
        c.create_text(cx, cy - 8, text=self._center,
                      fill="white", font=("Segoe UI", 22, "bold"))
        c.create_text(cx, cy + 20, text=self._sub,
                      fill=MUTED, font=("Segoe UI", 10))


class Spark(ctk.CTkFrame):
    """Mini-grafico temperatura (canvas) con area sfumata, min/max, soglia."""
    def __init__(self, master, w=240, h=64, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.cv = tk.Canvas(self, width=w, height=h, bg=CARD,
                            highlightthickness=0)
        self.cv.pack()
        self.w, self.h = w, h
        self._last = []

    def plot(self, values, alert=55):
        c = self.cv
        c.delete("all")
        self._last = list(values or [])
        if not values:
            c.create_text(self.w // 2, self.h // 2, text="—",
                          fill=MUTED, font=("Segoe UI", 12))
            return
        vmin = min(min(values) - 2, 30)
        vmax = max(max(values) + 2, alert + 2)

        def y(v):
            return self.h - 10 - (v - vmin) / max(1, vmax - vmin) * (self.h - 22)

        # griglia
        for frac, lab in ((0.15, f"{vmax:.0f}°"), (0.5, ""), (0.85, f"{vmin:.0f}°")):
            yy = self.h * frac
            c.create_line(28, yy, self.w - 4, yy, fill="#232a36")
            if lab:
                c.create_text(14, yy, text=lab, fill=MUTED, font=("Segoe UI", 7))
        # soglia
        ya = y(alert)
        c.create_line(28, ya, self.w - 4, ya, fill=RED, dash=(4, 3))
        c.create_text(self.w - 22, ya - 8, text=f"{alert}°", fill=RED,
                      font=("Segoe UI", 7, "bold"))
        pts = []
        n = len(values)
        for i, v in enumerate(values):
            x = 30 + i / max(1, n - 1) * (self.w - 36) if n > 1 else self.w / 2
            pts += [x, y(v)]
        if len(pts) >= 4:
            # area sotto la curva
            c.create_polygon([pts[0], self.h - 4] + pts + [pts[-2], self.h - 4],
                             fill="#2f7bff", outline="", stipple="gray25")
            c.create_line(*pts, fill=ACCENT, width=2, smooth=True)
            # min/max/current
            mx, mn = max(values), min(values)
            c.create_text(34, 8, text=f"max {mx:.0f}°", fill=ORANGE,
                          font=("Segoe UI", 7), anchor="w")
            c.create_text(self.w - 6, 8, text=f"ora {values[-1]:.0f}°",
                          fill="white", font=("Segoe UI", 8, "bold"), anchor="e")


class AttrBars(ctk.CTkFrame):
    """Barre orizzontali normalizzate per attributi SMART critici."""
    def __init__(self, master, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.cv = tk.Canvas(self, width=300, height=150, bg=CARD,
                            highlightthickness=0)
        self.cv.pack(fill="x")

    def plot(self, items):
        """items: [(label, value0-100, color)] max 6."""
        c = self.cv
        c.delete("all")
        W = 300
        if not items:
            c.create_text(W // 2, 20, text="—", fill=MUTED)
            return
        H = max(60, len(items) * 24 + 8)
        c.configure(height=H)
        for i, (lab, val, col) in enumerate(items[:6]):
            yy = 12 + i * 24
            c.create_text(4, yy, text=lab[:22], fill=MUTED,
                          font=("Segoe UI", 8), anchor="w")
            c.create_rectangle(110, yy - 7, 250, yy + 7, fill="#242c39",
                               outline="")
            w = max(2, min(140, val / 100 * 140))
            c.create_rectangle(110, yy - 7, 110 + w, yy + 7, fill=col,
                               outline="")
            c.create_text(256, yy, text=f"{val:.0f}", fill="white",
                          font=("Segoe UI", 8, "bold"), anchor="w")


class MultiChart(ctk.CTkFrame):
    """Grafico multi-serie (temperatura + salute) con assi e legenda."""
    def __init__(self, master, w=560, h=150, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.cv = tk.Canvas(self, width=w, height=h, bg=CARD,
                            highlightthickness=0)
        self.cv.pack(fill="x")
        self.w, self.h = w, h

    def plot(self, temps, scores, alert=55):
        c = self.cv
        c.delete("all")
        W, H = self.w, self.h
        # assi
        c.create_line(34, 6, 34, H - 18, fill="#3a4354")
        c.create_line(34, H - 18, W - 6, H - 18, fill="#3a4354")
        c.create_text(40, 10, text="°C / score", fill=MUTED,
                      font=("Segoe UI", 7), anchor="w")
        # legenda
        c.create_line(W - 190, 10, W - 172, 10, fill=ORANGE, width=2)
        c.create_text(W - 168, 10, text="temp °C", fill=MUTED,
                      font=("Segoe UI", 7), anchor="w")
        c.create_line(W - 110, 10, W - 92, 10, fill=CYAN, width=2)
        c.create_text(W - 88, 10, text="salute", fill=MUTED,
                      font=("Segoe UI", 7), anchor="w")
        n = max(len(temps), len(scores), 2)
        vmin, vmax = 25, 100

        def X(i):
            return 38 + i / max(1, n - 1) * (W - 48)

        def Y(v):
            return (H - 22) - (v - vmin) / max(1, vmax - vmin) * (H - 34)

        # griglia orizzontale
        for gv in (40, 60, 80):
            c.create_line(34, Y(gv), W - 6, Y(gv), fill="#1e2430")
            c.create_text(30, Y(gv), text=str(gv), fill=MUTED,
                          font=("Segoe UI", 7), anchor="e")
        # soglia temp
        c.create_line(34, Y(alert), W - 6, Y(alert), fill=RED, dash=(4, 3))
        if temps:
            pts = []
            for i, v in enumerate(temps):
                pts += [X(i), Y(min(100, max(0, v)))]
            if len(pts) >= 4:
                c.create_line(*pts, fill=ORANGE, width=2, smooth=True)
                c.create_oval(pts[-2] - 3, pts[-1] - 3, pts[-2] + 3,
                              pts[-1] + 3, fill=ORANGE, outline="")
        if scores:
            pts = []
            for i, v in enumerate(scores):
                pts += [X(i), Y(min(100, max(0, v)))]
            if len(pts) >= 4:
                c.create_line(*pts, fill=CYAN, width=2, smooth=True)


class HealthTimeline(ctk.CTkFrame):
    """Timeline sintetica: pallini colorati per fascia oraria + label."""
    def __init__(self, master, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.cv = tk.Canvas(self, width=560, height=44, bg=CARD,
                            highlightthickness=0)
        self.cv.pack(fill="x")

    def plot(self, entries):
        """entries: [(label, key)] key in green/orange/red/gray."""
        c = self.cv
        c.delete("all")
        cols = {"green": GREEN, "orange": ORANGE, "red": RED, "gray": "#3a4354"}
        n = max(1, len(entries))
        W = 560
        c.create_line(20, 16, W - 20, 16, fill="#2b313c", width=2)
        for i, (lab, key) in enumerate(entries):
            x = 20 + (i / max(1, n - 1) * (W - 40) if n > 1 else (W - 40) / 2)
            c.create_oval(x - 7, 9, x + 7, 23, fill=cols.get(key, "#3a4354"),
                          outline="")
            c.create_text(x, 33, text=lab[:12], fill=MUTED,
                          font=("Segoe UI", 7))
