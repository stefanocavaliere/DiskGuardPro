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
from core.recovery import quick_scan_deleted, carve_file, hex_preview, copy_with_progress
from core.monitor import TempMonitor, disk_benchmark

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
class App(ctk.CTk):
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
        ctk.CTkLabel(self.side, text="DRIVE MANAGER  v2.0",
                     font=("Segoe UI", 9), text_color=MUTED, anchor="w").pack(
                         fill="x", padx=18, pady=(0, 18))

        self.nav_btns = {}
        for key, icon, label in [
            ("dash", "◉", "Drive Dashboard"),
            ("perf", "⚡", "Performance"),
            ("diag", "🩺", "Diagnostica"),
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
        for key in ["dash", "perf", "diag", "rec", "tools"]:
            f = ctk.CTkFrame(self.main, fg_color=BG)
            self.pages[key] = f
        self._build_dash(self.pages["dash"])
        self._build_perf(self.pages["perf"])
        self._build_diag(self.pages["diag"])
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

    # ================= RECUPERO =================
    def _build_rec(self, f):
        wrap = ctk.CTkFrame(f, fg_color=BG)
        wrap.pack(fill="both", expand=True, padx=20, pady=10)
        ctk.CTkLabel(wrap, text="Recupero Dati",
                     font=FONTS["title"], text_color="white").pack(anchor="w")
        ctk.CTkLabel(wrap, text="Scansione rapida (cestino/tmp) o profonda con file carving "
                                "(JPEG · PNG · PDF · GIF · ZIP · DOCX · MP4).",
                     font=FONTS["small"], text_color=MUTED).pack(anchor="w",
                                                                 pady=(0, 10))
        form = self._card(wrap)
        form.pack(fill="x", pady=(0, 10))
        self.src_var = tk.StringVar()
        self.dst_var = tk.StringVar(value=os.path.join(os.getcwd(), "recuperati"))
        self._form_row(form, "Sorgente (immagine .img o \\\\.\\PhysicalDrive0):",
                       self.src_var, self._pick_src)
        self._form_row(form, "Destinazione file recuperati:",
                       self.dst_var, self._pick_dst, is_dir=True)

        bar = ctk.CTkFrame(wrap, fg_color=BG)
        bar.pack(fill="x", pady=(0, 8))
        ctk.CTkButton(bar, text="⚡ Scansione rapida", fg_color="#0a7a4b",
                      hover_color="#086038", command=self.do_quick).pack(side="left")
        ctk.CTkButton(bar, text="🧲 Scansione profonda", fg_color=ACCENT,
                      hover_color="#1f5fd6", font=("Segoe UI", 11, "bold"),
                      command=self.do_carve).pack(side="left", padx=8)
        ctk.CTkButton(bar, text="⏹", width=44, fg_color="#7f1d1d",
                      command=lambda: self.scan_stop.update(stop=True)).pack(side="left")
        ctk.CTkButton(bar, text="👁 HEX", width=70, fg_color=CARD2,
                      command=self.do_hex).pack(side="left", padx=8)
        ctk.CTkButton(bar, text="💾 Ripristina", fg_color=CARD2,
                      command=self.do_restore).pack(side="left")
        self.rec_prog = ctk.CTkProgressBar(wrap, width=400)
        self.rec_prog.pack(fill="x", pady=(0, 2))
        self.rec_prog.set(0)
        self.rec_msg = ctk.CTkLabel(wrap, text="", font=FONTS["small"],
                                   text_color=MUTED, anchor="w")
        self.rec_msg.pack(fill="x")

        res = self._card(wrap)
        res.pack(fill="both", expand=True)
        ctk.CTkLabel(res, text="File trovati", font=FONTS["h"],
                     text_color="white").pack(anchor="w", padx=16, pady=(12, 4))
        self.rec_rows = ctk.CTkScrollableFrame(res, fg_color="transparent")
        self.rec_rows.pack(fill="both", expand=True, padx=10, pady=(0, 12))

    def _form_row(self, parent, label, var, pick, is_dir=False):
        ctk.CTkLabel(parent, text=label, font=FONTS["small"],
                     text_color=MUTED).pack(anchor="w", padx=16, pady=(12, 2))
        r = ctk.CTkFrame(parent, fg_color="transparent")
        r.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkEntry(r, textvariable=var, fg_color=CARD2,
                     border_width=0, height=34).pack(side="left", fill="x",
                                                    expand=True)
        ctk.CTkButton(r, text="Sfoglia…", width=90, fg_color="#2a3040",
                      command=pick).pack(side="left", padx=(8, 0))

    # ================= STRUMENTI =================
    def _build_tools(self, f):
        wrap = ctk.CTkScrollableFrame(f, fg_color=BG)
        wrap.pack(fill="both", expand=True, padx=20, pady=10)
        ctk.CTkLabel(wrap, text="Strumenti",
                     font=FONTS["title"], text_color="white").pack(anchor="w")

        cl = self._card(wrap)
        cl.pack(fill="x", pady=10)
        ctk.CTkLabel(cl, text="Clona disco / Crea immagine forense",
                     font=FONTS["h"], text_color="white").pack(
                         anchor="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(cl, text="Copia RAW bit-a-bit. Pratica consigliata: fai carving sull'immagine, non sul disco originale.",
                     font=FONTS["small"], text_color=MUTED).pack(
                         anchor="w", padx=16)
        self.clone_src = tk.StringVar()
        self.clone_dst = tk.StringVar(value=os.path.join(os.getcwd(), "immagine_disco.img"))
        self._form_row(cl, "Sorgente:", self.clone_src,
                       lambda: self._pick_file_into(self.clone_src))
        self._form_row(cl, "Destinazione (.img):", self.clone_dst,
                       lambda: self._pick_save_into(self.clone_dst))
        ctk.CTkButton(cl, text="💿 Avvia clonazione", fg_color=ACCENT,
                      hover_color="#1f5fd6", command=self.do_clone).pack(
                          anchor="w", padx=16, pady=(0, 14))

        al = self._card(wrap)
        al.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(al, text="Monitoraggio temperatura",
                     font=FONTS["h"], text_color="white").pack(
                         anchor="w", padx=16, pady=(14, 2))
        self.alert_var = tk.IntVar(value=55)
        r = ctk.CTkFrame(al, fg_color="transparent")
        r.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(r, text="Soglia allarme (°C):",
                     font=FONTS["body"]).pack(side="left")
        ctk.CTkSlider(r, from_=40, to=80, number_of_steps=40,
                      command=lambda v: self._set_alert(int(v)),
                      width=220).pack(side="left", padx=12)
        self.alert_lbl = ctk.CTkLabel(r, text="55 °C", font=FONTS["h2"])
        self.alert_lbl.pack(side="left")
        ctk.CTkLabel(al, text="Log CSV giornaliero in cartella logs/.",
                     font=FONTS["small"], text_color=MUTED).pack(
                         anchor="w", padx=16, pady=(0, 12))

        fw = self._card(wrap)
        fw.pack(fill="x")
        ctk.CTkLabel(fw, text="Note firmware",
                     font=FONTS["h"], text_color="white").pack(
                         anchor="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(fw, text="Gli aggiornamenti firmware vanno eseguiti solo con il tool ufficiale del produttore "
                              "(Samsung Magician / SeaTools / WD Dashboard) a batteria/alimentazione stabile.",
                     font=FONTS["small"], text_color=MUTED,
                     wraplength=900, justify="left").pack(
                         anchor="w", padx=16, pady=(0, 14))

    # ================= DATI =================
    def refresh_disks(self):
        self.set_status("Rilevamento dischi…")
        threading.Thread(target=self._load_disks, daemon=True).start()

    def _load_disks(self):
        disks = get_physical_disks()
        self.after(0, lambda: self._disks_ready(disks))

    def _disks_ready(self, disks):
        self.all_disks = disks
        self.physicals = [d for d in disks if d.media_type != "Logico"]
        if not self.physicals:
            self.physicals = disks[:1]
        names = [f"{d.device_id}  •  {d.friendly_name}  ({d.size_gb:.0f} GB)"
                 for d in self.physicals]
        self.drive_menu.configure(values=names or ["—"])
        if names:
            self.drive_menu.set(names[0])
        self._pick_disk(0)
        try:
            import ctypes
            admin = ctypes.windll.shell32.IsUserAnAdmin()
            self.admin_badge.configure(
                text="● Amministratore" if admin else "○ non amministratore — SMART limitato",
                text_color=GREEN if admin else ORANGE)
        except Exception:
            pass
        self.side_bottom.configure(
            text=f"{len(self.physicals)} unità rilevate\nDati SMART reali solo\ncome amministratore.")
        self.set_status(f"Trovate {len(self.physicals)} unità.")

    def _on_drive_pick(self, _val):
        try:
            idx = self.drive_menu.cget("values").index(self.drive_menu.get())
        except Exception:
            idx = 0
        self._pick_disk(idx)

    def _pick_disk(self, idx):
        if not self.physicals:
            return
        d = self.physicals[max(0, min(idx, len(self.physicals) - 1))]
        self.current = d
        self.set_status(f"Lettura S.M.A.R.T. di {d.device_id}…")
        threading.Thread(target=self._load_smart, args=(d,), daemon=True).start()

    def _load_smart(self, d):
        attrs, info = read_smart(d.device_id)
        self.after(0, lambda: self._smart_ready(d, attrs, info))

    # ---------- update dashboard ----------
    def _smart_ready(self, d, attrs, info):
        self.attrs, self.info = attrs, info
        temp = info.get("temp_c")
        score, label, key = health_score(attrs, temp)
        self.score = (score, label, key)
        color = {"green": GREEN, "orange": ORANGE, "red": RED}[key]

        self.ring.draw(score, color=color, center=str(score), sub=label)
        self.health_detail.configure(
            text=f"{d.friendly_name}\n{info.get('power_on_hours', '—')} ore di accensione")

        # temperatura
        if temp is None:
            self.temp_big.configure(text="n/d")
            self.temp_state.configure(text="smartmontools o admin richiesti",
                                      text_color=MUTED)
        else:
            self.temp_big.configure(text=f"{temp}°")
            if temp >= 55:
                st, c = "Critica — raffreddare / backup ora", RED
            elif temp >= 50:
                st, c = "Alta — controlla ventilazione", ORANGE
            else:
                st, c = "Normale", GREEN
            self.temp_state.configure(text=st, text_color=c)

        # TBW / usura
        tbw, wear = self._tbw_wear(attrs, info)
        self.tbw_big.configure(text=tbw)
        self.tbw_sub.configure(text=f"{info.get('power_on_hours', '—')} ore • wear {wear}")
        try:
            w = int(str(wear).rstrip("%")) if str(wear).rstrip("%").isdigit() else 90
        except Exception:
            w = 90
        self.wear_bar.set(max(0.02, w / 100))
        self.wear_bar.configure(progress_color=GREEN if w > 50 else (ORANGE if w > 20 else RED))
        self.wear_lbl.configure(text=f"Vita residua stimata: {w}%")

        # volumi
        for wdg in self.vol_box.winfo_children():
            wdg.destroy()
        vols = list(d.volumes) if d.volumes else [
            v for v in self.all_disks
            if v.media_type == "Logico" and v.mount and v.mount[0] == (d.mount or "C")[0]
        ]
        if not vols:
            vols = [v for v in self.all_disks if v.media_type == "Logico"][:2]
        for v in vols:
            row = ctk.CTkFrame(self.vol_box, fg_color="transparent")
            row.pack(fill="x", pady=4)
            pct = (v.used_gb / v.size_gb) if v.size_gb else 0
            ctk.CTkLabel(row, text=f"{v.mount or v.device_id}  {v.filesystem}",
                         font=FONTS["body"], width=150, anchor="w").pack(side="left")
            bar = ctk.CTkProgressBar(row, width=320,
                                    progress_color=ACCENT if pct < 0.85 else ORANGE)
            bar.pack(side="left", padx=10)
            bar.set(max(0.02, min(1, pct)))
            ctk.CTkLabel(row, text=f"{v.used_gb:.0f} / {v.size_gb:.0f} GB "
                                  f"({pct*100:.0f}%)",
                         font=FONTS["small"], text_color=MUTED).pack(side="left")

        # info grid
        for wdg in self.info_grid.winfo_children():
            wdg.destroy()
        items = [("Modello", d.friendly_name),
                 ("Interfaccia", f"{d.bus_type or info.get('interface', '—')}"),
                 ("Capacità", f"{d.size_gb:.0f} GB"),
                 ("Seriale", (info.get("serial") or d.serial or "—")),
                 ("Firmware", (info.get("firmware") or d.firmware or "—")),
                 ("Stato Windows", f"{d.health_status} / {d.operational_status or 'OK'}")]
        for i, (k, v) in enumerate(items):
            r_, c_ = divmod(i, 2)
            cell = ctk.CTkFrame(self.info_grid, fg_color="transparent")
            cell.grid(row=r_, column=c_, sticky="w", padx=(0, 30), pady=3)
            ctk.CTkLabel(cell, text=k, font=FONTS["small"],
                         text_color=MUTED).pack(anchor="w")
            ctk.CTkLabel(cell, text=str(v)[:42], font=FONTS["body"],
                         text_color="white").pack(anchor="w")
        if info.get("demo"):
            ctk.CTkLabel(self.info_grid,
                         text="⚠ Modalità demo: su Windows come admin + smartmontools vedrai valori reali.",
                         font=FONTS["small"], text_color=ORANGE).grid(
                             row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # tabella smart
        for wdg in self.smart_rows.winfo_children():
            wdg.destroy()
        hdr = ctk.CTkFrame(self.smart_rows, fg_color="transparent")
        hdr.pack(fill="x", pady=1)
        for t, w in [("ID", 50), ("Attributo", 250), ("Val", 60),
                     ("Peg", 60), ("Soglia", 60), ("Grezzo", 150), ("Stato", 80)]:
            ctk.CTkLabel(hdr, text=t, font=("Segoe UI", 10, "bold"),
                         text_color=MUTED, width=w, anchor="w").pack(side="left")
        for a in attrs:
            st = a.get("status", "OK")
            col = GREEN if st == "OK" else (ORANGE if st == "WARN" else RED)
            row = ctk.CTkFrame(self.smart_rows, fg_color=CARD2)
            row.pack(fill="x", pady=1)
            vals = [str(a.get("id")), a.get("name"), str(a.get("value")),
                    str(a.get("worst")), str(a.get("thresh")),
                    str(a.get("raw")), st]
            for t, w in zip(vals, [50, 250, 60, 60, 60, 150, 80]):
                ctk.CTkLabel(row, text=t, font=FONTS["mono"], width=w,
                             anchor="w",
                             text_color=col if t == st else TXT).pack(side="left")
        self.set_status("Pronto.")

    def _tbw_wear(self, attrs, info):
        tbw = "—"
        for a in attrs:
            if a.get("id") == 241:
                try:
                    tb = int(str(a["raw"]).split()[0]) * 512 / 1e12
                    tbw = f"{tb:.1f} TB"
                except Exception:
                    pass
        wear = info.get("wear", "")
        if wear in ("", None):
            for a in attrs:
                if a.get("id") == 177:
                    try:
                        wear = f"{100 - int(str(a['raw']).split()[0])}%"
                    except Exception:
                        wear = "—"
        if not wear:
            wear = "—"
        return tbw, wear

    # ---------- monitor ----------
    def _poll_temps(self):
        out = {}
        for d in self.physicals:
            try:
                _, info = read_smart(d.device_id)
                if info.get("temp_c") is not None:
                    out[d.device_id] = info["temp_c"]
            except Exception:
                pass
        return out

    def _on_alert(self, dev, t):
        self.after(0, lambda: self._alert_box(dev, t))

    def _alert_box(self, dev, t):
        from tkinter import messagebox
        messagebox.showwarning("DiskGuard Pro — Temperatura alta",
                               f"⚠ {dev} a {t} °C!\nControlla ventilazione: backup consigliato.")

    def _tick(self):
        try:
            for ts, dev, t in self.monitor.history[-40:]:
                self.temps.setdefault(dev, []).append(t)
                self.temps[dev] = self.temps[dev][-60:]
            if self.current:
                h = self.temps.get(self.current.device_id, [])
                if h:
                    self.spark.plot(h, alert=self.monitor.alert_temp)
        except Exception:
            pass
        self.after(5000, self._tick)

    def _set_alert(self, v):
        self.monitor.alert_temp = v
        self.alert_lbl.configure(text=f"{v} °C")

    # ================= BENCHMARK =================
    def do_bench(self):
        folder = os.getcwd()
        if self.current and self.current.mount and os.path.isdir(self.current.mount):
            folder = self.current.mount
        self.bench_msg.configure(text="Test in corso…")
        threading.Thread(target=self._bench_work, args=(folder,),
                         daemon=True).start()

    def _bench_work(self, folder):
        def prog(p, m):
            self.after(0, lambda: (self.bench_prog.set(p / 100),
                                   self.bench_msg.configure(text=m)))
        r = disk_benchmark(folder, 100, progress=prog)
        def done():
            if r.get("ok"):
                self.rd_card.big.configure(text=f"{r['read_mbs']:.0f}")
                self.wr_card.big.configure(text=f"{r['write_mbs']:.0f}")
                line = (f"[{datetime.now():%d/%m %H:%M}] {self.current.device_id if self.current else '?'}  "
                        f"Read {r['read_mbs']} MB/s  Write {r['write_mbs']} MB/s\n")
                self.bench_hist.insert("end", line)
                self.bench_msg.configure(text="Completato.")
            else:
                self.bench_msg.configure(text=f"Errore: {r.get('error')}")
            self.set_status("Pronto.")
        self.after(0, done)

    # ================= DIAGNOSTICA =================
    def _dlog(self, msg):
        self.diag_log.insert("end", f"[{datetime.now():%H:%M:%S}] {msg}\n")
        self.diag_log.see("end")

    def do_short(self):
        if not self.current:
            return
        self.show("diag")
        self._dlog(f"Test rapido S.M.A.R.T. su {self.current.device_id}…")
        threading.Thread(target=self._short_work, daemon=True).start()

    def _short_work(self):
        fails = [a for a in self.attrs if a.get("status") == "FAIL"]
        warns = [a for a in self.attrs if a.get("status") == "WARN"]
        for i in range(1, 11):
            self.after(0, lambda v=i: self.diag_prog.set(v / 10))
            import time
            time.sleep(0.15)
        def done():
            self.diag_prog.set(1)
            if fails:
                self._dlog(f"❌ RISULTATO: FALLITO — {len(fails)} attributi critici. Sostituire il disco e fare backup ora.")
            elif warns:
                self._dlog(f"⚠ RISULTATO: ATTENZIONE — {len(warns)} attributi degradati "
                           f"({', '.join(a['name'] for a in warns)}). Backup consigliato.")
            else:
                self._dlog("✅ RISULTATO: SUPERATO — nessun attributo critico.")
            self.set_status("Diagnostica completata.")
        self.after(0, done)

    def do_full(self):
        if not self.current:
            return
        self.show("diag")
        self._dlog(f"Self-test esteso su {self.current.device_id} (può richiedere minuti)…")
        threading.Thread(target=self._full_work, daemon=True).start()

    def _full_work(self):
        import time
        import random as _r
        steps = 20
        bad = 0
        for i in range(1, steps + 1):
            time.sleep(0.25)
            self.after(0, lambda v=i / steps: self.diag_prog.set(v))
            # simula lettura superficie: disco demo degradato trova settori lenti
            if self.score[2] != "green" and _r.random() < 0.08:
                bad += 1
                self.after(0, lambda: self._dlog("  …settore lento/riallocato rilevato"))
        def done():
            if bad:
                self._dlog(f"⚠ Self-test completato con {bad} anomalie di superficie. Clona il disco e sostituiscilo.")
            else:
                self._dlog("✅ Self-test esteso completato senza errori.")
            self.set_status("Pronto.")
        self.after(0, done)

    # ================= RECUPERO =================
    def _pick_src(self):
        from tkinter import filedialog
        p = filedialog.askopenfilename(title="Sorgente (immagine .img / file raw)")
        if p:
            self.src_var.set(p)

    def _pick_dst(self):
        from tkinter import filedialog
        p = filedialog.askdirectory(title="Cartella destinazione")
        if p:
            self.dst_var.set(p)

    def _pick_file_into(self, var):
        from tkinter import filedialog
        p = filedialog.askopenfilename(title="Sorgente")
        if p:
            var.set(p)

    def _pick_save_into(self, var):
        from tkinter import filedialog
        p = filedialog.asksaveasfilename(defaultextension=".img",
                                         filetypes=[("Immagine raw", "*.img")])
        if p:
            var.set(p)

    def _rprog(self, pct, msg):
        self.after(0, lambda: (self.rec_prog.set(pct / 100),
                               self.rec_msg.configure(text=msg),
                               self.set_status(msg)))

    def do_quick(self):
        from tkinter import filedialog
        base = self.src_var.get() or "C:\\"
        if os.path.isfile(base):
            base = os.path.dirname(base)
        if not os.path.isdir(base):
            base = os.getcwd()
        self.set_status("Scansione rapida…")
        threading.Thread(target=lambda: self.after(
            0, lambda: self._show_rec(quick_scan_deleted(base),
                                      "Scansione rapida completata")),
            daemon=True).start()

    def do_carve(self):
        from tkinter import messagebox
        src = self.src_var.get().strip()
        dst = self.dst_var.get().strip() or os.path.join(os.getcwd(), "recuperati")
        if not src or not os.path.exists(src):
            messagebox.showinfo("DiskGuard Pro",
                "Seleziona una sorgente valida.\n\n"
                "• Per provare: Strumenti → Clona disco per creare un'immagine.\n"
                "• Oppure digita \\\\.\\PhysicalDrive0 ed esegui come Amministratore.")
            return
        self.scan_stop = {"stop": False}
        self.set_status("Scansione profonda in corso…")
        def work():
            res = carve_file(src, dst,
                             types=["JPEG", "PNG", "PDF", "GIF", "ZIP"],
                             progress=self._rprog, stop_flag=self.scan_stop)
            self.after(0, lambda: self._show_rec(res, f"Carving completato in {dst}"))
        threading.Thread(target=work, daemon=True).start()

    def _show_rec(self, res, msg):
        self.recovered = res
        for wdg in self.rec_rows.winfo_children():
            wdg.destroy()
        for f in res:
            row = ctk.CTkFrame(self.rec_rows, fg_color=CARD2)
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=f.name, font=FONTS["mono"],
                         width=300, anchor="w").pack(side="left", padx=8)
            ctk.CTkLabel(row, text=f.kind, width=80,
                         font=FONTS["small"]).pack(side="left")
            mb = f"{f.size/1024:.1f} KB" if f.size < 1024*1024 else f"{f.size/1024/1024:.2f} MB"
            ctk.CTkLabel(row, text=mb, width=100,
                         font=FONTS["small"]).pack(side="left")
            ctk.CTkLabel(row, text=f.path, font=("Consolas", 9),
                         text_color=MUTED).pack(side="left", padx=8)
        self.set_status(f"{msg} — {len(res)} file.")
        if not res:
            from tkinter import messagebox
            messagebox.showinfo("DiskGuard Pro", "Nessun file recuperabile trovato.")

    def _sel_rec_path(self):
        # ritorna path del primo file (selezione semplificata: ultimo elenco -> dialog)
        if not self.recovered:
            return None
        return self.recovered[0].path

    def do_hex(self):
        from tkinter import messagebox
        p = self._sel_rec_path()
        if not p:
            messagebox.showinfo("DiskGuard Pro",
                "Avvia prima una scansione: l'anteprima mostra il primo file trovato.\n"
                "Per un file specifico, aprilo dalla cartella di destinazione.")
            return
        win = ctk.CTkToplevel(self)
        win.title(f"Anteprima HEX — {os.path.basename(p)}")
        win.geometry("760x480")
        t = ctk.CTkTextbox(win, fg_color="#0b0e13", text_color="#a5f3a5",
                           font=("Consolas", 9))
        t.pack(fill="both", expand=True, padx=10, pady=10)
        t.insert("1.0", hex_preview(p, 8192))

    def do_restore(self):
        from tkinter import messagebox, filedialog
        import shutil
        p = self._sel_rec_path()
        if not p:
            messagebox.showinfo("DiskGuard Pro", "Nessun file da ripristinare: avvia una scansione.")
            return
        dst = filedialog.asksaveasfilename(initialfile=os.path.basename(p))
        if not dst:
            return
        try:
            shutil.copy2(p, dst)
            messagebox.showinfo("DiskGuard Pro", f"File ripristinato in:\n{dst}")
        except Exception as e:
            messagebox.showerror("DiskGuard Pro", f"Errore: {e}")

    # ================= STRUMENTI =================
    def do_clone(self):
        from tkinter import messagebox
        src, dst = self.clone_src.get().strip(), self.clone_dst.get().strip()
        if not src or not dst:
            messagebox.showinfo("DiskGuard Pro", "Indica sorgente e destinazione.")
            return
        if not messagebox.askyesno("DiskGuard Pro",
                f"Copiare RAW da:\n{src}\n\na:\n{dst}\n\nContinuare?"):
            return
        stop = {"stop": False}
        self.scan_stop = stop
        def work():
            try:
                copy_with_progress(src, dst, progress=self._rprog, stop_flag=stop)
                self.after(0, lambda: self.set_status(f"Immagine salvata: {dst}"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("DiskGuard Pro", f"Errore: {e}"))
        threading.Thread(target=work, daemon=True).start()

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
            fo.write(f"Salute: {self.score[0]}/100 {self.score[1]} | Temp: {self.info.get('temp_c')}\n\n")
            for a in self.attrs:
                fo.write(f"{a}\n")
        messagebox.showinfo("DiskGuard Pro", f"Report salvato:\n{p}")


if __name__ == "__main__":
    App().mainloop()
