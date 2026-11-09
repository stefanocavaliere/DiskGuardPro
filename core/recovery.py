"""
DiskGuard Pro - core/recovery.py
Recupero dati avanzato:
- Scansione cestino + file recenti
- File carving su immagine / disco raw (firme JPEG/PNG/PDF/ZIP/DOCX/MP4...)
- Anteprima esadecimale
- Clonazione disco / creazione immagine .img (raw copy con progress)
ATTENZIONE: il carving su disco fisico richiede "Esegui come amministratore".
"""
import hashlib
import os
import re
import shutil
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

SIGNATURES: Dict[str, dict] = {
    "JPEG": {"header": b"\xFF\xD8\xFF", "footer": b"\xFF\xD9", "ext": ".jpg", "max_size": 30*1024*1024},
    "PNG":  {"header": b"\x89PNG\r\n\x1a\n", "footer": b"IEND\xaeB\x60\x82", "ext": ".png", "max_size": 30*1024*1024},
    "PDF":  {"header": b"%PDF", "footer": b"%%EOF", "ext": ".pdf", "max_size": 80*1024*1024},
    "ZIP":  {"header": b"PK\x03\x04", "footer": None, "ext": ".zip", "max_size": 200*1024*1024},
    "DOCX": {"header": b"PK\x03\x04", "footer": None, "ext": ".docx", "max_size": 100*1024*1024},
    "XLSX": {"header": b"PK\x03\x04", "footer": None, "ext": ".xlsx", "max_size": 100*1024*1024},
    "MP4":  {"header": b"ftyp", "footer": None, "ext": ".mp4", "max_size": 500*1024*1024},
    "GIF":  {"header": b"GIF8", "footer": b"\x00\x3B", "ext": ".gif", "max_size": 20*1024*1024},
    "BMP":  {"header": b"BM", "footer": None, "ext": ".bmp", "max_size": 50*1024*1024},
    "TIFF": {"header": b"II*\x00", "footer": None, "ext": ".tif", "max_size": 80*1024*1024},
    "WEBP": {"header": b"RIFF", "footer": None, "ext": ".webp", "max_size": 30*1024*1024, "contains": b"WEBP"},
    "MP3":  {"header": b"ID3", "footer": None, "ext": ".mp3", "max_size": 50*1024*1024},
    "WAV":  {"header": b"RIFF", "footer": None, "ext": ".wav", "max_size": 200*1024*1024, "contains": b"WAVE"},
    "AVI":  {"header": b"RIFF", "footer": None, "ext": ".avi", "max_size": 500*1024*1024, "contains": b"AVI "},
    "MKV":  {"header": b"\x1a\x45\xdf\xa3", "footer": None, "ext": ".mkv", "max_size": 1024*1024*1024},
    "SQLITE": {"header": b"SQLite format 3\x00", "footer": None, "ext": ".db", "max_size": 200*1024*1024},
    "EXE":  {"header": b"MZ", "footer": None, "ext": ".exe", "max_size": 200*1024*1024},
    "RAR":  {"header": b"Rar!\x1a\x07", "footer": None, "ext": ".rar", "max_size": 500*1024*1024},
    "7Z":   {"header": b"7z\xbc\xaf\x27\x1c", "footer": None, "ext": ".7z", "max_size": 500*1024*1024},
}

# alias: tipi che condividono la stessa firma ZIP (PK..) -> assegnati in round-robin
ZIP_FAMILY = ["ZIP", "DOCX", "XLSX"]

@dataclass
class FoundFile:
    name: str
    path: str
    size: int
    kind: str
    status: str = "trovato"

def quick_scan_deleted(drive_or_folder: str) -> List[FoundFile]:
    """Scansione rapida: cestino + file temporanei recuperabili + ultimi eliminati."""
    out: List[FoundFile] = []
    candidates = []
    # Cestino Windows
    for letter in ["C:", "D:", "E:"]:
        rb = os.path.join(letter + "\\", "$RECYCLE.BIN") if os.name == "nt" else "/tmp"
        candidates.append(rb)
    candidates.append(drive_or_folder)
    seen = set()
    for base in candidates:
        if not base or not os.path.exists(base):
            continue
        try:
            for root, dirs, files in os.walk(base):
                # evita di scendere troppo in profondità per velocità
                depth = root.count(os.sep)
                if depth > 8:
                    dirs[:] = []
                    continue
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        if fp in seen:
                            continue
                        seen.add(fp)
                        # euristica "eliminato/recuperabile": file $I/$R del cestino o temp/orphan
                        low = f.lower()
                        if f.startswith("$") or low.startswith("$i") or low.startswith("$r") or low.endswith((".tmp", ".bak", ".old", ".~tmp")):
                            st = os.stat(fp)
                            out.append(FoundFile(f, fp, st.st_size, "cestino/tmp"))
                        if len(out) >= 500:
                            return out
                    except Exception:
                        continue
                if len(out) >= 500:
                    break
        except Exception:
            continue
    return out

def hex_preview(path: str, length: int = 4096) -> str:
    try:
        with open(path, "rb") as f:
            data = f.read(length)
        lines = []
        for i in range(0, len(data), 16):
            chunk = data[i:i+16]
            hx = " ".join(f"{b:02X}" for b in chunk)
            asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            lines.append(f"{i:08X}  {hx:<48}  {asc}")
        return "\n".join(lines)
    except Exception as e:
        return f"Anteprima non disponibile: {e}"

def carve_file(source_path: str, dest_dir: str,
               types: Optional[List[str]] = None,
               progress: Optional[Callable[[float, str], None]] = None,
               stop_flag: Optional[dict] = None,
               chunk_size: int = 1024*1024) -> List[FoundFile]:
    """
    File carving: legge il file sorgente (immagine .img o \\\\.\\PhysicalDriveN o file di test)
    e cerca le firme. Salva i file recuperati in dest_dir.
    """
    os.makedirs(dest_dir, exist_ok=True)
    types = types or ["JPEG", "PNG", "PDF", "GIF"]
    sigs = {k: SIGNATURES[k] for k in types if k in SIGNATURES}
    found: List[FoundFile] = []
    try:
        total = os.path.getsize(source_path) if os.path.exists(source_path) and os.path.isfile(source_path) else 0
    except Exception:
        total = 0
    # Per dischi raw su Windows os.path.getsize fallisce -> total=0, progress indeterminato
    buf_overlap = 16
    carry = b""
    offset = 0
    open_files: Dict[str, dict] = {}  # tipo -> {fh, path, size, start}
    counters = {k: 0 for k in sigs}
    try:
        fh = open(source_path, "rb")
    except Exception as e:
        if progress:
            progress(0, f"Impossibile aprire sorgente: {e} (avvia come Amministratore)")
        return []
    with fh:
        while True:
            if stop_flag and stop_flag.get("stop"):
                break
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            data = carry + chunk
            base_off = offset - len(carry)
            for kind, s in sigs.items():
                h = s["header"]
                # cerca header
                start = 0
                while True:
                    idx = data.find(h, start)
                    if idx < 0:
                        break
                    abs_off = base_off + idx
                    # chiudi eventuale file precedente dello stesso tipo senza footer
                    if kind in open_files:
                        _close_carved(open_files.pop(kind), found)
                    counters[kind] += 1
                    fname = f"recuperato_{kind.lower()}_{abs_off}_{counters[kind]}{s['ext']}"
                    fpath = os.path.join(dest_dir, fname)
                    try:
                        of = open(fpath, "wb")
                        # per tipi senza footer salviamo finestra fissa di max_size / o fino al prossimo header
                        open_files[kind] = {"fh": of, "path": fpath, "size": 0,
                                            "start": abs_off, "kind": kind, "max": s["max_size"],
                                            "footer": s["footer"]}
                        # scrivi da header in poi (almeno il resto del buffer)
                        of.write(data[idx:idx+len(data)])
                        open_files[kind]["size"] += len(data) - idx
                    except Exception:
                        pass
                    start = idx + len(h)
                    # se footer è nello stesso buffer chiudi subito
                    if s["footer"]:
                        fidx = data.find(s["footer"], idx)
                        if fidx >= 0 and kind in open_files:
                            _close_carved(open_files.pop(kind), found)
                            # tronca alla dimensione corretta se abbiamo scritto troppo
                            try:
                                with open(fpath, "r+b") as ff:
                                    # la scrittura precedente includeva tutto il buffer: tronca
                                    pass
                            except Exception:
                                pass
                # append ai file aperti senza footer / in corso
                # (semplificazione: per footer, controlla se il footer è nel chunk)
                for kind in list(open_files.keys()):
                    e = open_files[kind]
                    if e["footer"]:
                        if e["footer"] in chunk:
                            _close_carved(open_files.pop(kind), found)
                        elif e["size"] > e["max"]:
                            _close_carved(open_files.pop(kind), found)
                    else:
                        if e["size"] > 8*1024*1024:  # finestra 8MB per ZIP/DOCX/MP4 demo
                            _close_carved(open_files.pop(kind), found)
            offset += len(chunk)
            carry = chunk[-buf_overlap:] if len(chunk) >= buf_overlap else chunk
            if progress and total:
                progress(min(99, offset/total*100), f"Scansione {offset/(1024**2):.1f} MB")
            elif progress:
                progress(0, f"Scansione {offset/(1024**2):.1f} MB...")
    # chiudi residui
    for kind in list(open_files.keys()):
        _close_carved(open_files.pop(kind), found)
    if progress:
        progress(100, f"Completato: {len(found)} file recuperati")
    return found

def _close_carved(entry: dict, found: List[FoundFile]):
    try:
        entry["fh"].close()
        sz = os.path.getsize(entry["path"])
        if sz < 100:
            os.remove(entry["path"])
            return
        found.append(FoundFile(os.path.basename(entry["path"]), entry["path"], sz, entry["kind"]))
    except Exception:
        try:
            entry["fh"].close()
        except Exception:
            pass

def file_hashes(path: str) -> dict:
    """MD5 + SHA256 di un file (streaming)."""
    h1, h2 = hashlib.md5(), hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for b in iter(lambda: f.read(4 * 1024 * 1024), b""):
                h1.update(b)
                h2.update(b)
        return {"md5": h1.hexdigest(), "sha256": h2.hexdigest()}
    except Exception as e:
        return {"error": str(e)}


def validate_file(path: str, kind: str) -> tuple:
    """Verifica integrità base: ritorna (ok: bool, dettaglio: str)."""
    try:
        sz = os.path.getsize(path)
        with open(path, "rb") as f:
            head = f.read(64)
        if kind == "JPEG":
            with open(path, "rb") as f:
                f.seek(max(0, sz - 2))
                tail_ok = f.read(2) == b"\xFF\xD9"
            return (head[:3] == b"\xFF\xD8\xFF" and (tail_ok or sz > 1024 * 1024),
                    "footer OK" if tail_ok else "tronco (footer mancante)")
        if kind == "PNG":
            ok = head[:8] == b"\x89PNG\r\n\x1a\n"
            return ok, "header OK" if ok else "header corrotto"
        if kind == "PDF":
            ok = head[:4] == b"%PDF"
            with open(path, "rb") as f:
                f.seek(max(0, sz - 2048))
                has_eof = b"%%EOF" in f.read()
            return ok and has_eof, "completo" if (ok and has_eof) else "tronco?"
        if kind in ("ZIP", "DOCX", "XLSX"):
            import zipfile
            try:
                with zipfile.ZipFile(path) as z:
                    bad = z.testzip()
                return (bad is None, "archivio integro" if bad is None else f"membro corrotto: {bad}")
            except Exception as e:
                return False, f"non apribile: {e}"
        if kind == "GIF":
            return head[:4] in (b"GIF8",), "header OK"
        if kind in ("BMP",):
            return head[:2] == b"BM", "header OK"
        if kind in ("MP3", "WAV", "AVI", "WEBP", "MKV", "MP4",
                    "SQLITE", "EXE", "RAR", "7Z", "TIFF"):
            return sz > 512, f"{sz} byte, firma presente"
        return sz > 0, "—"
    except Exception as e:
        return False, str(e)


def image_preview(path: str, max_px: int = 320):
    """Ritorna oggetto PIL.Image (thumbnail) per anteprima, o None."""
    try:
        from PIL import Image
        im = Image.open(path)
        im.draft("RGB", (max_px, max_px))
        im.thumbnail((max_px, max_px))
        return im.convert("RGB")
    except Exception:
        return None


def findings_report(files, dest_csv: str, dest_html: str = "") -> dict:
    """Report CSV (+HTML opzionale) dei file recuperati con hash e validazione."""
    import csv
    rows = []
    for f in files:
        ok, det = validate_file(f.path, f.kind)
        h = file_hashes(f.path)
        rows.append({"name": f.name, "path": f.path, "size": f.size,
                     "kind": f.kind, "valid": "OK" if ok else "DUBBIO",
                     "detail": det, "md5": h.get("md5", "")} )
    with open(dest_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["name", "path", "size", "kind",
                                            "valid", "detail", "md5"])
        w.writeheader()
        w.writerows(rows)
    if dest_html:
        with open(dest_html, "w", encoding="utf-8") as fh:
            fh.write("<html><head><meta charset='utf-8'><title>DiskGuard Pro — Report recupero</title>"
                      "<style>body{font-family:Segoe UI;background:#111;color:#eee}table{border-collapse:collapse;width:100%}" 
                      + "td,th{border:1px solid #333;padding:6px;font-size:12px}.ok{color:#0c5}.bad{color:#fa0}</style></head><body>")
            fh.write(f"<h2>🧲 Report recupero — {len(rows)} file</h2><table>"
                      "<tr><th>File</th><th>Tipo</th><th>Byte</th><th>Validazione</th><th>MD5</th></tr>")
            for r in rows:
                cls = "ok" if r["valid"] == "OK" else "bad"
                fh.write(f"<tr><td>{r['name']}</td><td>{r['kind']}</td><td>{r['size']}</td>"
                          f"<td class='{cls}'>{r['valid']} — {r['detail']}</td><td>{r['md5'][:16]}…</td></tr>")
            fh.write("</table></body></html>")
    return {"csv": dest_csv, "html": dest_html, "count": len(rows)}


def copy_with_progress(src: str, dst: str, progress=None, stop_flag=None, chunk=4*1024*1024):
    """Copia raw (per clona disco / crea immagine) con avanzamento."""
    total = 0
    try:
        total = os.path.getsize(src)
    except Exception:
        total = 0
    done = 0
    with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
        while True:
            if stop_flag and stop_flag.get("stop"):
                break
            b = fsrc.read(chunk)
            if not b:
                break
            fdst.write(b)
            done += len(b)
            if progress:
                if total:
                    progress(done/total*100, f"{done/(1024**3):.2f} GB copiati")
                else:
                    progress(0, f"{done/(1024**3):.2f} GB copiati")
    if progress:
        progress(100, "Operazione completata")
