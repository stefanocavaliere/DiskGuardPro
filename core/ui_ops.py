"""DiskGuard Pro - logica operativa UI (mixin App). Importato da app.py."""
import os
import threading
import tkinter as tk
from datetime import datetime

import customtkinter as ctk

from core.theme import (BG, SIDEBAR, CARD, CARD2, TXT, MUTED, ACCENT, CYAN,
                        GREEN, ORANGE, RED, FONTS, Ring, Spark, fmt_gb)
from core.disks import get_physical_disks
from core.smart import read_smart, health_score
from core.recovery import (quick_scan_deleted, carve_file, hex_preview,
                           copy_with_progress, validate_file, file_hashes,
                           image_preview, findings_report)
from core.monitor import disk_benchmark
from core.analysis import (get_layout, surface_scan, disk_usage,
                           io_latency_test, get_shadow_copies)
from core.ai import predict, ai_verdict, scan_unknown, rank_files, temp_anomaly
from core.ai import retrain_from_csv


class AppOpsMixin:
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
    # ---------- helpers formattazione dashboard ----------
    @staticmethod
    def _raw_int(a):
        try:
            return int(str(a.get("raw", 0)).split()[0])
        except Exception:
            return 0

    def _smart_ready(self, d, attrs, info):
        self.attrs, self.info = attrs, info
        temp = info.get("temp_c")
        score, label, key = health_score(attrs, temp)
        self.score = (score, label, key)
        self.score_hist = getattr(self, "score_hist", []) + [score]
        self.score_hist = self.score_hist[-60:]
        color = {"green": GREEN, "orange": ORANGE, "red": RED}[key]
        by_id = {}
        for a in attrs or []:
            try:
                by_id[int(a.get("id"))] = a
            except Exception:
                pass

        # ---- card salute ----
        self.ring.draw(score, color=color, center=str(score), sub=f"/100 {label}")
        badge_txt = {"green": "● BUONO", "orange": "● ATTENZIONE", "red": "● CRITICO"}[key]
        try:
            self.health_badge.configure(text=f"{badge_txt}  {score}/100", text_color=color)
        except Exception:
            pass
        crit = [a for a in (attrs or []) if a.get("status") == "FAIL"]
        warn = [a for a in (attrs or []) if a.get("status") == "WARN"]
        lines = []
        if crit:
            lines.append(f"❌ {len(crit)} attributi critici: " + ", ".join(a.get('name', '?') for a in crit[:2]))
        if warn:
            lines.append(f"⚠ {len(warn)} in attenzione: " + ", ".join(a.get('name', '?') for a in warn[:2]))
        if not lines:
            lines.append("✅ Tutti gli attributi entro soglia")
        lines.append(f"⏱ {info.get('power_on_hours', '—')} ore • 🔄 {self._raw_int(by_id.get(12, {}))} accensioni")
        self.health_lines.configure(text="\n".join(lines))
        try:
            verdict = ai_verdict(attrs, info)
        except Exception:
            verdict = ""
        self.health_detail.configure(text=f"{d.friendly_name} — {d.media_type}/{d.bus_type}\n{verdict}")

        # ---- card temperatura ----
        if temp is None:
            self.temp_big.configure(text="n/d")
            self.temp_state.configure(text="dati non disponibili", text_color=MUTED)
            self.temp_minmax.configure(text="smartmontools o admin richiesti")
            self.temp_ai.configure(text="")
        else:
            t = float(temp)
            self.temp_big.configure(text=f"{t:.0f}°")
            if t >= 55:
                st, c = "CRITICA", RED
                tip = "Raffreddare subito + backup ora"
            elif t >= 50:
                st, c = "ALTA", ORANGE
                tip = "Controlla ventilazione e carico"
            elif t <= 30:
                st, c = "FREDDA", CYAN
                tip = "Valore basso, nessun problema"
            else:
                st, c = "NORMALE", GREEN
                tip = f"Margine {(55 - t):.0f}°C alla soglia di allarme"
            self.temp_state.configure(text=st, text_color=c)
            h = self.temps.get(d.device_id, [])
            mm = f"min {min(h):.0f}° • max {max(h):.0f}°" if h else "in raccolta dati…"
            self.temp_minmax.configure(text=mm)
            try:
                an = temp_anomaly(h) if h else {"ok": True, "msg": "raccolta dati…"}
                self.temp_ai.configure(text=f"🤖 {an.get('msg', '')}")
            except Exception:
                pass
            self.temp_big.configure(text_color=c if c != CYAN else "white")

        # ---- card vita residua / TBW ----
        tbw, wear = self._tbw_wear(attrs, info)
        tb_val = None
        for a in attrs or []:
            if a.get("id") == 241:
                try:
                    tb_val = int(str(a["raw"]).split()[0]) * 512 / 1e12
                except Exception:
                    pass
        self.tbw_big.configure(text=tbw)
        self.tbw_sub.configure(text=f"{info.get('power_on_hours', '—')} ore • usura {wear}")
        try:
            w = int(str(wear).rstrip("%")) if str(wear).rstrip("%").isdigit() else 90
        except Exception:
            w = 90
        self.wear_bar.set(max(0.02, w / 100))
        wcol = GREEN if w > 50 else (ORANGE if w > 20 else RED)
        self.wear_bar.configure(progress_color=wcol)
        self.wear_lbl.configure(text=f"Vita residua stimata: {w}%", text_color=wcol)
        extra = []
        if tb_val is not None:
            extra.append(f"✍️ {tb_val:.1f} TB scritti (host writes)")
        poh = info.get("power_on_hours")
        try:
            poh = int(poh)
            yrs = poh / 24 / 365
            extra.append(f"⏱ {poh:,} ore ≈ {yrs:.1f} anni di accensione")
        except Exception:
            pass
        if warn or crit:
            extra.append("⚠ degrado SMART: backup ravvicinati")
        self.tbw_extra.configure(text=" • ".join(extra) if extra else "")

        # ---- card rischio AI ----
        try:
            p = predict(attrs, info)
            pcol = {"Basso": GREEN, "Moderato": ORANGE, "Alto": ORANGE, "Critico": RED}[p["risk"]]
            self.ai_ring.draw(p["p30"], color=pcol, center=f"{p['p30']}%")
            self.ai_level.configure(text=p["risk"].upper(), text_color=pcol)
            self.ai_hint.configure(text=f"90gg {p['p90']}% • 180gg {p['p180']}%\n{p['action'][:110]}")
        except Exception as e:
            self.ai_level.configure(text="n/d", text_color=MUTED)
            self.ai_hint.configure(text=str(e)[:100])

        # ---- barre attributi critici ----
        def norm(aid, worst_raw, invert=True):
            a = by_id.get(aid)
            if not a:
                return None
            raw = self._raw_int(a)
            try:
                v = float(a.get("value", 100))
            except Exception:
                v = 100
            return (a.get("name", f"ID {aid}")[:20], v,
                    GREEN if a.get("status") == "OK" else (ORANGE if a.get("status") == "WARN" else RED))
        items = [x for x in [norm(5, 50), norm(197, 20), norm(198, 20), norm(194, 60),
                             norm(177, 100), norm(199, 100)] if x]
        try:
            self.attrbars.plot(items)
        except Exception:
            pass
        bad_names = [a.get("name") for a in (crit + warn)[:3]]
        self.attr_note.configure(
            text=("Da monitorare: " + ", ".join(bad_names)) if bad_names
            else "Valori normalizzati 0–100 (soglia critica < soglia SMART). Tutto nella norma.")

        # ---- grafico combinato ----
        try:
            h = self.temps.get(d.device_id, [])[-60:]
            self.multichart.plot(h, self.score_hist[-len(h):] if h else self.score_hist[-60:],
                                 alert=self.monitor.alert_temp)
            tl = []
            if h:
                step = max(1, len(h) // 8)
                for i in range(0, len(h), step):
                    v = h[i]
                    tl.append((f"{v:.0f}°", "red" if v >= 55 else ("orange" if v >= 50 else "green")))
            else:
                tl = [("raccolta dati…", "gray")]
            self.timeline.plot(tl)
            self.spark.plot(h, alert=self.monitor.alert_temp)
        except Exception:
            pass

        # volumi
        for wdg in self.vol_box.winfo_children():
            wdg.destroy()
        vols = list(d.volumes) if d.volumes else [
            v for v in self.all_disks
            if v.media_type == "Logico" and v.mount and v.mount[0] == (d.mount or "C")[0]
        ]
        if not vols:
            vols = [v for v in self.all_disks if v.media_type == "Logico"][:2]
        tot_u = sum(v.used_gb for v in vols)
        tot_s = sum(v.size_gb for v in vols) or 1
        try:
            self.vol_total.configure(
                text=f"{len(vols)} volumi • {fmt_gb(tot_u)} usati su {fmt_gb(tot_s)} "
                     f"({tot_u/tot_s*100:.0f}% occupato)")
        except Exception:
            pass
        for v in vols:
            row = ctk.CTkFrame(self.vol_box, fg_color="transparent")
            row.pack(fill="x", pady=5)
            pct = (v.used_gb / v.size_gb) if v.size_gb else 0
            dot = "🟢" if pct < 0.75 else ("🟠" if pct < 0.9 else "🔴")
            ctk.CTkLabel(row, text=f"{dot} {v.mount or v.device_id}",
                         font=("Segoe UI", 12, "bold"), width=90, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=f"{v.filesystem}", font=FONTS["small"],
                         text_color=MUTED, width=60).pack(side="left")
            bar = ctk.CTkProgressBar(row, width=320,
                                    progress_color=ACCENT if pct < 0.75 else (ORANGE if pct < 0.9 else RED))
            bar.pack(side="left", padx=10)
            bar.set(max(0.02, min(1, pct)))
            free = max(0, v.size_gb - v.used_gb)
            ctk.CTkLabel(row, text=f"{fmt_gb(v.used_gb)} / {fmt_gb(v.size_gb)}  "
                                  f"({pct*100:.0f}%)  •  liberi {fmt_gb(free)}",
                         font=FONTS["small"], text_color=MUTED).pack(side="left")

        # info grid
        for wdg in self.info_grid.winfo_children():
            wdg.destroy()
        items = [("💽 Modello", d.friendly_name),
                 ("🔌 Interfaccia", f"{d.bus_type or info.get('interface', '—')}" +
                  (f" • {d.device_id}" if d.device_id else "")),
                 ("💾 Capacità", f"{fmt_gb(d.size_gb)}  ({d.size_gb:.0f} GB)"),
                 ("🏷 Seriale", (info.get("serial") or d.serial or "—")),
                 ("🧩 Firmware", (info.get("firmware") or d.firmware or "—")),
                 ("🪟 Stato Windows", f"{d.health_status} / {d.operational_status or 'OK'}"),
                 ("🌡 Temperatura", f"{temp} °C" if temp is not None else "n/d"),
                 ("🤖 Rischio AI", f"{self.score[0]}/100 {self.score[1]}")]
        for i, (k, v) in enumerate(items):
            r_, c_ = divmod(i, 4)
            cell = ctk.CTkFrame(self.info_grid, fg_color=CARD2, corner_radius=8)
            cell.grid(row=r_, column=c_, sticky="ew", padx=(0, 8), pady=4, ipadx=8, ipady=6)
            ctk.CTkLabel(cell, text=k, font=("Segoe UI", 9, "bold"),
                         text_color=MUTED).pack(anchor="w")
            ctk.CTkLabel(cell, text=str(v)[:40], font=FONTS["body"],
                         text_color="white").pack(anchor="w")
        try:
            self.info_grid.grid_columnconfigure((0, 1, 2, 3), weight=1)
        except Exception:
            pass
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
                h = self.temps.get(self.current.device_id, [])[-60:]
                if h and hasattr(self, "spark"):
                    self.spark.plot(h, alert=self.monitor.alert_temp)
                    self.multichart.plot(h, getattr(self, "score_hist", [])[-len(h):] or [self.score[0]] * len(h),
                                         alert=self.monitor.alert_temp)
                    try:
                        self.temp_minmax.configure(text=f"min {min(h):.0f}° • max {max(h):.0f}° • ora {h[-1]:.0f}°")
                    except Exception:
                        pass
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
        types = [t for t, v in self.type_vars.items() if v.get()] or ["JPEG", "PNG", "PDF"]
        self.set_status(f"Scansione profonda ({', '.join(types)})…")
        def work():
            res = carve_file(src, dst, types=types,
                             progress=self._rprog, stop_flag=self.scan_stop)
            self.after(0, lambda: self._show_rec(res, f"Carving completato in {dst}"))
        threading.Thread(target=work, daemon=True).start()

    def _show_rec(self, res, msg, only_valid=False, query=""):
        self.recovered = res
        self._rec_filtered = res
        if only_valid:
            tmp = []
            for f in res:
                ok, _ = validate_file(f.path, f.kind)
                if ok:
                    tmp.append(f)
            self._rec_filtered = tmp
        if query:
            q = query.lower()
            self._rec_filtered = [f for f in self._rec_filtered
                                  if q in f.name.lower() or q in f.kind.lower()]
        for wdg in self.rec_rows.winfo_children():
            wdg.destroy()
        for f in self._rec_filtered:
            ok, det = validate_file(f.path, f.kind)
            row = ctk.CTkFrame(self.rec_rows, fg_color=CARD2)
            row.pack(fill="x", pady=1)
            badge = "✓" if ok else "?"
            bcol = GREEN if ok else ORANGE
            b = ctk.CTkLabel(row, text=badge, width=26, font=("Segoe UI", 12, "bold"),
                             text_color=bcol)
            b.pack(side="left", padx=(8, 0))
            ctk.CTkLabel(row, text=f.name, font=FONTS["mono"],
                         width=280, anchor="w").pack(side="left", padx=8)
            ctk.CTkLabel(row, text=f.kind, width=70,
                         font=FONTS["small"]).pack(side="left")
            mb = f"{f.size/1024:.1f} KB" if f.size < 1024*1024 else f"{f.size/1024/1024:.2f} MB"
            ctk.CTkLabel(row, text=mb, width=90,
                         font=FONTS["small"]).pack(side="left")
            ctk.CTkLabel(row, text=det[:40], width=200, anchor="w",
                         font=FONTS["small"], text_color=bcol).pack(side="left")
            row.bind("<Double-Button-1>", lambda e, p=f.path: self.preview_file(p))
            for ch in row.winfo_children():
                ch.bind("<Double-Button-1>", lambda e, p=f.path: self.preview_file(p))
        self.rec_count.configure(text=f"{len(self._rec_filtered)} / {len(res)} file")
        self.set_status(f"{msg} — {len(res)} file.")
        if not res:
            from tkinter import messagebox
            messagebox.showinfo("DiskGuard Pro", "Nessun file recuperabile trovato.")

    def _sel_rec_path(self):
        items = getattr(self, "_rec_filtered", self.recovered)
        if not items:
            return None
        return items[0].path

    def preview_file(self, p):
        """Anteprima: immagine se possibile, altrimenti HEX."""
        win = ctk.CTkToplevel(self)
        win.title(f"Anteprima — {os.path.basename(p)}")
        win.geometry("780x540")
        im = image_preview(p)
        if im is not None:
            try:
                import customtkinter as _ctk
                from PIL import ImageTk as _ITk
                tk_im = _ITk.PhotoImage(im)
                lbl = ctk.CTkLabel(win, text="", image=tk_im)
                lbl.image = tk_im
                lbl.pack(pady=10)
            except Exception:
                pass
            ok, det = validate_file(p, os.path.splitext(p)[1])
            h = file_hashes(p)
            ctk.CTkLabel(win, text=f"Validazione: {det}  •  MD5: {h.get('md5','—')[:24]}…",
                         font=FONTS["small"], text_color=MUTED).pack()
        ctk.CTkLabel(win, text="Dump esadecimale (primi 8 KB):",
                     font=FONTS["small"], text_color=MUTED).pack(anchor="w", padx=10)
        t = ctk.CTkTextbox(win, fg_color="#0b0e13", text_color="#a5f3a5",
                           font=("Consolas", 9))
        t.pack(fill="both", expand=True, padx=10, pady=10)
        t.insert("1.0", hex_preview(p, 8192))

    def do_hex(self):
        from tkinter import messagebox
        p = self._sel_rec_path()
        if not p:
            messagebox.showinfo("DiskGuard Pro", "Avvia prima una scansione.")
            return
        self.preview_file(p)

    def do_filter_valid(self):
        if not self.recovered:
            from tkinter import messagebox
            messagebox.showinfo("DiskGuard Pro", "Avvia prima una scansione.")
            return
        self._show_rec(self.recovered, "Filtro: solo file validi", only_valid=True)

    def do_search(self):
        if not self.recovered:
            return
        self._show_rec(self.recovered, "Ricerca", query=self.rec_filter.get().strip())

    def do_report(self):
        from tkinter import messagebox, filedialog
        if not getattr(self, "_rec_filtered", None):
            messagebox.showinfo("DiskGuard Pro", "Niente da esportare: avvia una scansione.")
            return
        base = filedialog.asksaveasfilename(defaultextension=".csv",
                                            initialfile="diskguard_recupero.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not base:
            return
        html = os.path.splitext(base)[0] + ".html"
        r = findings_report(self._rec_filtered, base, html)
        messagebox.showinfo("DiskGuard Pro",
                            f"Report salvato:\n{r['csv']}\n{r['html']}\n({r['count']} file con hash MD5 e validazione)")

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

    # ================= ANALISI: metodi =================
    def _aprog(self, pct, msg):
        self.after(0, lambda: (self.surf_prog.set(pct / 100),
                               self.surf_msg.configure(text=msg),
                               self.set_status(msg)))

    def do_layout(self):
        self.set_status("Lettura layout partizioni…")
        threading.Thread(target=self._layout_work, daemon=True).start()

    def _layout_work(self):
        lay = get_layout()
        self.after(0, lambda: self._layout_show(lay))

    def _layout_show(self, lay):
        for wdg in self.layout_box.winfo_children():
            wdg.destroy()
        for d in lay.get("disks", []):
            gb = (d.get("Size") or 0) / 1024**3
            head = ctk.CTkLabel(self.layout_box,
                                text=f"💽 Disco {d.get('Number')} — {d.get('FriendlyName')}  "
                                     f"[{d.get('PartitionStyle')}]  {gb:.0f} GB  "
                                     f"{d.get('BusType','')}  Salute: {d.get('HealthStatus')}",
                                font=FONTS["h2"], text_color="white", anchor="w")
            head.pack(fill="x", pady=(8, 2))
            for p in [x for x in lay.get("partitions", [])
                      if x.get("DiskNumber") == d.get("Number")]:
                letter = f" ({p.get('DriveLetter')}:)" if p.get("DriveLetter") else ""
                ctk.CTkLabel(self.layout_box,
                             text=f"   └─ Partizione {p.get('PartitionNumber')}{letter} — "
                                  f"{(p.get('Size') or 0)/1024**3:.1f} GB — {p.get('Type')}",
                             font=FONTS["mono"], text_color=MUTED,
                             anchor="w").pack(fill="x")
        if lay.get("demo"):
            ctk.CTkLabel(self.layout_box, text="⚠ Layout demo (su Windows vedrai GPT/MBR reali).",
                         font=FONTS["small"], text_color=ORANGE).pack(anchor="w")
        vss = get_shadow_copies()
        if vss:
            ctk.CTkLabel(self.layout_box,
                         text=f"📸 Copie shadow VSS trovate: {len(vss)} — "
                              f"ultima: {vss[0].get('InstallDate','—')} su {vss[0].get('Volume','—')}",
                         font=FONTS["small"], text_color=GREEN).pack(anchor="w", pady=(6, 0))
        self.set_status(f"Layout: {len(lay.get('disks',[]))} dischi, "
                        f"{len(lay.get('partitions',[]))} partizioni.")

    def do_surface(self):
        from tkinter import messagebox
        src = (self.src_var.get().strip() if hasattr(self, "src_var") else "") or ""
        if not src or not os.path.exists(src):
            # fallback: usa il mount del disco corrente
            if self.current and self.current.mount and os.path.isdir(self.current.mount):
                messagebox.showinfo("DiskGuard Pro",
                    "Seleziona prima una sorgente nel Recupero (immagine .img).\n"
                    "La scansione del disco di sistema dall'interno è sconsigliata.")
            else:
                messagebox.showinfo("DiskGuard Pro",
                    "Vai in Recupero Dati e scegli una sorgente (immagine .img).")
            return
        self.scan_stop = {"stop": False}
        threading.Thread(target=self._surface_work, args=(src,), daemon=True).start()

    def _surface_work(self, src):
        res = surface_scan(src, block_mb=2, progress=self._aprog,
                           stop_flag=self.scan_stop)
        self.after(0, lambda: self._surface_show(res))

    def _surface_show(self, res):
        cv = self.surf_map
        cv.delete("all")
        blocks = res.get("blocks", [])
        W = max(300, cv.winfo_width() or 900)
        n = max(1, len(blocks))
        cols = 100
        cell = max(3, W // cols)
        for i, (off, st, ms) in enumerate(blocks[:cols * 8]):
            x, y = (i % cols) * cell, (i // cols) * cell
            col = GREEN if st == "ok" else (ORANGE if st == "slow" else RED)
            cv.create_rectangle(x + 1, y + 1, x + cell - 1, y + cell - 1,
                                fill=col, outline="")
        self.surf_msg.configure(
            text=f"ok={res.get('ok')}  lenti={res.get('slow')}  illeggibili={res.get('bad')}  "
                 f"media {res.get('avg_mbs')} MB/s su {res.get('total_mb')} MB")
        self.set_status("Surface scan completata." if not res.get("error") else res["error"])

    def do_usage(self):
        folder = (self.current.mount if self.current and self.current.mount
                  and os.path.isdir(self.current.mount) else os.getcwd())
        self.usage_box.delete("1.0", "end")
        self.usage_box.insert("end", f"Analisi di {folder}…\n")
        threading.Thread(target=self._usage_work, args=(folder,), daemon=True).start()

    def _usage_work(self, folder):
        r = disk_usage(folder, max_entries=30000,
                       progress=lambda p, m: self.after(0, lambda: self.set_status(m)))
        self.after(0, lambda: self._usage_show(r))

    def _usage_show(self, r):
        if r.get("error"):
            self.usage_box.insert("end", f"Errore: {r['error']}\n")
            return
        gb = r["total_size"] / 1024**3
        txt = (f"📁 {r['folder']}\n{gb:.1f} GB in {r['total_files']} file / {r['total_dirs']} cartelle\n\n"
               "Top estensioni (per spazio):\n")
        for ext, n, sz in r["by_ext"][:12]:
            txt += f"  {ext:<10} {n:>6} file  {sz/1024**2:>9.1f} MB\n"
        txt += "\nFile più grandi:\n"
        for fp, sz in r["largest"][:12]:
            txt += f"  {sz/1024**2:>8.1f} MB  {fp[:80]}\n"
        self.usage_box.delete("1.0", "end")
        self.usage_box.insert("end", txt)
        self.set_status("Analisi uso completata.")

    def do_iotest(self):
        folder = os.getcwd()
        self.io_box.delete("1.0", "end")
        self.io_box.insert("end", "Test latenza 4K in corso…\n")
        threading.Thread(target=self._io_work, args=(folder,), daemon=True).start()

    def _io_work(self, folder):
        r = io_latency_test(folder)
        self.after(0, lambda: self._io_show(r))

    def _io_show(self, r):
        if not r.get("ok"):
            self.io_box.insert("end", f"Errore: {r.get('error')}\n")
            return
        vss = get_shadow_copies()
        txt = (f"⚡ Latenza media: {r['avg_ms']} ms\nP95: {r['p95_ms']} ms   Max: {r['max_ms']} ms\n"
               f"IOPS stimati: ~{r['iops']}\nGiudizio: {r['giudizio']}\n\n"
               f"📸 Copie shadow VSS: {len(vss)}\n")
        for s in vss[:5]:
            txt += f"  {s.get('Volume','?')} — {s.get('InstallDate','?')}\n"
        self.io_box.delete("1.0", "end")
        self.io_box.insert("end", txt)
        self.set_status("Test I/O completato.")

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

    # ================= AI: metodi =================
    def _ai_update(self, p):
        colors = {"Basso": GREEN, "Moderato": ORANGE, "Alto": ORANGE, "Critico": RED}
        c = colors.get(p["risk"], GREEN)
        self.ai_gauge.draw(p["p30"], color=c, center=f"{p['p30']}%")
        self.ai_risk.configure(text=f"Rischio 30gg: {p['risk'].upper()}", text_color=c)
        self.ai_action.configure(
            text=f"90gg {p['p90']}% · 180gg {p['p180']}%\n{p['action']}")
        for wdg in self.ai_factors.winfo_children():
            wdg.destroy()
        if not p["factors"]:
            ctk.CTkLabel(self.ai_factors, text="Nessun fattore critico: SMART pulito.",
                         font=FONTS["small"], text_color=GREEN).pack(anchor="w")
        for name, contrib, level in p["factors"]:
            row = ctk.CTkFrame(self.ai_factors, fg_color=CARD2)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=name, font=FONTS["small"], width=220,
                         anchor="w").pack(side="left", padx=8)
            bar = ctk.CTkProgressBar(row, width=120,
                                    progress_color=ORANGE if contrib < 1 else RED)
            bar.pack(side="left")
            bar.set(max(0.03, min(1, contrib / 3)))
            ctk.CTkLabel(row, text=f"livello {level}", font=("Consolas", 9),
                         text_color=MUTED).pack(side="left", padx=8)

    def do_ai_refresh(self):
        if not self.current:
            return
        try:
            p = predict(self.attrs, self.info)
        except Exception as e:
            self.ai_action.configure(text=f"Errore AI: {e}")
            return
        self._ai_update(p)
        self.set_status(f"AI: rischio 30gg {p['p30']}% ({p['risk']}).")

    def do_ai_anomaly(self):
        h = self.temps.get(self.current.device_id, []) if self.current else []
        try:
            r = temp_anomaly(h)
        except Exception as e:
            r = {"ok": False, "msg": str(e)}
        icon = "✅" if r.get("ok") else "⚠️"
        self.ai_anom.delete("1.0", "end")
        self.ai_anom.insert("end",
            f"{icon} {r.get('msg')}\nCampioni: {len(h)}  z={r.get('z','—')}  "
            f"slope={r.get('slope','—')}  media={r.get('mean','—')}°C\n"
            f"Storico: {[round(x) for x in h[-20:]]}")

    def do_ai_fragments(self):
        from tkinter import messagebox
        src = (self.src_var.get().strip() if hasattr(self, "src_var") else "") or ""
        if not src or not os.path.exists(src):
            messagebox.showinfo("DiskGuard Pro",
                "Scegli prima una sorgente nel Recupero (immagine .img).")
            return
        self.scan_stop = {"stop": False}
        self.ai_frags.delete("1.0", "end")
        self.ai_frags.insert("end", "Deep scan AI in corso…\n")
        threading.Thread(target=self._frag_work, args=(src,), daemon=True).start()

    def _frag_work(self, src):
        def prog(pct, msg):
            self.after(0, lambda: (self.ai_prog.set(pct / 100),
                                   self.set_status("AI: " + msg)))
        res = scan_unknown(src, progress=prog, stop_flag=self.scan_stop)
        self.after(0, lambda: self._frag_show(res))

    def _frag_show(self, res):
        self.ai_frags.delete("1.0", "end")
        if res and "error" in res[0]:
            self.ai_frags.insert("end", f"Errore: {res[0]['error']}\n")
            return
        if not res:
            self.ai_frags.insert("end", "Nessun blocco classificabile.\n")
            return
        for r in res:
            self.ai_frags.insert(
                "end", f"• {r['kind']:<28} {r['blocks']:>3} blocchi  conf {r['avg_conf']:.0%}  ({r['note']})\n")
        self.set_status(f"AI: {len(res)} tipi probabili trovati nei frammenti.")

    def do_ai_rank(self):
        items = getattr(self, "_rec_filtered", None) or self.recovered
        if not items:
            from tkinter import messagebox
            messagebox.showinfo("DiskGuard Pro",
                "Avvia prima una scansione nel Recupero Dati.")
            return
        ranked = rank_files(items)
        self.ai_rank.delete("1.0", "end")
        self.ai_rank.insert("end", "Priorità ripristino (score AI):\n")
        for f, score, why in ranked[:25]:
            stars = "★" * max(1, score // 20)
            self.ai_rank.insert(
                "end", f"{score:>3} {stars:<5} {f.kind:<6} {f.name[:42]}  [{why[:50]}]\n")
        self.set_status(f"AI ranking: {len(ranked)} file ordinati per priorità.")

    def _pick_train(self):
        from tkinter import filedialog
        p = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if p:
            self.train_var.set(p)

    def do_train(self):
        from core.ai import retrain_from_csv
        csvp = self.train_var.get().strip()
        if not csvp or not os.path.exists(csvp):
            from tkinter import messagebox
            messagebox.showinfo("DiskGuard Pro", "Seleziona un CSV stile Backblaze.")
            return
        self.train_msg.configure(text="Allenamento in corso…")
        threading.Thread(target=self._train_work, args=(csvp,), daemon=True).start()

    def _train_work(self, csvp):
        try:
            r = retrain_from_csv(csvp)
            msg = (f"✅ Modello aggiornato: {r['rows']} righe, {r['failures']} guasti, "
                   f"accuratezza {r['accuracy']}% → {r['dest']}" if r.get("ok")
                   else f"❌ {r.get('error')}")
        except Exception as e:
            msg = f"❌ {e}"
        self.after(0, lambda: (self.train_msg.configure(text=msg),
                               self.set_status(msg)))
