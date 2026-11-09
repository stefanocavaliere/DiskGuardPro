"""
DiskGuard Pro - core/ai.py (v4.0)
Motori AI locali (100% offline, nessuna dipendenza extra, solo stdlib):

1) SMARTPredictor — predizione rischio guasto a 30/90/180 giorni.
   Regressione logistica con pesi pre-allenati su statistiche stile Backblaze
   (drive reali: realloc/pending/uncorrectable/temp/ore/CRC/usura).
   Ri-allenabile dall'utente con CSV Backblaze (tools/train_ai.py).

2) FragmentClassifier — classifica blocchi sconosciuti (senza header) per tipo
   probabile con analisi statistica del contenuto (entropia, byte stampabili,
   marker specifici, sync MP3, restart JPEG...).

3) rank_files — punteggio AI 0-100 per prioritizzare i file recuperati.

4) temp_anomaly — anomaly detection (z-score + trend) sullo storico temperatura.
"""
import json
import math
import os
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------- predizione
FEATURES = ["realloc", "pending", "uncorr", "temp", "poh", "crc", "wear", "cycles"]

# pesi pre-allenati (logit = b + Σ w·x, x normalizzate 0..~1)
_BUNDLED = {
    "intercept": -4.2,
    "weights": {
        "realloc": 3.0, "pending": 2.6, "uncorr": 2.2, "temp": 1.4,
        "poh": 0.8, "crc": 1.0, "wear": 1.2, "cycles": 0.3,
    },
}

FACTOR_NAMES = {
    "realloc": "Settori riallocati",
    "pending": "Settori in attesa (pending)",
    "uncorr": "Errori non correggibili",
    "temp": "Temperatura elevata",
    "poh": "Ore di accensione elevate",
    "crc": "Errori CRC interfaccia",
    "wear": "Usura NAND/SSD",
    "cycles": "Cicli accensione elevati",
}


def _clip(x, lo=0.0, hi=1.2):
    return max(lo, min(hi, x))


def _to_int(v) -> int:
    try:
        return int(str(v).split()[0])
    except Exception:
        return 0


def extract_features(attrs: List[dict], info: dict) -> Dict[str, float]:
    """Normalizza attributi SMART in feature 0..~1."""
    by_id = {}
    for a in attrs or []:
        try:
            by_id[int(a.get("id"))] = _to_int(a.get("raw"))
        except Exception:
            pass
    temp = info.get("temp_c")
    try:
        temp = float(temp)
    except Exception:
        temp = None
    wear_used = 0.0
    for a in attrs or []:
        if a.get("id") == 177:  # wear leveling: raw = % usura usata (su alcuni drive)
            try:
                r = _to_int(a.get("raw"))
                wear_used = _clip(r / 100.0) if r <= 100 else 0.0
            except Exception:
                pass
    w = info.get("wear")
    if isinstance(w, str) and "%" in w:
        try:
            wear_used = _clip((100 - float(w.replace("%", ""))) / 100.0)
        except Exception:
            pass
    poh = by_id.get(9, info.get("power_on_hours") or 0)
    try:
        poh = int(poh)
    except Exception:
        poh = 0
    return {
        "realloc": _clip(math.log1p(by_id.get(5, 0)) / math.log1p(50)),
        "pending": _clip(math.log1p(by_id.get(197, 0)) / math.log1p(20)),
        "uncorr": _clip(math.log1p(by_id.get(198, 0)) / math.log1p(20)),
        "temp": _clip(((temp - 35) / 25.0)) if temp is not None else 0.2,
        "poh": _clip(math.log1p(max(0, poh)) / math.log1p(50000)),
        "crc": _clip(math.log1p(by_id.get(199, 0) + by_id.get(199, 0) * 0) / math.log1p(100)),
        "wear": _clip(wear_used),
        "cycles": _clip(math.log1p(by_id.get(12, 0)) / math.log1p(10000)),
    }


def _load_model() -> dict:
    """Modello ri-allenato dall'utente se presente, altrimenti pesi bundled."""
    for p in [os.path.join(os.path.dirname(__file__), "ai_weights.json"),
              os.path.join(os.getcwd(), "ai_weights.json")]:
        try:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    m = json.load(f)
                if "weights" in m and "intercept" in m:
                    return m
        except Exception:
            pass
    return _BUNDLED


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, x))))


def predict(attrs: List[dict], info: dict) -> dict:
    """Ritorna {p30,p90,p180 (%), risk, action, factors, logit}."""
    model = _load_model()
    w = model["weights"]
    b = model.get("intercept", -4.2)
    feats = extract_features(attrs, info)
    logit = b + sum(w.get(k, 0.0) * feats.get(k, 0.0) for k in FEATURES)
    p30 = _sigmoid(logit)
    p90 = 1 - (1 - p30) ** 3
    p180 = 1 - (1 - p30) ** 6
    if p30 < 0.05:
        risk, action = "Basso", "Nessuna azione urgente. Mantieni backup di routine e monitoraggio temperatura."
    elif p30 < 0.15:
        risk, action = "Moderato", "Aumenta frequenza backup (settimanale). Ricontrolla SMART tra 30 giorni."
    elif p30 < 0.40:
        risk, action = "Alto", "Backup completo immediato + clona il disco. Pianifica sostituzione entro 90 giorni."
    else:
        risk, action = "Critico", "⛔ Sostituisci il disco ora: clona su nuova unità e non usarlo per dati importanti."
    contrib = sorted(((k, w.get(k, 0.0) * feats.get(k, 0.0)) for k in FEATURES),
                     key=lambda x: x[1], reverse=True)
    factors = [(FACTOR_NAMES[k], round(c, 3), round(feats[k], 3)) for k, c in contrib if c > 0.02]
    return {"p30": round(p30 * 100, 1), "p90": round(p90 * 100, 1),
            "p180": round(p180 * 100, 1), "risk": risk, "action": action,
            "factors": factors, "logit": round(logit, 3)}


def ai_verdict(attrs, info) -> str:
    """Riga di verdetto AI per diagnostica/dashboard."""
    p = predict(attrs, info)
    icon = {"Basso": "✅", "Moderato": "⚠️", "Alto": "🔶", "Critico": "⛔"}.get(p["risk"], "•")
    top = ", ".join(f[0] for f in p["factors"][:2]) or "nessun fattore critico"
    return (f"{icon} AI: rischio guasto 30gg {p['p30']}% ({p['risk']}) — "
            f"90gg {p['p90']}% · 180gg {p['p180']}% · fattori: {top}")


# ------------------------------------------------------- anomaly temperatura
def temp_anomaly(history: List[float]) -> dict:
    """Z-score + trend lineare sullo storico temperature."""
    h = [x for x in history if x is not None]
    if len(h) < 5:
        return {"ok": True, "msg": "dati insufficienti (servono ≥5 campioni)"}
    n = len(h)
    mean = sum(h) / n
    var = sum((x - mean) ** 2 for x in h) / n
    std = math.sqrt(var) if var > 0 else 0.5
    z = (h[-1] - mean) / std if std else 0
    xs = list(range(n))
    mx = sum(xs) / n
    slope = (sum((x - mx) * (y - mean) for x, y in zip(xs, h)) /
             (sum((x - mx) ** 2 for x in xs) or 1))
    flags = []
    if abs(z) > 2.5:
        flags.append(f"picco anomalo: {h[-1]:.0f}°C (z={z:+.1f})")
    if slope > 0.15:
        flags.append(f"trend in aumento (+{slope:.2f}°C/campione)")
    elif slope < -0.15:
        flags.append("trend in calo (raffreddamento)")
    return {"ok": not flags, "z": round(z, 2), "slope": round(slope, 3),
            "mean": round(mean, 1),
            "msg": "; ".join(flags) if flags else f"stabile attorno a {mean:.0f}°C"}


# ------------------------------------------------------- classifica frammenti
def _entropy(data: bytes) -> float:
    if not data:
        return 0.0
    from collections import Counter
    c = Counter(data)
    n = len(data)
    return -sum((v / n) * math.log2(v / n) for v in c.values())


def _printable_ratio(data: bytes) -> float:
    if not data:
        return 0.0
    ok = sum(1 for b in data if 32 <= b < 127 or b in (9, 10, 13))
    return ok / len(data)


def fragment_scores(block: bytes) -> List[Tuple[str, float, str]]:
    """Punteggi (tipo, confidenza 0-1, motivo) per un blocco di byte."""
    out: List[Tuple[str, float, str]] = []
    if len(block) < 512:
        return out
    head = block[:64]
    ent = _entropy(block[:8192])
    pr = _printable_ratio(block[:4096])

    def add(kind, conf, why):
        out.append((kind, min(0.99, conf), why))

    if block[:3] == b"\xFF\xD8\xFF":
        add("JPEG", 0.99, "header JPEG")
    if block[:8] == b"\x89PNG\r\n\x1a\n":
        add("PNG", 0.99, "header PNG")
    if block[:4] == b"%PDF":
        add("PDF", 0.97, "header PDF")
    if b"SQLite format 3\x00" in head:
        add("SQLITE", 0.99, "magic SQLite")
    if b"Rar!\x1a\x07" in head:
        add("RAR", 0.97, "magic RAR")
    if b"7z\xbc\xaf\x27\x1c" in head:
        add("7Z", 0.97, "magic 7-Zip")
    if head[:2] == b"MZ":
        add("EXE", 0.9, "header MZ")
    if b"\x1a\x45\xdf\xa3" in head:
        add("MKV", 0.9, "magic Matroska")
    if b"ftyp" in head:
        add("MP4", 0.9, "box ftyp")
    if head[:4] == b"ID3":
        add("MP3", 0.9, "tag ID3")
    if head[:4] == b"RIFF":
        if b"WAVE" in head:
            add("WAV", 0.92, "RIFF/WAVE")
        elif b"AVI " in head:
            add("AVI", 0.92, "RIFF/AVI")
        elif b"WEBP" in head:
            add("WEBP", 0.92, "RIFF/WEBP")
    if head[:2] == b"BM":
        add("BMP", 0.9, "header BM")
    if head[:4] == b"II*\x00":
        add("TIFF", 0.9, "header TIFF")
    if b"PK\x03\x04" in head:
        fam = "ZIP"
        if b"word/" in block[:8192]:
            fam = "DOCX"
        elif b"xl/" in block[:8192]:
            fam = "XLSX"
        add(fam, 0.88, "local header PK + " + ("word/" if fam == "DOCX" else "xl/" if fam == "XLSX" else "archivio"))
    if head[:4] == b"GIF8":
        add("GIF", 0.95, "header GIF")
    # euristiche senza header
    restarts = sum(1 for i in range(len(block) - 1)
                   if block[i] == 0xFF and 0xD0 <= block[i + 1] <= 0xD7)
    if restarts > 6 and 6.5 < ent < 8.0:
        add("JPEG-frammento", 0.7, f"{restarts} restart marker, H={ent:.1f}")
    syncs = sum(1 for i in range(min(len(block) - 1, 4096))
                if block[i] == 0xFF and (block[i + 1] & 0xE0) == 0xE0)
    if syncs > 8 and 6.0 < ent < 8.0:
        add("MP3-frammento", 0.7, f"{syncs} frame-sync, H={ent:.1f}")
    if pr > 0.85 and ent < 5.5 and not out:
        add("TESTO", 0.6, f"testo {pr*100:.0f}%, H={ent:.1f}")
    if ent > 7.6 and not out:
        add("SCONOSCIUTO-compresso/cifrato", 0.5, f"entropia alta H={ent:.1f}")
    if not out and 4.5 < ent < 7.5:
        add("SCONOSCIUTO-binario", 0.4, f"H={ent:.1f}")
    return sorted(out, key=lambda x: x[1], reverse=True)[:3]


def scan_unknown(source_path: str, blocks: int = 120, block_kb: int = 64,
                 progress=None, stop_flag=None) -> List[dict]:
    """Campiona N blocchi e classifica quelli senza firma nota. Ritorna aggregate."""
    try:
        total = os.path.getsize(source_path)
    except Exception:
        return [{"error": "sorgente non leggibile"}]
    size = block_kb * 1024
    step = max(size, total // blocks) if total else size
    agg: Dict[str, list] = {}
    try:
        fh = open(source_path, "rb")
    except Exception as e:
        return [{"error": str(e)}]
    n = 0
    with fh:
        off = 0
        while n < blocks and off < (total or 10**12):
            if stop_flag and stop_flag.get("stop"):
                break
            try:
                fh.seek(off)
                blk = fh.read(size)
            except Exception:
                break
            if not blk or len(blk) < 512:
                break
            for kind, conf, why in fragment_scores(blk)[:1]:
                e = agg.setdefault(kind, [0, 0.0, why])
                e[0] += 1
                e[1] += conf
            n += 1
            off += step
            if progress and n % 10 == 0:
                progress(n / blocks * 100, f"AI: analizzati {n}/{blocks} blocchi…")
    res = [{"kind": k, "blocks": v[0], "avg_conf": round(v[1] / v[0], 2), "note": v[2]}
           for k, v in sorted(agg.items(), key=lambda x: -x[1][0])]
    if progress:
        progress(100, f"AI: {n} blocchi analizzati, {len(res)} tipi probabili")
    return res


# ---------------------------------------------------------------- ranking
TYPE_VALUE = {"JPEG": 8, "PNG": 8, "PDF": 9, "DOCX": 10, "XLSX": 10,
              "SQLITE": 10, "MP3": 5, "MP4": 6, "MKV": 6, "ZIP": 6,
              "RAR": 6, "7Z": 6, "GIF": 5, "BMP": 5, "TIFF": 7,
              "WEBP": 6, "WAV": 6, "AVI": 6, "EXE": 2}


def rank_files(files: List, kinds_note: Optional[Dict[str, tuple]] = None) -> List[Tuple]:
    """(file, score 0-100, motivo) — per prioritizzare il ripristino."""
    from .recovery import validate_file
    out = []
    for f in files:
        score, notes = 50.0, []
        ok, det = validate_file(f.path, f.kind)
        if ok:
            score += 25
            notes.append("valido")
        else:
            score -= 15
            notes.append(det)
        score += TYPE_VALUE.get(f.kind, 4)
        # plausibilità dimensione
        typical = {"JPEG": (5e3, 30e6), "PNG": (5e3, 30e6), "PDF": (5e3, 80e6),
                   "MP3": (5e4, 50e6), "SQLITE": (8e3, 200e6)}
        if f.kind in typical:
            lo, hi = typical[f.kind]
            if lo <= f.size <= hi:
                score += 8
                notes.append("dimensione plausibile")
            else:
                score -= 8
                notes.append("dimensione anomala")
        if f.size < 512:
            score -= 20
        score = max(1, min(99, round(score)))
        out.append((f, score, "; ".join(notes)))
    return sorted(out, key=lambda x: -x[1])


# ---------------------------------------------------------------- ri-allena
def retrain_from_csv(csv_path: str, dest: str = "") -> dict:
    """Ri-allena la logistica da CSV stile Backblaze (colonne smart_* + failure).
    Ritorna metriche + salva ai_weights.json."""
    import csv
    X, y = [], []
    with open(csv_path, newline="", encoding="utf-8", errors="replace") as f:
        rd = csv.DictReader(f)
        cols = rd.fieldnames or []
        get = lambda r, *names: next((r[c] for c in names if c in r), "")
        for r in rd:
            try:
                feats = {
                    "realloc": _clip(math.log1p(int(float(get(r, "smart_5_raw") or 0))) / math.log1p(50)),
                    "pending": _clip(math.log1p(int(float(get(r, "smart_197_raw") or 0))) / math.log1p(20)),
                    "uncorr": _clip(math.log1p(int(float(get(r, "smart_198_raw") or 0))) / math.log1p(20)),
                    "temp": _clip(((float(get(r, "smart_194_raw") or 40)) - 35) / 25.0),
                    "poh": _clip(math.log1p(int(float(get(r, "smart_9_raw") or 0))) / math.log1p(50000)),
                    "crc": _clip(math.log1p(int(float(get(r, "smart_199_raw") or 0))) / math.log1p(100)),
                    "wear": _clip(float(get(r, "wear_used") or 0)),
                    "cycles": _clip(math.log1p(int(float(get(r, "smart_12_raw") or 0))) / math.log1p(10000)),
                }
                X.append([feats[k] for k in FEATURES])
                y.append(1 if str(get(r, "failure")).strip() in ("1", "True", "true", "YES") else 0)
            except Exception:
                continue
    if len(X) < 20 or sum(y) == 0:
        return {"ok": False, "error": f"dati insufficienti ({len(X)} righe, {sum(y)} guasti)"}
    w = [0.0] * len(FEATURES)
    b = -3.0
    lr = 0.5
    for _ in range(400):
        for xi, yi in zip(X, y):
            p = _sigmoid(b + sum(a * c for a, c in zip(w, xi)))
            err = (p - yi)
            for j in range(len(w)):
                w[j] -= lr * err * xi[j] / len(X)
            b -= lr * err / len(X)
    # accuratezza train
    tp = sum(1 for xi, yi in zip(X, y) if (_sigmoid(b + sum(a * c for a, c in zip(w, xi))) >= 0.5) == yi)
    dest = dest or os.path.join(os.path.dirname(__file__), "ai_weights.json")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump({"intercept": b, "weights": dict(zip(FEATURES, w)),
                   "trained_on": csv_path, "rows": len(X),
                   "failures": sum(y)}, f, indent=1)
    return {"ok": True, "rows": len(X), "failures": sum(y),
            "accuracy": round(tp / len(X) * 100, 1), "dest": dest}
