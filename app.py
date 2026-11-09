"""
DiskGuard Pro 1.0 - App desktop Windows 11
Controllo Hard Disk (temperatura e salute) + Recupero Dati Avanzato.

Avvio:
    pip install -r requirements.txt
    python app.py

Su Windows: eseguire come Amministratore per SMART / carving disco raw.
Richiede smartmontools (https://www.smartmontools.org) per SMART completo.
"""
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.disks import get_physical_disks
from core.smart import read_smart, health_score
from core.recovery import quick_scan_deleted, carve_file, hex_preview, copy_with_progress, SIGNATURES
from core.monitor import TempMonitor, disk_benchmark

APP_TITLE = "DiskGuard Pro — Salute Dischi & Recupero Dati"
BG, BG2, FG, ACC = "#0f1115", "#161a22", "#e8ecf3", "#3b82f6"

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1180x760")
        self.configure(bg=BG)
        self.disks = []
        self.current = None
        self.attrs = []
        self.info = {}
        self.recovered = []
        self.scan_stop = {"stop": False}
        self._build_ui()
        self.refresh_disks()
        # monitor temperatura
        self.monitor = TempMonitor(self._all_temps, interval_s=5, alert_temp=55,
                                   on_alert=self._on_temp_alert)
        self.monitor.start()
        self.after(2000, self._tick_monitor)

    # ---------- UI ----------
    def _build_ui(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG2, foreground=FG, padding=(14, 8))
        style.map("TNotebook.Tab", background=[("selected", ACC)])
        style.configure("Treeview", background=BG2, foreground=FG, fieldbackground=BG2, rowheight=24)
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG)

        top = tk.Frame(self, bg=BG2, height=64)
        top.pack(fill="x")
        tk.Label(top, text="🛡️ DiskGuard Pro", font=("Segoe UI", 18, "bold"),
                 bg=BG2, fg="white").pack(side="left", padx=16, pady=10)
        tk.Label(top, text="Windows 11 • Temperatura • SMART • Recupero dati",
                 bg=BG2, fg="#9aa4b2", font=("Segoe UI", 10)).pack(side="left")
        self.clock = tk.Label(top, bg=BG2, fg="#9aa4b2", font=("Segoe UI", 10))
        self.clock.pack(side="right", padx=16)
        self._clock()

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=10)
        self.nb = nb

        # TAB 1 dashboard
        f1 = ttk.Frame(nb)
        nb.add(f1, text="  💽 Dashboard Salute  ")
        self._build_dash(f1)
        # TAB 2 SMART
        f2 = ttk.Frame(nb)
        nb.add(f2, text="  🌡️ Temperatura & SMART  ")
        self._build_smart(f2)
        # TAB 3 recupero
        f3 = ttk.Frame(nb)
        nb.add(f3, text="  🧲 Recupero Dati  ")
        self._build_recovery(f3)
        # TAB 4 strumenti
        f4 = ttk.Frame(nb)
        nb.add(f4, text="  🧰 Strumenti  ")
        self._build_tools(f4)

        self.status = tk.Label(self, text="Pronto.", anchor="w", bg=BG2, fg="#9aa4b2",
                               font=("Segoe UI", 9))
        self.status.pack(fill="x", padx=10, pady=(0, 8))

    def _clock(self):
        try:
            self.clock.config(text=datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
        except Exception:
            pass
        self.after(1000, self._clock)

    def set_status(self, t):
        self.status.config(text=t)

    # ----- TAB dashboard -----
    def _build_dash(self, f):
        left = tk.Frame(f, bg=BG)
        left.pack(side="left", fill="y", padx=10, pady=10)
        tk.Label(left, text="Dischi rilevati", bg=BG, fg=FG,
                 font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.disk_list = tk.Listbox(left, width=42, height=18, bg=BG2, fg=FG,
                                    selectbackground=ACC, font=("Consolas", 10))
        self.disk_list.pack(pady=8)
        self.disk_list.bind("<<ListboxSelect>>", lambda e: self.select_disk())
        tk.Button(left, text="🔄 Aggiorna", command=self.refresh_disks,
                  bg=ACC, fg="white", font=("Segoe UI", 10, "bold"),
                  relief="flat", padx=12, pady=6).pack(anchor="w")

        right = tk.Frame(f, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        self.health_big = tk.Label(right, text="—", bg=BG, fg=FG, font=("Segoe UI", 44, "bold"))
        self.health_big.pack(anchor="w")
        self.health_sub = tk.Label(right, text="", bg=BG, fg="#9aa4b2", font=("Segoe UI", 11))
        self.health_sub.pack(anchor="w")
        self.dash_info = tk.Text(right, height=16, bg=BG2, fg=FG, font=("Consolas", 10),
                                 relief="flat", padx=10, pady=10)
        self.dash_info.pack(fill="both", expand=True, pady=10)

    # ----- TAB smart -----
    def _build_smart(self, f):
        cols = ("id", "nome", "valore", "peggiore", "soglia", "grezzo", "stato")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=16)
        heads = [("id", "ID"), ("nome", "Attributo"), ("valore", "Valore"),
                 ("peggiore", "Peggiore"), ("soglia", "Soglia"),
                 ("grezzo", "Dato grezzo"), ("stato", "Stato")]
        for c, h in heads:
            self.tree.heading(c, text=h)
        self.tree.column("id", width=50, anchor="center")
        self.tree.column("nome", width=220)
        self.tree.column("valore", width=70, anchor="center")
        self.tree.column("peggiore", width=70, anchor="center")
        self.tree.column("soglia", width=70, anchor="center")
        self.tree.column("grezzo", width=160, anchor="center")
        self.tree.column("stato", width=80, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)
        bar = tk.Frame(f, bg=BG)
        bar.pack(fill="x", padx=10, pady=6)
        tk.Button(bar, text="📥 Esporta report TXT", command=self.export_report,
                  bg="#1f2937", fg="white", relief="flat", padx=10, pady=6).pack(side="left", padx=4)
        self.temp_lbl = tk.Label(bar, text="", bg=BG, fg=FG, font=("Segoe UI", 11, "bold"))
        self.temp_lbl.pack(side="right")

    # ----- TAB recupero -----
    def _build_recovery(self, f):
        top = tk.Frame(f, bg=BG)
        top.pack(fill="x", padx=10, pady=8)
        tk.Label(top, text="Sorgente (immagine .img o disco):", bg=BG, fg=FG).pack(side="left")
        self.src_var = tk.StringVar()
        tk.Entry(top, textvariable=self.src_var, width=70, bg=BG2, fg=FG,
                 insertbackground="white").pack(side="left", padx=8)
        tk.Button(top, text="Sfoglia…", command=self._pick_src,
                  bg="#1f2937", fg="white", relief="flat").pack(side="left")
        top2 = tk.Frame(f, bg=BG)
        top2.pack(fill="x", padx=10, pady=4)
        tk.Label(top2, text="Destinazione recupero:", bg=BG, fg=FG).pack(side="left")
        self.dst_var = tk.StringVar(value=os.path.join(os.getcwd(), "recuperati"))
        tk.Entry(top2, textvariable=self.dst_var, width=70, bg=BG2, fg=FG,
                 insertbackground="white").pack(side="left", padx=8)
        tk.Button(top2, text="Sfoglia…", command=self._pick_dst,
                  bg="#1f2937", fg="white", relief="flat").pack(side="left")

        btns = tk.Frame(f, bg=BG)
        btns.pack(fill="x", padx=10, pady=6)
        tk.Button(btns, text="⚡ Scansione rapida (cestino/tmp)",
                  command=self.do_quick, bg="#065f46", fg="white",
                  relief="flat", padx=10, pady=6).pack(side="left", padx=4)
        tk.Button(btns, text="🧲 Scansione profonda (carving)",
                  command=self.do_carve, bg=ACC, fg="white",
                  font=("Segoe UI", 10, "bold"), relief="flat", padx=10, pady=6).pack(side="left", padx=4)
        tk.Button(btns, text="⏹ Stop", command=lambda: self.scan_stop.update(stop=True),
                  bg="#7f1d1d", fg="white", relief="flat", padx=10, pady=6).pack(side="left", padx=4)
        tk.Button(btns, text="👁 Anteprima HEX", command=self.do_hex,
                  bg="#1f2937", fg="white", relief="flat", padx=10, pady=6).pack(side="left", padx=4)
        tk.Button(btns, text="💾 Ripristina selezionato", command=self.do_restore,
                  bg="#1f2937", fg="white", relief="flat", padx=10, pady=6).pack(side="left", padx=4)

        self.prog = ttk.Progressbar(f, length=400, mode="determinate")
        self.prog.pack(fill="x", padx=10, pady=4)
        self.prog_lbl = tk.Label(f, text="", bg=BG, fg="#9aa4b2")
        self.prog_lbl.pack(anchor="w", padx=10)

        cols = ("nome", "tipo", "dim", "percorso")
        self.rtree = ttk.Treeview(f, columns=cols, show="headings", height=12)
        for c, h in [("nome", "File"), ("tipo", "Tipo"), ("dim", "Dimensione"), ("percorso", "Percorso")]:
            self.rtree.heading(c, text=h)
        self.rtree.column("nome", width=260)
        self.rtree.column("tipo", width=100, anchor="center")
        self.rtree.column("dim", width=110, anchor="center")
        self.rtree.column("percorso", width=500)
        self.rtree.pack(fill="both", expand=True, padx=10, pady=6)

    # ----- TAB strumenti -----
    def _build_tools(self, f):
        g = tk.Frame(f, bg=BG)
        g.pack(fill="both", expand=True, padx=14, pady=14)
        tk.Label(g, text="Clona disco / Crea immagine", bg=BG, fg=FG,
                 font=("Segoe UI", 12, "bold")).pack(anchor="w")
        row = tk.Frame(g, bg=BG)
        row.pack(fill="x", pady=6)
        self.clone_src = tk.StringVar()
        self.clone_dst = tk.StringVar(value=os.path.join(os.getcwd(), "immagine_disco.img"))
        tk.Entry(row, textvariable=self.clone_src, width=55, bg=BG2, fg=FG).pack(side="left", padx=4)
        tk.Button(row, text="Sorgente…", command=lambda: self._pick_into(self.clone_src),
                  bg="#1f2937", fg="white", relief="flat").pack(side="left", padx=2)
        tk.Entry(row, textvariable=self.clone_dst, width=55, bg=BG2, fg=FG).pack(side="left", padx=4)
        tk.Button(row, text="Destinazione…", command=lambda: self._pick_save_into(self.clone_dst),
                  bg="#1f2937", fg="white", relief="flat").pack(side="left", padx=2)
        tk.Button(g, text="💿 Avvia clonazione / immagine", command=self.do_clone,
                  bg=ACC, fg="white", font=("Segoe UI", 10, "bold"),
                  relief="flat", padx=12, pady=6).pack(anchor="w", pady=4)

        tk.Label(g, text="Benchmark velocità disco", bg=BG, fg=FG,
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(14, 0))
        brow = tk.Frame(g, bg=BG)
        brow.pack(fill="x", pady=6)
        self.bench_var = tk.StringVar(value=os.getcwd())
        tk.Entry(brow, textvariable=self.bench_var, width=70, bg=BG2, fg=FG).pack(side="left", padx=4)
        tk.Button(brow, text="Cartella…",
                  command=lambda: self._pick_dir_into(self.bench_var),
                  bg="#1f2937", fg="white", relief="flat").pack(side="left")
        tk.Button(brow, text="▶ Test 100 MB", command=self.do_bench,
                  bg="#065f46", fg="white", relief="flat", padx=10).pack(side="left", padx=8)
        self.bench_lbl = tk.Label(g, text="", bg=BG, fg=FG, font=("Consolas", 11))
        self.bench_lbl.pack(anchor="w")

        tk.Label(g, text="Soglia allarme temperatura (°C)", bg=BG, fg=FG).pack(anchor="w", pady=(14, 0))
        self.alert_var = tk.IntVar(value=55)
        tk.Spinbox(g, from_=40, to=80, textvariable=self.alert_var, width=6,
                   command=lambda: setattr(self.monitor, "alert_temp", self.alert_var.get())).pack(anchor="w")
        tk.Label(g, text="Log temperature: cartella logs/ (CSV giornaliero). Grafico ultimi rilevamenti:",
                 bg=BG, fg="#9aa4b2").pack(anchor="w", pady=(10, 0))
        self.hist_txt = tk.Text(g, height=8, bg=BG2, fg=FG, font=("Consolas", 9), relief="flat")
        self.hist_txt.pack(fill="both", expand=True, pady=6)

    # ---------- logica ----------
    def refresh_disks(self):
        self.set_status("Rilevamento dischi…")
        def work():
            disks = get_physical_disks()
            self.after(0, lambda: self._show_disks(disks))
        threading.Thread(target=work, daemon=True).start()

    def _show_disks(self, disks):
        self.disks = disks
        self.disk_list.delete(0, "end")
        for d in disks:
            self.disk_list.insert("end", f"{d.device_id} — {d.friendly_name} ({d.size_gb} GB)")
        if disks:
            self.disk_list.selection_set(0)
            self.select_disk()
        self.set_status(f"Trovati {len(disks)} dischi/unità.")

    def select_disk(self):
        sel = self.disk_list.curselection()
        if not sel:
            return
        d = self.disks[sel[0]]
        self.current = d
        self.set_status(f"Lettura SMART di {d.device_id}…")
        def work():
            attrs, info = read_smart(d.device_id)
            self.after(0, lambda: self._show_health(d, attrs, info))
        threading.Thread(target=work, daemon=True).start()

    def _show_health(self, d, attrs, info):
        self.attrs, self.info = attrs, info
        temp = info.get("temp_c")
        score, label, color = health_score(attrs, temp)
        colors = {"green": "#22c55e", "orange": "#f59e0b", "red": "#ef4444"}
        self.health_big.config(text=f"{score}/100 — {label}", fg=colors.get(color, "white"))
        tstr = f"{temp} °C" if temp is not None else "n/d (installa smartmontools / avvia come admin)"
        self.health_sub.config(text=f"{d.friendly_name}  •  {d.size_gb} GB  •  🌡 {tstr}")
        lines = [
            f"Dispositivo : {d.device_id}",
            f"Modello     : {d.friendly_name}",
            f"Tipo/Bus    : {d.media_type} / {d.bus_type}",
            f"Capacità    : {d.size_gb} GB  (usati {d.used_gb} • liberi {d.free_gb} {d.mount})",
            f"Filesystem  : {d.filesystem}",
            f"Stato Win   : {d.health_status} / {d.operational_status}",
            f"Seriale     : {info.get('serial', '—')}",
            f"Ore accens. : {info.get('power_on_hours', '—')}",
            f"Temperatura : {tstr}",
            "",
            "Attributi SMART principali:",
        ]
        for a in attrs[:12]:
            lines.append(f"  [{a['id']:>3}] {a['name']:<24} val={a['value']}  raw={a['raw']}  {a['status']}")
        if info.get("demo"):
            lines.append("")
            lines.append("⚠ MODALITÀ DEMO: dati simulati (su Windows con smartmontools vedrai valori reali).")
        self.dash_info.delete("1.0", "end")
        self.dash_info.insert("1.0", "\n".join(lines))
        # tab smart
        for i in self.tree.get_children():
            self.tree.delete(i)
        for a in attrs:
            self.tree.insert("", "end", values=(a["id"], a["name"], a["value"],
                                                a["worst"], a["thresh"], a["raw"], a["status"]))
        self.temp_lbl.config(text=f"🌡 {tstr}   •   Salute: {info.get('health', '—')}")
        self.set_status("Pronto.")

    # monitor
    def _all_temps(self):
        out = {}
        for d in self.disks:
            try:
                _, info = read_smart(d.device_id)
                if info.get("temp_c") is not None:
                    out[d.device_id] = info["temp_c"]
            except Exception:
                continue
        return out

    def _on_temp_alert(self, dev, t):
        self.after(0, lambda: messagebox.showwarning(
            "DiskGuard Pro — Temperatura alta",
            f"⚠ {dev} a {t} °C!\nControlla ventilazione / backup immediato consigliato."))

    def _tick_monitor(self):
        try:
            h = self.monitor.history[-12:]
            if h and hasattr(self, "hist_txt"):
                self.hist_txt.delete("1.0", "end")
                for ts, dev, t in h:
                    bar = "█" * max(1, min(30, int((t or 0) / 2)))
                    self.hist_txt.insert("end", f"{ts}  {dev:<16} {t:>3}°C  {bar}\n")
        except Exception:
            pass
        self.after(5000, self._tick_monitor)

    # ---------- recupero ----------
    def _pick_src(self):
        p = filedialog.askopenfilename(title="Sorgente (immagine .img / file raw / disco)")
        if p:
            self.src_var.set(p)

    def _pick_dst(self):
        p = filedialog.askdirectory(title="Cartella destinazione")
        if p:
            self.dst_var.set(p)

    def _pick_into(self, var):
        p = filedialog.askopenfilename(title="Sorgente")
        if p:
            var.set(p)

    def _pick_save_into(self, var):
        p = filedialog.asksaveasfilename(title="Destinazione immagine",
                                        defaultextension=".img",
                                        filetypes=[("Immagine raw", "*.img"), ("Tutti", "*.*")])
        if p:
            var.set(p)

    def _pick_dir_into(self, var):
        p = filedialog.askdirectory()
        if p:
            var.set(p)

    def _progress(self, pct, msg):
        self.after(0, lambda: (self.prog.config(value=pct), self.prog_lbl.config(text=msg),
                               self.set_status(msg)))

    def do_quick(self):
        base = self.src_var.get() or "C:\\"
        if os.path.isfile(base):
            base = os.path.dirname(base)
        self.set_status("Scansione rapida…")
        def work():
            res = quick_scan_deleted(base)
            self.after(0, lambda: self._show_rec(res, "Scansione rapida completata"))
        threading.Thread(target=work, daemon=True).start()

    def do_carve(self):
        src = self.src_var.get().strip()
        dst = self.dst_var.get().strip() or os.path.join(os.getcwd(), "recuperati")
        if not src or not os.path.exists(src):
            messagebox.showinfo("DiskGuard Pro",
                "Seleziona una sorgente valida.\n\n"
                "• Per provare: crea prima un'immagine con Strumenti → Clona disco.\n"
                "• Su Windows puoi usare \\\\.\\PhysicalDrive0 come sorgente\n"
                "  (digita il percorso a mano ed esegui come Amministratore).")
            return
        self.scan_stop = {"stop": False}
        self.set_status("Scansione profonda in corso…")
        def work():
            res = carve_file(src, dst,
                             types=["JPEG", "PNG", "PDF", "GIF", "ZIP"],
                             progress=self._progress, stop_flag=self.scan_stop)
            self.after(0, lambda: self._show_rec(res, f"Carving completato: {len(res)} file in {dst}"))
        threading.Thread(target=work, daemon=True).start()

    def _show_rec(self, res, msg):
        self.recovered = res
        for i in self.rtree.get_children():
            self.rtree.delete(i)
        for f in res:
            mb = f"{f.size/1024:.1f} KB" if f.size < 1024*1024 else f"{f.size/1024/1024:.2f} MB"
            self.rtree.insert("", "end", values=(f.name, f.kind, mb, f.path))
        self.set_status(f"{msg} — {len(res)} file.")
        if not res:
            messagebox.showinfo("DiskGuard Pro", "Nessun file recuperabile trovato nella sorgente.")

    def do_hex(self):
        sel = self.rtree.selection()
        if not sel:
            messagebox.showinfo("DiskGuard Pro", "Seleziona un file dalla lista.")
            return
        path = self.rtree.item(sel[0])["values"][3]
        win = tk.Toplevel(self)
        win.title(f"Anteprima HEX — {os.path.basename(path)}")
        win.geometry("760x480")
        t = tk.Text(win, bg="#0b0e13", fg="#a5f3a5", font=("Consolas", 9))
        t.pack(fill="both", expand=True)
        t.insert("1.0", hex_preview(path, 8192))

    def do_restore(self):
        sel = self.rtree.selection()
        if not sel:
            messagebox.showinfo("DiskGuard Pro", "Seleziona un file dalla lista.")
            return
        src = self.rtree.item(sel[0])["values"][3]
        dst = filedialog.asksaveasfilename(initialfile=os.path.basename(src))
        if not dst:
            return
        try:
            import shutil
            shutil.copy2(src, dst)
            messagebox.showinfo("DiskGuard Pro", f"File ripristinato in:\n{dst}")
        except Exception as e:
            messagebox.showerror("DiskGuard Pro", f"Errore: {e}")

    # ---------- strumenti ----------
    def do_clone(self):
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
                copy_with_progress(src, dst, progress=self._progress, stop_flag=stop)
                self.after(0, lambda: self.set_status(f"Immagine salvata: {dst}"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("DiskGuard Pro", f"Errore: {e}"))
        threading.Thread(target=work, daemon=True).start()

    def do_bench(self):
        folder = self.bench_var.get().strip() or os.getcwd()
        self.bench_lbl.config(text="Test in corso…")
        def work():
            r = disk_benchmark(folder, 100, progress=self._progress)
            def show():
                if r.get("ok"):
                    self.bench_lbl.config(
                        text=f"⚡ Scrittura: {r['write_mbs']} MB/s   •   Lettura: {r['read_mbs']} MB/s  (100 MB)")
                else:
                    self.bench_lbl.config(text=f"Errore: {r.get('error')}")
            self.after(0, show)
        threading.Thread(target=work, daemon=True).start()

    def export_report(self):
        if not self.current:
            return
        p = filedialog.asksaveasfilename(defaultextension=".txt",
            initialfile=f"diskguard_report_{self.current.device_id}.txt",
            filetypes=[("Testo", "*.txt")])
        if not p:
            return
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"DiskGuard Pro — Report disco {datetime.now():%d/%m/%Y %H:%M}\n")
            f.write(f"Dispositivo: {self.current.device_id} {self.current.friendly_name}\n")
            f.write(f"Info: {self.info}\n\nSMART:\n")
            for a in self.attrs:
                f.write(f"{a}\n")
        messagebox.showinfo("DiskGuard Pro", f"Report salvato:\n{p}")


if __name__ == "__main__":
    App().mainloop()
