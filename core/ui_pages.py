"""DiskGuard Pro - pagine UI secondarie (mixin App). Importato da app.py."""
import os
import threading
import tkinter as tk
from datetime import datetime

import customtkinter as ctk

from core.disks import get_physical_disks
from core.smart import read_smart, health_score
from core.recovery import (quick_scan_deleted, carve_file, hex_preview,
                           copy_with_progress, validate_file, file_hashes,
                           image_preview, findings_report)
from core.monitor import disk_benchmark
from core.analysis import (get_layout, surface_scan, disk_usage,
                           io_latency_test, get_shadow_copies)
from core.ai import predict, scan_unknown, rank_files, temp_anomaly


class AppPagesMixin:
    # ================= ANALISI DISCO =================
    def _build_analysis(self, f):
        wrap = ctk.CTkScrollableFrame(f, fg_color=BG)
        wrap.pack(fill="both", expand=True, padx=20, pady=10)
        ctk.CTkLabel(wrap, text="Analisi Disco",
                     font=FONTS["title"], text_color="white").pack(anchor="w")
        ctk.CTkLabel(wrap, text="Layout partizioni (GPT/MBR) · mappa superficie · uso disco · latenza I/O · copie shadow.",
                     font=FONTS["small"], text_color=MUTED).pack(anchor="w", pady=(0, 10))

        lay = self._card(wrap)
        lay.pack(fill="x", pady=(0, 10))
        hdr = ctk.CTkFrame(lay, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(hdr, text="Layout partizioni", font=FONTS["h"],
                     text_color="white").pack(side="left")
        ctk.CTkButton(hdr, text="⟳ Ricarica layout", width=130, fg_color=CARD2,
                      command=self.do_layout).pack(side="right")
        self.layout_box = ctk.CTkScrollableFrame(lay, fg_color="transparent", height=150)
        self.layout_box.pack(fill="x", padx=10, pady=(0, 12))

        surf = self._card(wrap)
        surf.pack(fill="x", pady=(0, 10))
        hdr2 = ctk.CTkFrame(surf, fg_color="transparent")
        hdr2.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(hdr2, text="Mappa superficie (lettura a blocchi)", font=FONTS["h"],
                     text_color="white").pack(side="left")
        ctk.CTkLabel(hdr2, text="■ ok  ■ lento  ■ illeggibile", font=FONTS["small"],
                     text_color=MUTED).pack(side="right", padx=10)
        sbar = ctk.CTkFrame(surf, fg_color="transparent")
        sbar.pack(fill="x", padx=16, pady=(0, 6))
        ctk.CTkButton(sbar, text="🗺 Avvia surface scan", fg_color=ACCENT,
                      hover_color="#1f5fd6", command=self.do_surface).pack(side="left")
        ctk.CTkButton(sbar, text="⏹", width=44, fg_color="#7f1d1d",
                      command=lambda: self.scan_stop.update(stop=True)).pack(side="left", padx=8)
        self.surf_prog = ctk.CTkProgressBar(sbar, width=260)
        self.surf_prog.pack(side="left", padx=8)
        self.surf_prog.set(0)
        self.surf_msg = ctk.CTkLabel(sbar, text="Usa la stessa sorgente del Recupero.",
                                    font=FONTS["small"], text_color=MUTED)
        self.surf_msg.pack(side="left")
        self.surf_map = tk.Canvas(surf, height=110, bg=CARD, highlightthickness=0)
        self.surf_map.pack(fill="x", padx=16, pady=(0, 14))

        cols = ctk.CTkFrame(wrap, fg_color=BG)
        cols.pack(fill="x", pady=(0, 10))
        uc = self._card(cols)
        uc.pack(side="left", fill="both", expand=True, padx=(0, 5))
        uh = ctk.CTkFrame(uc, fg_color="transparent")
        uh.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(uh, text="Uso disco", font=FONTS["h"],
                     text_color="white").pack(side="left")
        ctk.CTkButton(uh, text="Analizza volume", width=130, fg_color=CARD2,
                      command=self.do_usage).pack(side="right")
        self.usage_box = ctk.CTkTextbox(uc, height=170, fg_color=CARD2,
                                       text_color=TXT, font=FONTS["mono"])
        self.usage_box.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        ioc = self._card(cols)
        ioc.pack(side="left", fill="both", expand=True, padx=(5, 0))
        ih = ctk.CTkFrame(ioc, fg_color="transparent")
        ih.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(ih, text="Latenza I/O 4K + Shadow", font=FONTS["h"],
                     text_color="white").pack(side="left")
        ctk.CTkButton(ih, text="Test I/O", width=100, fg_color=CARD2,
                      command=self.do_iotest).pack(side="right")
        self.io_box = ctk.CTkTextbox(ioc, height=170, fg_color=CARD2,
                                    text_color=TXT, font=FONTS["mono"])
        self.io_box.pack(fill="both", expand=True, padx=16, pady=(0, 14))

    # ================= AI PREDITTIVA =================
    def _build_ai(self, f):
        wrap = ctk.CTkScrollableFrame(f, fg_color=BG)
        wrap.pack(fill="both", expand=True, padx=20, pady=10)
        ctk.CTkLabel(wrap, text="AI Predittiva — offline",
                     font=FONTS["title"], text_color="white").pack(anchor="w")
        ctk.CTkLabel(wrap, text="Predizione guasto (logistica su feature SMART stile Backblaze) · anomaly detection temperatura · classifica frammenti sconosciuti · ranking file recuperati. Nessun cloud, nessuna API key.",
                     font=FONTS["small"], text_color=MUTED, wraplength=1000,
                     justify="left").pack(anchor="w", pady=(0, 10))

        # riga 1: rischio + gauge
        row = ctk.CTkFrame(wrap, fg_color=BG)
        row.pack(fill="x", pady=(0, 10))
        rc = self._card(row)
        rc.pack(side="left", fill="both", expand=True, padx=(0, 5))
        ctk.CTkLabel(rc, text="Rischio guasto stimato", font=FONTS["small"],
                     text_color=MUTED).pack(anchor="w", padx=16, pady=(14, 0))
        self.ai_gauge = Ring(rc, size=150)
        self.ai_gauge.pack(pady=6)
        self.ai_risk = ctk.CTkLabel(rc, text="—", font=FONTS["h"], text_color="white")
        self.ai_risk.pack()
        self.ai_action = ctk.CTkLabel(rc, text="", font=FONTS["small"],
                                     text_color=MUTED, wraplength=320, justify="center")
        self.ai_action.pack(padx=16, pady=(4, 12))
        ctk.CTkButton(rc, text="🔄 Ricalcola AI", fg_color=ACCENT,
                      hover_color="#1f5fd6", command=self.do_ai_refresh).pack(pady=(0, 14))

        fc = self._card(row)
        fc.pack(side="left", fill="both", expand=True, padx=(5, 0))
        ctk.CTkLabel(fc, text="Fattori di rischio (peso × livello)", font=FONTS["h"],
                     text_color="white").pack(anchor="w", padx=16, pady=(14, 4))
        self.ai_factors = ctk.CTkScrollableFrame(fc, fg_color="transparent", height=200)
        self.ai_factors.pack(fill="both", expand=True, padx=10, pady=(0, 12))

        # riga 2: anomaly + classifier
        row2 = ctk.CTkFrame(wrap, fg_color=BG)
        row2.pack(fill="x")
        an = self._card(row2)
        an.pack(side="left", fill="both", expand=True, padx=(0, 5))
        ah = ctk.CTkFrame(an, fg_color="transparent")
        ah.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(ah, text="Anomaly detection temperatura", font=FONTS["h"],
                     text_color="white").pack(side="left")
        ctk.CTkButton(ah, text="Analizza", width=100, fg_color=CARD2,
                      command=self.do_ai_anomaly).pack(side="right")
        self.ai_anom = ctk.CTkTextbox(an, height=110, fg_color=CARD2,
                                      text_color=TXT, font=FONTS["mono"])
        self.ai_anom.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        cl = self._card(row2)
        cl.pack(side="left", fill="both", expand=True, padx=(5, 0))
        ch = ctk.CTkFrame(cl, fg_color="transparent")
        ch.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(ch, text="Classifica frammenti (deep scan AI)", font=FONTS["h"],
                     text_color="white").pack(side="left")
        ctk.CTkButton(ch, text="Scansiona", width=100, fg_color=CARD2,
                      command=self.do_ai_fragments).pack(side="right")
        self.ai_prog = ctk.CTkProgressBar(cl, width=200)
        self.ai_prog.pack(fill="x", padx=16, pady=(0, 4))
        self.ai_prog.set(0)
        self.ai_frags = ctk.CTkTextbox(cl, height=110, fg_color=CARD2,
                                       text_color=TXT, font=FONTS["mono"])
        self.ai_frags.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        # riga 3: ranking + retrain
        row3 = ctk.CTkFrame(wrap, fg_color=BG)
        row3.pack(fill="x", pady=(10, 0))
        rk = self._card(row3)
        rk.pack(side="left", fill="both", expand=True, padx=(0, 5))
        rh = ctk.CTkFrame(rk, fg_color="transparent")
        rh.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(rh, text="Ranking AI file recuperati", font=FONTS["h"],
                     text_color="white").pack(side="left")
        ctk.CTkButton(rh, text="Rank", width=90, fg_color=CARD2,
                      command=self.do_ai_rank).pack(side="right")
        self.ai_rank = ctk.CTkTextbox(rk, height=120, fg_color=CARD2,
                                      text_color=TXT, font=FONTS["mono"])
        self.ai_rank.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        rt = self._card(row3)
        rt.pack(side="left", fill="both", expand=True, padx=(5, 0))
        ctk.CTkLabel(rt, text="Ri-allena modello (CSV Backblaze)", font=FONTS["h"],
                     text_color="white").pack(anchor="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(rt, text="Colonne: smart_5/197/198/194/9_raw + failure (1=guasto).",
                     font=FONTS["small"], text_color=MUTED).pack(anchor="w", padx=16)
        self.train_var = tk.StringVar()
        ctk.CTkEntry(rt, textvariable=self.train_var, fg_color=CARD2,
                     border_width=0, placeholder_text="percorso CSV…").pack(
                         fill="x", padx=16, pady=8)
        brow = ctk.CTkFrame(rt, fg_color="transparent")
        brow.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkButton(brow, text="Sfoglia…", width=90, fg_color="#2a3040",
                      command=self._pick_train).pack(side="left")
        ctk.CTkButton(brow, text="🧠 Allena", fg_color=ACCENT,
                      hover_color="#1f5fd6", command=self.do_train).pack(side="left", padx=8)
        self.train_msg = ctk.CTkLabel(rt, text="", font=FONTS["small"], text_color=MUTED)
        self.train_msg.pack(anchor="w", padx=16, pady=(0, 10))

    # ================= RECUPERO =================
    def _build_rec(self, f):
        wrap = ctk.CTkFrame(f, fg_color=BG)
        wrap.pack(fill="both", expand=True, padx=20, pady=10)
        top = ctk.CTkFrame(wrap, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(top, text="Recupero Dati",
                     font=FONTS["title"], text_color="white").pack(side="left")
        self.rec_count = ctk.CTkLabel(top, text="", font=FONTS["small"],
                                     text_color=MUTED)
        self.rec_count.pack(side="right")
        ctk.CTkLabel(wrap, text="19 firme: JPEG PNG PDF GIF BMP TIFF WEBP · ZIP DOCX XLSX · MP4 MP3 WAV AVI MKV · SQLITE EXE RAR 7Z. Anteprima immagini, validazione, hash, report CSV/HTML.",
                     font=FONTS["small"], text_color=MUTED, wraplength=1000,
                     justify="left").pack(anchor="w", pady=(0, 10))
        form = self._card(wrap)
        form.pack(fill="x", pady=(0, 10))
        self.src_var = tk.StringVar()
        self.dst_var = tk.StringVar(value=os.path.join(os.getcwd(), "recuperati"))
        self._form_row(form, "Sorgente (immagine .img o \\\\.\\PhysicalDrive0):",
                       self.src_var, self._pick_src)
        self._form_row(form, "Destinazione file recuperati:",
                       self.dst_var, self._pick_dst, is_dir=True)
        # tipi file con checkbox
        trow = ctk.CTkFrame(form, fg_color="transparent")
        trow.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkLabel(trow, text="Tipi:", font=FONTS["small"],
                     text_color=MUTED).pack(side="left")
        self.type_vars = {}
        for t in ["JPEG", "PNG", "PDF", "GIF", "BMP", "ZIP", "DOCX",
                  "XLSX", "MP4", "MP3", "MKV", "SQLITE", "EXE", "RAR", "7Z"]:
            v = tk.BooleanVar(value=t in ("JPEG", "PNG", "PDF", "GIF", "ZIP"))
            self.type_vars[t] = v
            ctk.CTkCheckBox(trow, text=t, variable=v, width=70,
                            font=("Segoe UI", 10)).pack(side="left", padx=3)

        bar = ctk.CTkFrame(wrap, fg_color=BG)
        bar.pack(fill="x", pady=(0, 8))
        ctk.CTkButton(bar, text="⚡ Rapida", fg_color="#0a7a4b",
                      hover_color="#086038", command=self.do_quick).pack(side="left")
        ctk.CTkButton(bar, text="🧲 Profonda", fg_color=ACCENT,
                      hover_color="#1f5fd6", font=("Segoe UI", 11, "bold"),
                      command=self.do_carve).pack(side="left", padx=8)
        ctk.CTkButton(bar, text="⏹", width=44, fg_color="#7f1d1d",
                      command=lambda: self.scan_stop.update(stop=True)).pack(side="left")
        ctk.CTkButton(bar, text="Filtra: solo validi", width=120, fg_color=CARD2,
                      command=self.do_filter_valid).pack(side="left", padx=8)
        ctk.CTkButton(bar, text="📄 Report", width=90, fg_color=CARD2,
                      command=self.do_report).pack(side="left")
        self.rec_filter = tk.StringVar()
        ctk.CTkEntry(bar, textvariable=self.rec_filter, placeholder_text="🔍 cerca…",
                     fg_color=CARD2, border_width=0, width=150).pack(side="left", padx=8)
        ctk.CTkButton(bar, text="Cerca", width=60, fg_color=CARD2,
                      command=self.do_search).pack(side="left")
        self.rec_prog = ctk.CTkProgressBar(wrap, width=400)
        self.rec_prog.pack(fill="x", pady=(0, 2))
        self.rec_prog.set(0)
        self.rec_msg = ctk.CTkLabel(wrap, text="", font=FONTS["small"],
                                   text_color=MUTED, anchor="w")
        self.rec_msg.pack(fill="x")

        res = self._card(wrap)
        res.pack(fill="both", expand=True)
        ctk.CTkLabel(res, text="File trovati (doppio clic = anteprima)", font=FONTS["h"],
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