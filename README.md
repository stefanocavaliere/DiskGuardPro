# 🛡️ DiskGuard Pro 2.0 — Drive Manager stile Samsung Magician (Windows 11)

Interfaccia ispirata a **Samsung Magician**: sidebar di navigazione, selettore unità in alto,
card **Stato di salute** (anello 0–100), **Temperatura** (valore + mini-grafico + allarmi),
**Vita residua / TBW**, **Volumi** con barre d'uso, benchmark, diagnostica e recupero dati.

## Pagine

| Voce sidebar | Contenuto |
|---|---|
| ◉ Drive Dashboard | Anello salute, temperatura + grafico, vita residua/TBW, volumi, info unità (modello, interfaccia, seriale, firmware), azioni rapide |
| ⚡ Performance | Benchmark lettura/scrittura sequenziale con card dedicate + cronologia test |
| 🩺 Diagnostica | Test rapido S.M.A.R.T. + self-test esteso, log, tabella attributi completa |
| 🧲 Recupero Dati | Scansione rapida (cestino/tmp) + carving profondo (JPEG/PNG/PDF/GIF/ZIP), anteprima HEX, ripristino |
| 🧰 Strumenti | Clona disco / immagine forense `.img`, soglia allarme temperatura, note firmware |

## Requisiti (Windows 11)
- Python 3.10+ (spunta *Add to PATH*)
- **Esegui come Amministratore** per SMART reale e accesso disco raw
- Facoltativo ma consigliato: [smartmontools](https://www.smartmontools.org) → `smartctl.exe`

## Avvio rapido
1. Doppio clic su **`AVVIA_Windows11.bat`**, oppure:
```bat
pip install -r requirements.txt
python app.py
```

## Creare il .exe
```bat
pip install pyinstaller
pyinstaller DiskGuardPro.spec
```
`dist/DiskGuardPro.exe` (richiede privilegi admin, nessuna console).

## Recupero dati — flusso consigliato
1. **Strumenti → Clona disco** per creare l'immagine `.img` del disco.
2. **Recupero Dati** → sorgente = immagine, destinazione = cartella.
3. **Scansione profonda** → verifica → **Ripristina**.

## Struttura
```
DiskGuardPro/
├── app.py                # UI CustomTkinter stile Magician (Ring, Spark, 5 pagine)
├── AVVIA_Windows11.bat   # setup + avvio
├── DiskGuardPro.spec     # build pyinstaller → .exe (uac_admin)
├── requirements.txt      # customtkinter, psutil, Pillow, wmi, pywin32
└── core/
    ├── disks.py          # rilevamento dischi (PowerShell + psutil)
    ├── smart.py          # SMART via smartctl / PowerShell / demo
    ├── recovery.py       # quick scan, carving, hex, clone raw
    └── monitor.py        # monitor temperatura, CSV, benchmark
```

## Note
- Linguaggio invariato: **Python** — per un'app leggera da .exe basta cambiare framework GUI
  (tkinter → **CustomTkinter**): look moderno senza la pesantezza di Electron/Tauri.
- Su Linux/Mac o senza permessi l'app gira in **modalità demo** con dati simulati.
- Il carving ZIP/DOCX/MP4 (senza footer fisso) salva finestre da 8 MB: verifica i file recuperati.
