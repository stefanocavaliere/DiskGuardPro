"""
DiskGuard Pro - core/analysis.py (v3.0)
Analisi disco avanzata:
- Layout partizioni (GPT/MBR) via PowerShell Get-Disk/Get-Partition/Get-Volume
- Surface scan (mappa blocchi ok/lenti/danneggiati) su file .img o disco raw
- Analisi uso disco (cartelle, file più grandi, per estensione)
- Test latenza I/O random 4K
- Shadow copies (VSS) + info filesystem
Tutto con fallback demo su non-Windows / senza permessi.
"""
import json
import os
import platform
import random
import subprocess
import time
from typing import Callable, Dict, List, Optional


def _run_ps(cmd: str, timeout: int = 20) -> str:
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                       capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()


# ---------------- layout partizioni ----------------
def get_layout() -> dict:
    """Ritorna {disks, partitions, volumes}. Demo se non disponibile."""
    out = {"disks": [], "partitions": [], "volumes": [], "demo": False}
    try:
        if platform.system() != "Windows":
            raise OSError("non-windows")
        disks = json.loads(_run_ps(
            "Get-Disk | Select-Object Number,FriendlyName,PartitionStyle,Size,"
            "OperationalStatus,HealthStatus,BusType | ConvertTo-Json") or "null")
        parts = json.loads(_run_ps(
            "Get-Partition | Select-Object DiskNumber,PartitionNumber,DriveLetter,"
            "Size,Type,GptType,IsActive | ConvertTo-Json") or "null")
        vols = json.loads(_run_ps(
            "Get-Volume | Select-Object DriveLetter,FileSystem,Size,SizeRemaining,"
            "HealthStatus,OperationalStatus | ConvertTo-Json") or "null")
        for key, val in (("disks", disks), ("partitions", parts), ("volumes", vols)):
            if val is None:
                continue
            if isinstance(val, dict):
                val = [val]
            out[key] = val or []
        if not out["disks"]:
            raise ValueError("vuoto")
        return out
    except Exception:
        pass
    # DEMO
    out.update({
        "demo": True,
        "disks": [
            {"Number": 0, "FriendlyName": "Samsung 980 PRO 1TB",
             "PartitionStyle": "GPT", "Size": 1000204886016,
             "OperationalStatus": "Online", "HealthStatus": "Healthy", "BusType": "NVMe"},
            {"Number": 1, "FriendlyName": "Seagate BarraCuda 2TB",
             "PartitionStyle": "GPT", "Size": 2000398934016,
             "OperationalStatus": "Online", "HealthStatus": "Warning", "BusType": "SATA"},
        ],
        "partitions": [
            {"DiskNumber": 0, "PartitionNumber": 1, "DriveLetter": "",
             "Size": 536870912, "Type": "System", "GptType": "{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}", "IsActive": False},
            {"DiskNumber": 0, "PartitionNumber": 3, "DriveLetter": "C",
             "Size": 999000000000, "Type": "Basic", "GptType": "{ebd0a0a2-b9e5-4433-87c0-68b6b72699c7}", "IsActive": False},
            {"DiskNumber": 1, "PartitionNumber": 1, "DriveLetter": "D",
             "Size": 2000300000000, "Type": "Basic", "GptType": "{ebd0a0a2-b9e5-4433-87c0-68b6b72699c7}", "IsActive": False},
        ],
        "volumes": [
            {"DriveLetter": "C", "FileSystem": "NTFS", "Size": 999000000000,
             "SizeRemaining": 342000000000, "HealthStatus": "Healthy", "OperationalStatus": "OK"},
            {"DriveLetter": "D", "FileSystem": "NTFS", "Size": 2000300000000,
             "SizeRemaining": 497000000000, "HealthStatus": "Healthy", "OperationalStatus": "OK"},
        ],
    })
    return out


# ---------------- surface scan ----------------
def surface_scan(source_path: str, block_mb: int = 2,
                 progress: Optional[Callable[[float, str], None]] = None,
                 stop_flag: Optional[dict] = None,
                 slow_ms: float = 80.0,
                 max_blocks: int = 2500) -> dict:
    """
    Legge la sorgente a blocchi e misura il tempo di lettura.
    Ritorna {blocks: [(offset_mb, status, ms)], bad, slow, ok, avg_mbs, total_mb}.
    status: ok / slow / bad. max_blocks limita la mappa (campiona oltre).
    """
    import math
    try:
        total = os.path.getsize(source_path)
    except Exception:
        total = 0
    block = block_mb * 1024 * 1024
    blocks: List[tuple] = []
    bad = slow = ok = 0
    done = 0
    t_all = 0.0
    n = 0
    step = 1
    if total and total / block > max_blocks:
        step = math.ceil((total / block) / max_blocks)
    try:
        fh = open(source_path, "rb")
    except Exception as e:
        if progress:
            progress(0, f"Impossibile aprire: {e} (prova come Amministratore)")
        return {"blocks": [], "bad": 0, "slow": 0, "ok": 0, "avg_mbs": 0,
                "total_mb": 0, "error": str(e)}
    idx = 0
    with fh:
        while True:
            if stop_flag and stop_flag.get("stop"):
                break
            t0 = time.perf_counter()
            try:
                fh.seek(idx * block)
                data = fh.read(block)
            except Exception:
                data = b""
                blocks.append((idx * block_mb, "bad", 9999.0))
                bad += 1
                idx += step
                continue
            if not data:
                break
            dt = (time.perf_counter() - t0) * 1000
            # campionamento: salta lettura ma registra
            if step > 1 and (idx % step != 0):
                idx += 1
                done += len(data)
                continue
            ms = dt
            n += 1
            t_all += dt / 1000
            done += len(data)
            if len(data) < block and total and done < total:
                pass
            if dt > 2000:
                st = "bad"
                bad += 1
            elif dt > slow_ms:
                st = "slow"
                slow += 1
            else:
                st = "ok"
                ok += 1
            blocks.append((idx * block_mb, st, round(dt, 1)))
            idx += 1
            if step > 1:
                idx = (idx // step) * step
                # avanza comunque: seek al prossimo campionato
                continue
            if progress and total:
                progress(min(99, done / total * 100),
                         f"Blocco {idx}: {done/(1024**2):.0f} MB — ok={ok} lenti={slow} bad={bad}")
            elif progress and idx % 10 == 0:
                progress(0, f"Blocco {idx} — ok={ok} lenti={slow} bad={bad}")
    avg = (done / (1024 ** 2) / t_all) if t_all > 0 else 0
    if progress:
        progress(100, f"Completato: {ok} ok, {slow} lenti, {bad} illeggibili — {avg:.0f} MB/s medi")
    return {"blocks": blocks, "bad": bad, "slow": slow, "ok": ok,
            "avg_mbs": round(avg, 1), "total_mb": round(done / (1024 ** 2), 1)}


# ---------------- uso disco ----------------
def disk_usage(folder: str, max_entries: int = 20000,
               progress: Optional[Callable[[float, str], None]] = None,
               stop_flag: Optional[dict] = None) -> dict:
    """Analizza cartella: totale, file, per estensione, top file più grandi."""
    total_size = 0
    total_files = 0
    total_dirs = 0
    by_ext: Dict[str, list] = {}
    largest: List[tuple] = []
    try:
        for root, dirs, files in os.walk(folder):
            if stop_flag and stop_flag.get("stop"):
                break
            total_dirs += 1
            for fn in files:
                if stop_flag and stop_flag.get("stop"):
                    break
                if total_files >= max_entries:
                    break
                fp = os.path.join(root, fn)
                try:
                    sz = os.path.getsize(fp)
                except Exception:
                    continue
                total_size += sz
                total_files += 1
                ext = os.path.splitext(fn)[1].lower() or "(nessuna)"
                e = by_ext.setdefault(ext, [0, 0])
                e[0] += 1
                e[1] += sz
                if len(largest) < 100 or sz > largest[-1][1]:
                    largest.append((fp, sz))
                    largest.sort(key=lambda x: x[1], reverse=True)
                    largest = largest[:100]
                if progress and total_files % 2000 == 0:
                    progress(0, f"Analizzati {total_files} file…")
            if total_files >= max_entries:
                break
    except Exception as e:
        return {"error": str(e)}
    by_ext_list = sorted(((k, v[0], v[1]) for k, v in by_ext.items()),
                         key=lambda x: x[2], reverse=True)[:30]
    if progress:
        progress(100, f"Completato: {total_files} file")
    return {"folder": folder, "total_size": total_size, "total_files": total_files,
            "total_dirs": total_dirs, "by_ext": by_ext_list, "largest": largest[:30]}


# ---------------- latenza I/O ----------------
def io_latency_test(folder: str, samples: int = 200) -> dict:
    """Letture random 4K su file temporaneo: latenza media/max + IOPS stimati."""
    import tempfile
    path = os.path.join(folder, ".diskguard_iotest.bin")
    size = 32 * 1024 * 1024
    try:
        with open(path, "wb") as f:
            f.write(os.urandom(size))
        import random as _r
        lats = []
        with open(path, "rb") as f:
            for _ in range(samples):
                off = _r.randrange(0, size - 4096)
                t0 = time.perf_counter()
                f.seek(off)
                f.read(4096)
                lats.append((time.perf_counter() - t0) * 1000)
        lats.sort()
        avg = sum(lats) / len(lats)
        p95 = lats[int(len(lats) * 0.95)]
        mx = lats[-1]
        iops = 1000 / avg if avg > 0 else 0
        giudizio = "Ottimo (SSD/NVMe)" if avg < 0.3 else (
            "Buono" if avg < 1.5 else ("Mediocre — disco sotto carico o HDD" if avg < 8 else "Critico — disco degradato?"))
        return {"avg_ms": round(avg, 3), "p95_ms": round(p95, 3),
                "max_ms": round(mx, 2), "iops": int(iops), "giudizio": giudizio, "ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass


# ---------------- shadow copies / filesystem ----------------
def get_shadow_copies() -> List[dict]:
    """Elenca copie shadow VSS (punti di ripristino) su Windows."""
    out: List[dict] = []
    try:
        if platform.system() != "Windows":
            return [{"Volume": "C:", "InstallDate": "DEMO",
                     "Device": r"\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy3",
                     "demo": True}]
        raw = _run_ps("Get-CimInstance Win32_ShadowCopy | Select-Object VolumeName,"
                      "InstallDate,DeviceObject | ConvertTo-Json")
        if not raw:
            return []
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        for s in data:
            out.append({"Volume": s.get("VolumeName"), "InstallDate": s.get("InstallDate"),
                        "Device": s.get("DeviceObject")})
    except Exception:
        pass
    return out


def filesystem_info(mount: str) -> dict:
    try:
        import psutil
        u = psutil.disk_usage(mount)
        return {"mount": mount, "total_gb": round(u.total / 1024**3, 1),
                "used_gb": round(u.used / 1024**3, 1),
                "free_gb": round(u.free / 1024**3, 1),
                "pct": u.percent}
    except Exception as e:
        return {"error": str(e)}
