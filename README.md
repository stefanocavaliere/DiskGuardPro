# 🛡️🤖 DiskGuard Pro 4.0 — Drive Manager stile Samsung Magician + AI locale (Windows 11)

Interfaccia ispirata a **Samsung Magician** + **motori AI 100% offline** (stdlib, nessun cloud/API key).

## Pagine

| Voce sidebar | Contenuto |
|---|---|
| ◉ Drive Dashboard | Anello salute, temperatura + grafico, vita residua/TBW, volumi, info unità, **verdetto AI** |
| ⚡ Performance | Benchmark lettura/scrittura + cronologia |
| 🩺 Diagnostica | Test rapido S.M.A.R.T. + self-test esteso, tabella attributi |
| 🗺 Analisi Disco | Layout GPT/MBR, **mappa superficie**, uso disco, latenza I/O 4K, copie shadow VSS |
| 🤖 **AI Predittiva** | Rischio guasto 30/90/180gg, fattori, anomaly detection temp, deep scan frammenti, ranking file, ri-allenamento |
| 🧲 Recupero Dati | 19 firme, checkbox tipi, validazione, anteprima immagini, hash, filtri, report CSV/HTML |
| 🧰 Strumenti | Clona disco / immagine `.img`, soglia allarme, note firmware |

## 🤖 Motori AI (`core/ai.py`, solo stdlib)

1. **SMARTPredictor** — regressione logistica su 8 feature
   (realloc, pending, uncorr, temp, ore, CRC, usura, cicli) con pesi pre-allenati
   stile Backblaze. Output: probabilità 30/90/180gg + livello (Basso/Moderato/Alto/Critico)
   + fattori spiegabili + azione consigliata.
2. **Anomaly detection temperatura** — z-score + trend lineare sullo storico monitorato.
3. **FragmentClassifier** — classifica blocchi *senza header* (frammenti JPEG/MP3,
   TESTO, compresso/cifrato…) via entropia, marker, sync — per il deep scan.
4. **Ranking file** — score AI 0–100 per prioritizzare il ripristino
   (validità + tipo + dimensione plausibile).
5. **Ri-allenamento** — `python tools/train_ai.py dati.csv` (CSV stile Backblaze:
   `smart_5/197/198/194/9_raw + failure`) → scrive `core/ai_weights.json`
   usato automaticamente dall'app.

## Requisiti (Windows 11)
- Python 3.10+ (spunta *Add to PATH*)
- **Esegui come Amministratore** per SMART reale e disco raw
- [smartmontools](https://www.smartmontools.org) consigliato (`smartctl.exe`)

## Avvio
Doppio clic su **`AVVIA_Windows11.bat`**, oppure:
```bat
pip install -r requirements.txt
python app.py
```

## Build .exe
```bat
pip install pyinstaller
pyinstaller DiskGuardPro.spec
```

## Flusso forense consigliato
Strumenti → immagine `.img` → Analisi (surface scan) → AI (deep scan frammenti + ranking) → Recupero → Report CSV/HTML.

## Struttura
```
DiskGuardPro/
├── app.py                # UI CustomTkinter (Ring, Spark, 7 pagine)
├── AVVIA_Windows11.bat / DiskGuardPro.spec / requirements.txt
├── core/
│   ├── ai.py             # predizione, anomaly, classifier, ranking, retrain
│   ├── analysis.py       # layout, surface, uso disco, I/O, VSS
│   ├── recovery.py       # 19 firme, validazione, hash, preview, report
│   ├── disks.py / smart.py / monitor.py
└── tools/train_ai.py     # ri-allena il modello su CSV Backblaze
```

## Note
- Linguaggio invariato (**Python + CustomTkinter**): niente Electron, `.exe` leggero.
- Fuori Windows/senza permessi: modalità demo con dati simulati.
- L'AI è euristica locale, non diagnosi certificata: conferma sempre con backup + tool del produttore.
