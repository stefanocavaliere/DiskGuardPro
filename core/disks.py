"""
DiskGuard Pro - core/disks.py (v2.0)
Rilevamento dischi fisici e logici su Windows 11.
Usa: PowerShell (Get-PhysicalDisk), WMI, psutil. Fallback demo se non admin / non Windows.
"""
import json
import subprocess
import platform
from dataclasses import dataclass, field
from typing import List


@dataclass
class DiskInfo:
    device_id: str          # es. PhysicalDrive0 oppure C:
    friendly_name: str
    media_type: str = "Sconosciuto"   # SSD / HDD / NVMe / Sconosciuto / Logico
    bus_type: str = ""                # NVMe / SATA / USB...
    size_gb: float = 0.0
    used_gb: float = 0.0
    free_gb: float = 0.0
    mount: str = ""
    filesystem: str = ""
    health_status: str = "Sconosciuto"
    operational_status: str = ""
    firmware: str = ""
    serial: str = ""
    # volumi logici associati (solo per dischi fisici)
    volumes: list = field(default_factory=list)


def _run_ps(cmd: str, timeout: int = 15) -> str:
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                       capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()


def get_physical_disks() -> List[DiskInfo]:
    disks: List[DiskInfo] = []
    try:
        if platform.system() != "Windows":
            raise OSError("non-windows")
        ps_cmd = (
            "Get-PhysicalDisk | Select-Object DeviceId,FriendlyName,MediaType,BusType,"
            "HealthStatus,OperationalStatus,Size,FirmwareVersion,SerialNumber,"
            "AdapterSerialNumber | ConvertTo-Json"
        )
        out = _run_ps(ps_cmd)
        if not out:
            raise ValueError("ps vuoto")
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        for d in data:
            try:
                size_gb = round(float(d.get("Size", 0)) / (1024 ** 3), 1)
            except Exception:
                size_gb = 0
            disks.append(DiskInfo(
                device_id=f"PhysicalDrive{d.get('DeviceId')}",
                friendly_name=str(d.get("FriendlyName", "Disco") or "Disco"),
                media_type=str(d.get("MediaType", "Sconosciuto") or "Sconosciuto"),
                bus_type=str(d.get("BusType", "") or ""),
                size_gb=size_gb,
                health_status=str(d.get("HealthStatus", "Sconosciuto") or "Sconosciuto"),
                operational_status=str(d.get("OperationalStatus", "") or ""),
                firmware=str(d.get("FirmwareVersion", "") or ""),
                serial=str(d.get("SerialNumber", "") or d.get("AdapterSerialNumber", "") or ""),
            ))
    except Exception:
        pass

    # Volumi logici via psutil
    logicals: List[DiskInfo] = []
    try:
        import psutil
        for p in psutil.disk_partitions(all=False):
            try:
                u = psutil.disk_usage(p.mountpoint)
                logicals.append(DiskInfo(
                    device_id=p.device,
                    friendly_name=p.device,
                    media_type="Logico",
                    size_gb=round(u.total / (1024 ** 3), 1),
                    used_gb=round(u.used / (1024 ** 3), 1),
                    free_gb=round(u.free / (1024 ** 3), 1),
                    mount=p.mountpoint,
                    filesystem=p.fstype,
                    health_status="OK" if disks else "Sconosciuto",
                ))
            except Exception:
                continue
    except Exception:
        pass

    if not disks and not logicals:
        # ---------- DEMO MODE ----------
        disks = [
            DiskInfo("PhysicalDrive0", "Samsung 980 PRO 1TB", "SSD", "NVMe",
                     931.5, 612.3, 319.2, "C:", "NTFS", "Healthy", "OK",
                     firmware="5B2QGXA7", serial="S649NX0R123456"),
            DiskInfo("PhysicalDrive1", "Seagate BarraCuda 2TB", "HDD", "SATA",
                     1863.0, 1400.0, 463.0, "D:", "NTFS", "Warning", "OK",
                     firmware="CC43", serial="WDN123456789"),
        ]
        logicals = [
            DiskInfo("C:", "C:", "Logico", "", 931.5, 612.3, 319.2, "C:", "NTFS", "Healthy"),
            DiskInfo("D:", "D:", "Logico", "", 1863.0, 1400.0, 463.0, "D:", "NTFS", "Healthy"),
        ]

    # associa volumi al primo disco come fallback visivo
    if disks and logicals and not any(d.volumes for d in disks):
        disks[0].volumes = [v for v in logicals]
    return disks + [v for v in logicals if v not in disks[0].volumes] if disks else disks + logicals


def get_reliability_counters(device_id: str = "") -> dict:
    """Get-StorageReliabilityCounter per un disco fisico."""
    try:
        if platform.system() != "Windows":
            return {}
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
