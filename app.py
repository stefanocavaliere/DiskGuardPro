"""
DiskGuard Pro 2.0 — interfaccia stile Samsung Magician
Sidebar + selettore drive + card (Salute / Temperatura / TBW) + pagine:
Dashboard, Performance Benchmark, Diagnostica, Recupero Dati, Strumenti.

Avvio:
    pip install -r requirements.txt
    python app.py
Su Windows: eseguire come Amministratore per SMART / disco raw.
"""
import os
import sys
import threading
import tkinter as tk
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import customtkinter as ctk

from core.disks import get_physical_disks
from core.smart import read_smart, health_score
from core.recovery import (quick_scan_deleted, carve_file, hex_preview,
                           copy_with_progress, SIGNATURES, validate_file,
                           file_hashes, image_preview, findings_report)
from core.monitor import TempMonitor, disk_benchmark
from core.analysis import (get_layout, surface_scan, disk_usage,
                           io_latency_test, get_shadow_copies)
from core.ai import predict, ai_verdict, temp_anomaly, scan_unknown, rank_files
from core.ui_pages import AppPagesMixin
from core.ui_ops import AppOpsMixin

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

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

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
        if color: self._color = color
        if center is not None: self._center = center
        if sub is not None: self._sub = sub
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
        # soglia
        ya = y(alert)
        c.create_line(0, ya, self.w, ya, fill=RED, dash=(4, 3))
        pts = []
        n = len(values)
        for i, v in enumerate(values):
            x = 6 + i / max(1, n - 1) * (self.w - 12) if n > 1 else self.w / 2
            pts += [x, y(v)]
        if len(pts) >= 4:
            c.create_line(*pts, fill=ACCENT, width=2, smooth=True)


# =====================================================================
class App(AppPagesMixin, AppOpsMixin, ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("DiskGuard Pro — Drive Manager")
        self.geometry("1280x800")
        self.minsize(1100, 700)
        self.configure(fg_color=BG)

        self.all_disks = []     # fisici + logici
        self.physicals = []     # solo fisici (selettore)
        self.current = None
        self.attrs, self.info = [], {}
        self.score = (0, "—", "green")
        self.temps = {}         # device -> [storico]
        self.recovered = []
        self.scan_stop = {"stop": False}

        self.monitor = TempMonitor(self._poll_temps, interval_s=5,
                                   alert_temp=55, on_alert=self._on_alert)
        self.monitor.start()

        self._build_shell()
        self.refresh_disks()
        self.after(3000, self._tick)

    # ================= SHELL =================
    def _build_shell(self):
        # ---- sidebar ----
        self.side = ctk.CTkFrame(self, fg_color=SIDEBAR, width=218, corner_radius=0)
        self.side.pack(side="left", fill="y")
        self.side.pack_propagate(False)

        logo = ctk.CTkLabel(self.side, text="🛡️  DiskGuard Pro",
                            font=("Segoe UI", 17, "bold"), text_color="white",
                            anchor="w")
        logo.pack(fill="x", padx=18, pady=(20, 2))
        ctk.CTkLabel(self.side, text="DRIVE MANAGER  v4.0",
                     font=("Segoe UI", 9), text_color=MUTED, anchor="w").pack(
                         fill="x", padx=18, pady=(0, 18))

        self.nav_btns = {}
        for key, icon, label in [
            ("dash", "◉", "Drive Dashboard"),
            ("perf", "⚡", "Performance"),
            ("diag", "🩺", "Diagnostica"),
            ("analysis", "🗺", "Analisi Disco"),
            ("ai", "🤖", "AI Predittiva"),
            ("rec", "🧲", "Recupero Dati"),
            ("tools", "🧰", "Strumenti"),
        ]:
            b = ctk.CTkButton(self.side, text=f"  {icon}   {label}",
                              font=("Segoe UI", 12), anchor="w",
                              fg_color="transparent", hover_color=CARD2,
                              text_color=MUTED, height=44, corner_radius=8,
                              command=lambda k=key: self.show(k))
            b.pack(fill="x", padx=10, pady=2)
            self.nav_btns[key] = b

        self.side_bottom = ctk.CTkLabel(self.side, text="", font=FONTS["small"],
                                       text_color=MUTED, anchor="w",
                                       justify="left")
        self.side_bottom.pack(side="bottom", fill="x", padx=18, pady=16)

        # ---- area principale ----
        self.main = ctk.CTkFrame(self, fg_color=BG)
        self.main.pack(side="left", fill="both", expand=True)

        # topbar con selettore drive stile Magician
        top = ctk.CTkFrame(self.main, fg_color=BG)
        top.pack(fill="x", padx=20, pady=(16, 6))
        ctk.CTkLabel(top, text="Unità", font=FONTS["h"],
                     text_color=TXT).pack(side="left")
        self.drive_menu = ctk.CTkOptionMenu(top, width=380,
                                            fg_color=CARD2, button_color=ACCENT,
                                            font=FONTS["body"],
                                            command=self._on_drive_pick)
        self.drive_menu.pack(side="left", padx=12)
        ctk.CTkButton(top, text="⟳  Aggiorna", width=110,
                      fg_color=CARD2, hover_color="#2a3040",
                      command=self.refresh_disks).pack(side="left")
        self.admin_badge = ctk.CTkLabel(top, text="", font=FONTS["small"],
                                       text_color=MUTED)
        self.admin_badge.pack(side="right")

        # pagine
        self.pages = {}
        for key in ["dash", "perf", "diag", "analysis", "ai", "rec", "tools"]:
            f = ctk.CTkFrame(self.main, fg_color=BG)
            self.pages[key] = f
        self._build_dash(self.pages["dash"])
        self._build_perf(self.pages["perf"])
        self._build_diag(self.pages["diag"])
        self._build_analysis(self.pages["analysis"])
        self._build_ai(self.pages["ai"])
        self._build_rec(self.pages["rec"])
        self._build_tools(self.pages["tools"])

        # status bar
        self.status = ctk.CTkLabel(self.main, text="Pronto.",
                                   font=FONTS["small"], text_color=MUTED,
                                   anchor="w")
        self.status.pack(side="bottom", fill="x", padx=22, pady=8)
        self.show("dash")

    def show(self, key):
        for k, f in self.pages.items():
            f.pack_forget()
        self.pages[key].pack(fill="both", expand=True)
        for k, b in self.nav_btns.items():
            active = (k == key)
            b.configure(fg_color=CARD2 if active else "transparent",
                        text_color="white" if active else MUTED)

    def set_status(self, t):
        try:
            self.status.configure(text=t)
        except Exception:
            pass

    # ================= DASHBOARD =================
    def _card(self, parent, **kw):
        kw.setdefault("fg_color", CARD)
        kw.setdefault("corner_radius", 14)
        return ctk.CTkFrame(parent, **kw)

    def _build_dash(self, f):
        wrap = ctk.CTkScrollableFrame(f, fg_color=BG)
        wrap.pack(fill="both", expand=True, padx=20, pady=10)

        # riga 1: Salute | Temperatura | Vita residua/TBW
        row = ctk.CTkFrame(wrap, fg_color=BG)
        row.pack(fill="x", pady=(0, 12))

        c1 = self._card(row)
        c1.pack(side="left", fill="both", expand=True, padx=(0, 6))
        ctk.CTkLabel(c1, text="Stato di salute", font=FONTS["small"],
                     text_color=MUTED).pack(anchor="w", padx=16, pady=(14, 0))
        self.ring = Ring(c1, size=150)
        self.ring.pack(pady=8)
        self.health_detail = ctk.CTkLabel(c1, text="", font=FONTS["small"],
                                         text_color=MUTED)
        self.health_detail.pack(pady=(0, 14))

        c2 = self._card(row)
        c2.pack(side="left", fill="both", expand=True, padx=6)
        ctk.CTkLabel(c2, text="Temperatura", font=FONTS["small"],
                     text_color=MUTED).pack(anchor="w", padx=16, pady=(14, 0))
        self.temp_big = ctk.CTkLabel(c2, text="—", font=("Segoe UI", 40, "bold"),
                                    text_color="white")
        self.temp_big.pack(pady=(6, 0))
        self.temp_state = ctk.CTkLabel(c2, text="", font=FONTS["body"])
        self.temp_state.pack()
        self.spark = Spark(c2)
        self.spark.pack(pady=8)
        ctk.CTkLabel(c2, text="Ultimi 5 minuti • soglia allarme 55 °C",
                     font=("Segoe UI", 9), text_color=MUTED).pack(pady=(0, 12))

        c3 = self._card(row)
        c3.pack(side="left", fill="both", expand=True, padx=(6, 0))
        ctk.CTkLabel(c3, text="Vita residua / Scritture totali",
                     font=FONTS["small"], text_color=MUTED).pack(
                         anchor="w", padx=16, pady=(14, 0))
        self.tbw_big = ctk.CTkLabel(c3, text="—", font=("Segoe UI", 30, "bold"),
                                   text_color="white")
        self.tbw_big.pack(pady=(14, 0))
        self.tbw_sub = ctk.CTkLabel(c3, text="", font=FONTS["body"],
                                   text_color=MUTED)
        self.tbw_sub.pack()
        self.wear_bar = ctk.CTkProgressBar(c3, width=220, progress_color=GREEN)
        self.wear_bar.pack(pady=14)
        self.wear_bar.set(0.9)
        self.wear_lbl = ctk.CTkLabel(c3, text="", font=FONTS["small"],
                                   text_color=MUTED)
        self.wear_lbl.pack(pady=(0, 12))

        # riga 2: volumi
        vol = self._card(wrap)
        vol.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(vol, text="Volumi", font=FONTS["h"],
                     text_color="white").pack(anchor="w", padx=16, pady=(14, 4))
        self.vol_box = ctk.CTkFrame(vol, fg_color="transparent")
        self.vol_box.pack(fill="x", padx=16, pady=(0, 14))

        # riga 3: info drive + azioni
        bottom = ctk.CTkFrame(wrap, fg_color=BG)
        bottom.pack(fill="x")
        info = self._card(bottom)
        info.pack(side="left", fill="both", expand=True, padx=(0, 6))
        ctk.CTkLabel(info, text="Informazioni unità", font=FONTS["h"],
                     text_color="white").pack(anchor="w", padx=16, pady=(14, 6))
        self.info_grid = ctk.CTkFrame(info, fg_color="transparent")
        self.info_grid.pack(fill="x", padx=16, pady=(0, 14))

        acts = self._card(bottom)
        acts.pack(side="left", fill="y", padx=(6, 0))
        acts.configure(width=250)
        ctk.CTkLabel(acts, text="Azioni rapide", font=FONTS["h"],
                     text_color="white").pack(anchor="w", padx=16, pady=(14, 8))
        for txt, cmd in [
            ("🩺  Esegui diagnostica", lambda: self.show("diag")),
            ("⚡  Test prestazioni", lambda: self.show("perf")),
            ("🧲  Recupera dati", lambda: self.show("rec")),
            ("📥  Esporta report", self.export_report),
        ]:
            ctk.CTkButton(acts, text=txt, anchor="w", fg_color=CARD2,
                          hover_color="#2a3040", height=36,
                          command=cmd).pack(fill="x", padx=14, pady=4)
        ctk.CTkLabel(acts, text="", font=FONTS["small"]).pack(pady=6)

    # ================= PERFORMANCE =================
    def _build_perf(self, f):
        wrap = ctk.CTkFrame(f, fg_color=BG)
        wrap.pack(fill="both", expand=True, padx=20, pady=10)
        ctk.CTkLabel(wrap, text="Performance Benchmark",
                     font=FONTS["title"], text_color="white").pack(anchor="w")
        ctk.CTkLabel(wrap, text="Test sequenziale lettura/scrittura (file 100 MB temporaneo).",
                     font=FONTS["small"], text_color=MUTED).pack(anchor="w",
                                                                 pady=(0, 12))
        row = ctk.CTkFrame(wrap, fg_color=BG)
        row.pack(fill="x")
        self.rd_card = self._perf_card(row, "LETTURA SEQUENZIALE")
        self.rd_card.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.wr_card = self._perf_card(row, "SCRITTURA SEQUENZIALE")
        self.wr_card.pack(side="left", fill="both", expand=True, padx=(6, 0))

        bar = ctk.CTkFrame(wrap, fg_color=BG)
        bar.pack(fill="x", pady=14)
        ctk.CTkButton(bar, text="▶   Avvia test", fg_color=ACCENT,
                      hover_color="#1f5fd6", height=40, width=200,
                      font=("Segoe UI", 12, "bold"),
                      command=self.do_bench).pack(side="left")
        self.bench_prog = ctk.CTkProgressBar(bar, width=320)
        self.bench_prog.pack(side="left", padx=14)
        self.bench_prog.set(0)
        self.bench_msg = ctk.CTkLabel(bar, text="", font=FONTS["small"],
                                     text_color=MUTED)
        self.bench_msg.pack(side="left")

        hist = self._card(wrap)
        hist.pack(fill="both", expand=True, pady=(4, 0))
        ctk.CTkLabel(hist, text="Cronologia test", font=FONTS["h"],
                     text_color="white").pack(anchor="w", padx=16, pady=(12, 4))
        self.bench_hist = ctk.CTkTextbox(hist, height=140, fg_color=CARD2,
                                        text_color=TXT, font=FONTS["mono"])
        self.bench_hist.pack(fill="both", expand=True, padx=16, pady=(0, 14))

    def _perf_card(self, parent, title):
        c = self._card(parent)
        ctk.CTkLabel(c, text=title, font=FONTS["small"],
                     text_color=MUTED).pack(anchor="w", padx=16, pady=(14, 0))
        big = ctk.CTkLabel(c, text="—", font=("Segoe UI", 38, "bold"),
                           text_color="white")
        big.pack(pady=(8, 0))
        ctk.CTkLabel(c, text="MB/s", font=FONTS["small"],
                     text_color=MUTED).pack(pady=(0, 14))
        c.big = big
        return c

    # ================= DIAGNOSTICA =================
    def _build_diag(self, f):
        wrap = ctk.CTkFrame(f, fg_color=BG)
        wrap.pack(fill="both", expand=True, padx=20, pady=10)
        ctk.CTkLabel(wrap, text="Diagnostica",
                     font=FONTS["title"], text_color="white").pack(anchor="w")
        ctk.CTkLabel(wrap, text="Controllo S.M.A.R.T. + self-test del disco selezionato.",
                     font=FONTS["small"], text_color=MUTED).pack(anchor="w",
                                                                 pady=(0, 10))
        bar = ctk.CTkFrame(wrap, fg_color=BG)
        bar.pack(fill="x", pady=(0, 10))
        ctk.CTkButton(bar, text="⚡ Test rapido S.M.A.R.T.", fg_color=ACCENT,
                      hover_color="#1f5fd6", command=self.do_short).pack(side="left")
        ctk.CTkButton(bar, text="🔍 Self-test esteso", fg_color=CARD2,
                      hover_color="#2a3040",
                      command=self.do_full).pack(side="left", padx=8)
        self.diag_prog = ctk.CTkProgressBar(bar, width=260)
        self.diag_prog.pack(side="left", padx=8)
        self.diag_prog.set(0)

        self.diag_log = ctk.CTkTextbox(wrap, height=130, fg_color=CARD2,
                                      text_color=TXT, font=FONTS["mono"])
        self.diag_log.pack(fill="x", pady=(0, 10))

        tbl = self._card(wrap)
        tbl.pack(fill="both", expand=True)
        ctk.CTkLabel(tbl, text="Attributi S.M.A.R.T.", font=FONTS["h"],
                     text_color="white").pack(anchor="w", padx=16, pady=(12, 4))
        self.smart_rows = ctk.CTkScrollableFrame(tbl, fg_color="transparent",
                                                height=220)
        self.smart_rows.pack(fill="both", expand=True, padx=10, pady=(0, 12))


    def export_report(self):
        from tkinter import filedialog, messagebox
        if not self.current:
            return
        p = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=f"diskguard_report_{self.current.device_id}.txt",
            filetypes=[("Testo", "*.txt")])
        if not p:
            return
        with open(p, "w", encoding="utf-8") as fo:
            fo.write(f"DiskGuard Pro — Report {datetime.now():%d/%m/%Y %H:%M}\n")
            fo.write(f"Modello: {self.current.friendly_name} ({self.current.device_id})\n")
            fo.write(f"Salute: {self.score[0]}/100 {self.score[1]} | Temp: {self.info.get('temp_c')}\n")
            try:
                pa = predict(self.attrs, self.info)
                fo.write(f"AI: rischio 30gg {pa['p30']}% ({pa['risk']}) | "
                          f"90gg {pa['p90']}% | 180gg {pa['p180']}%\n")
                fo.write(f"AI azione: {pa['action']}\n")
                fo.write(f"AI fattori: {pa['factors']}\n")
            except Exception:
                pass
            fo.write("\n")
            for a in self.attrs:
                fo.write(f"{a}\n")
        messagebox.showinfo("DiskGuard Pro", f"Report salvato:\n{p}")


if __name__ == "__main__":
    App().mainloop()
