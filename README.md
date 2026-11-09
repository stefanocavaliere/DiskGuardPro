# 🛡️ DiskGuard Pro — Controllo Hard Disk + Recupero Dati Avanzato (Windows 11)

App desktop in stile Windows 11 per:
- 🌡️ **Temperatura dischi** in tempo reale (SMART / StorageReliabilityCounter) + grafico, log CSV e allarmi
- 💽 **Salute dischi**: stato Windows, punteggio 0–100, tabella SMART completa, ore di accensione, usura SSD
- 🧲 **Recupero dati avanzato**: scansione rapida (cestino/tmp) + carving profondo per firme (JPEG/PNG/PDF/GIF/ZIP/DOCX/MP4), anteprima HEX, ripristino
- 🧰 **Strumenti**: clonazione disco / creazione immagine `.img`, benchmark lettura/scrittura, report TXT

## Requisiti (Windows 11)
- Python 3.10+ (https://www.python.org/downloads/ — spunta *Add to PATH*)
- **Esegui come Amministratore** per SMART reale e accesso disco raw
- Facoltativo ma consigliato: [smartmontools](https://www.smartmontools.org) → `smartctl.exe` per SMART completo

## Avvio rapido
1. Doppio clic su **`AVVIA_Windows11.bat`** (installa dipendenze e avvia), oppure:
```bat
pip install customtkinter psutil matplotlib Pillow wmi pywin32
python app.py
```

## Creare il .exe
```bat
pip install pyinstaller
pyinstaller DiskGuardPro.spec
```
Trovi `dist/DiskGuardPro.exe` (già configurato per richiedere privilegi admin).

## Uso recupero dati
1. Tab **Recupero Dati** → *Sorgente*: seleziona un'immagine `.img`
   oppure digita `\\.\PhysicalDrive0` (admin) per scansione diretta disco.
2. *Destinazione*: cartella dove salvare i file recuperati.
3. **Scansione rapida** = cestino/file tmp; **Scansione profonda** = carving firme.
4. Seleziona un file → **Anteprima HEX** → **Ripristina selezionato**.
5. Buona pratica forense: prima crea un'immagine con **Strumenti → Clona disco**,
   poi fai carving sull'immagine (non sul disco originale).

## Struttura
```
DiskGuardPro/
├── app.py                # interfaccia (tkinter, tema scuro Win11)
├── AVVIA_Windows11.bat   # setup+avvio
├── DiskGuardPro.spec     # build pyinstaller → .exe
├── requirements.txt
└── core/
    ├── disks.py          # rilevamento dischi (PowerShell + psutil)
    ├── smart.py          # SMART via smartctl / PowerShell / demo
    ├── recovery.py       # quick scan, carving, hex, clone raw
    └── monitor.py        # monitor temperatura, log CSV, benchmark
```

## Note
- Su Linux/Mac o senza permessi l'app gira in **modalità demo** con dati simulati.
- Il carving ZIP/DOCX/MP4 (senza footer fisso) salva finestre da 8 MB: verifica i file recuperati.
- Valori SMART reali solo su Windows + smartmontools + esecuzione amministratore.
