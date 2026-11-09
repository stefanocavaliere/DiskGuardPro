"""
DiskGuard Pro - core/disks.py
Rilevamento dischi fisici e logici su Windows 11.
Usa: PowerShell (Get-PhysicalDisk), WMI, psutil. Fallback demo se non admin / non Windows.
"""
import json
import subprocess
import shutil
import platform
from dataclasses import dataclass, asdict
from typing import List

@dataclass
class DiskInfo:
    device_id: str          # es. PhysicalDrive0 oppure C:
    friendly_name: str
    media_type: str         # SSD / HDD / NVMe / Sconosciuto
    bus_type: str           # NVMe / SATA / USB...
    size_gb: float
    used_gb: float = 0
    free_gb: float = 0
    mount: str = ""
    filesystem: str = ""
    health_status: str = "Sconosciuto"
    operational_status: str = ""

def _run_ps(cmd: str, timeout=15) -> str:
    full = ["powershell", "-NoProfile", "-Command", cmd]
    r = subprocess.run(full, capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()

def get_physical_disks() -> List[DiskInfo]:
    disks: List[DiskInfo] = []
    try:
        if platform.system() != "Windows":
            raise OSError("non-windows")
        ps_cmd = (
            "Get-PhysicalDisk | Select-Object DeviceId,FriendlyName,MediaType,BusType,"
            "HealthStatus,OperationalStatus,Size | ConvertTo-Json"
        )
        out = _run_ps(ps_cmd)
        if not out:
            raise ValueError("ps vuoto")
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        for d in data:
            size_gb = round(float(d.get("Size", 0)) / (1024**3), 1) if d.get("Size") else 0
            disks.append(DiskInfo(
                device_id=f"PhysicalDrive{d.get('DeviceId')}",
                friendly_name=str(d.get("FriendlyName", "Disco")),
                media_type=str(d.get("MediaType", "Sconosciuto")),
                bus_type=str(d.get("BusType", "Sconosciuto")),
                size_gb=size_gb,
                health_status=str(d.get("HealthStatus", "Sconosciuto")),
                operational_status=str(d.get("OperationalStatus", "")),
            ))
    except Exception:
        pass

    # Arricchisci con lettere / spazio via psutil
    try:
        import psutil
        parts = psutil.disk_partitions(all=False)
        # mappa semplice: assegna C: al primo disco fisico se esiste
        for i, p in enumerate(parts):
            try:
                u = psutil.disk_usage(p.mountpoint)
                entry = DiskInfo(
                    device_id=p.device,
                    friendly_name=p.device,
                    media_type="Logico",
                    bus_type="",
                    size_gb=round(u.total/(1024**3),1),
                    used_gb=round(u.used/(1024**3),1),
                    free_gb=round(u.free/(1024**3),1),
                    mount=p.mountpoint,
                    filesystem=p.fstype,
                    health_status="OK" if disks else "Sconosciuto",
                )
                disks.append(entry)
            except Exception:
                continue
    except Exception:
        pass

    if not disks:
        # DEMO MODE (per test su Linux / senza permessi)
        disks = [
            DiskInfo("PhysicalDrive0", "Samsung 980 PRO 1TB (NVMe)", "SSD", "NVMe", 931.5, 612.3, 319.2, "C:", "NTFS", "Healthy", "OK"),
            DiskInfo("PhysicalDrive1", "Seagate Barracuda 2TB (HDD)", "HDD", "SATA", 1863.0, 1400.0, 463.0, "D:", "NTFS", "Warning", "OK"),
            DiskInfo("C:", "C:", "Logico", "", 931.5, 612.3, 319.2, "C:", "NTFS", "Healthy"),
        ]
    return disks

def get_reliability_counters(device_id: str = "") -> dict:
    """Get-StorageReliabilityCounter per un disco fisico."""
    try:
        if platform.system() != "Windows":
            return {}
        # device_id come PhysicalDrive0 -> numero
        import re
        m = re.search(r"(\d+)", device_id)
        num = m.group(1) if m else "0"
        ps = (
            f"Get-PhysicalDisk | Where-Object {{$_.DeviceId -eq {num}}} | "
            "Get-StorageReliabilityCounter | Select-Object Temperature,TemperatureMax,"
            "Wear,PowerOnHours,ReadErrorsTotal,WriteErrorsTotal | ConvertTo-Json"
        )
        out = _run_ps(ps)
        if out:
            return json.loads(out)
    except Exception:
        pass
    return {}
