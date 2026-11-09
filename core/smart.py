"""
DiskGuard Pro - core/smart.py
Lettura SMART + temperatura. Priorità:
1) smartctl.exe (smartmontools) -> dati reali completi
2) PowerShell Get-StorageReliabilityCounter -> temperatura reale
3) Demo realistica
"""
import subprocess
import shutil
import re
import random
import platform
from typing import Dict, List, Tuple

SMART_ATTRS_INTEREST = [5, 9, 12, 194, 196, 197, 198, 177, 233, 241, 242, 170, 173, 174]

def smartctl_available() -> str:
    for c in ["smartctl.exe", "smartctl"]:
        p = shutil.which(c)
        if p:
            return p
    # percorso comune smartmontools
    import os
    for p in [r"C:\Program Files\smartmontools\bin\smartctl.exe"]:
        if os.path.exists(p):
            return p
    return ""

def read_smart(device: str) -> Tuple[List[dict], dict]:
    """
    Ritorna (attributi SMART, info generali).
    attributo: {id, name, value, worst, thresh, raw, status}
    info: {model, serial, temp_c, health, power_on_hours, ...}
    """
    exe = smartctl_available()
    if exe and platform.system() == "Windows":
        try:
            # PhysicalDrive0 -> /dev/pd0
            m = re.search(r"(\d+)", device)
            dev = f"/dev/pd{m.group(1)}" if m and "Physical" in device else device
            out = subprocess.run([exe, "-a", "-j", dev],
                                 capture_output=True, text=True, timeout=20).stdout
            import json
            j = json.loads(out)
            attrs = []
            for a in j.get("ata_smart_attributes", {}).get("table", []):
                attrs.append({
                    "id": a.get("id"), "name": a.get("name"),
                    "value": a.get("value"), "worst": a.get("worst"),
                    "thresh": a.get("thresh"), "raw": a.get("raw", {}).get("value", a.get("raw", {})),
                    "status": "OK" if a.get("value", 100) >= a.get("thresh", 0) else "FAIL",
                })
            temp = None
            for k in ["temperature", "nvme_smart_health_information_log"]:
                pass
            t = j.get("temperature", {}).get("current")
            if t is None:
                t = j.get("nvme_smart_health_information_log", {}).get("temperature")
            info = {
                "model": j.get("model_name", device),
                "serial": j.get("serial_number", "—"),
                "temp_c": t,
                "health": "PASS" if j.get("smart_status", {}).get("passed", True) else "FAIL",
                "power_on_hours": j.get("power_on_time", {}).get("hours"),
                "raw_json": True,
            }
            return attrs, info
        except Exception:
            pass

    # Fallback PowerShell temperatura
    try:
        from .disks import get_reliability_counters
        c = get_reliability_counters(device)
        if c:
            temp = c.get("Temperature")
            # TemperatureMax a volte assente
            attrs = [
                {"id": 9, "name": "Power_On_Hours", "value": 100, "worst": 100, "thresh": 0, "raw": c.get("PowerOnHours", "—"), "status": "OK"},
                {"id": 194, "name": "Temperature_Celsius", "value": 100, "worst": 100, "thresh": 0, "raw": temp, "status": "OK"},
                {"id": 199, "name": "UDMA_CRC_Errors", "value": 100, "worst": 100, "thresh": 0, "raw": 0, "status": "OK"},
            ]
            info = {"model": device, "serial": "—", "temp_c": temp,
                    "health": "Healthy", "power_on_hours": c.get("PowerOnHours"), "wear": c.get("Wear")}
            return attrs, info
    except Exception:
        pass

    # DEMO
    base_temp = 38 if "SSD" in device or "0" in device else 41
    t = base_temp + random.randint(-2, 6)
    attrs = [
        {"id": 5, "name": "Reallocated_Sector_Ct", "value": 100, "worst": 100, "thresh": 10, "raw": 0, "status": "OK"},
        {"id": 9, "name": "Power_On_Hours", "value": 96, "worst": 96, "thresh": 0, "raw": 8420, "status": "OK"},
        {"id": 12, "name": "Power_Cycle_Count", "value": 99, "worst": 99, "thresh": 0, "raw": 1240, "status": "OK"},
        {"id": 177, "name": "Wear_Leveling_Count", "value": 92, "worst": 92, "thresh": 0, "raw": 38, "status": "OK"},
        {"id": 194, "name": "Temperature_Celsius", "value": 100-t+60, "worst": 90, "thresh": 0, "raw": t, "status": "OK"},
        {"id": 196, "name": "Reallocated_Event_Count", "value": 100, "worst": 100, "thresh": 0, "raw": 0, "status": "OK"},
        {"id": 197, "name": "Current_Pending_Sector", "value": 100, "worst": 100, "thresh": 0, "raw": 0, "status": "OK"},
        {"id": 198, "name": "Offline_Uncorrectable", "value": 100, "worst": 100, "thresh": 0, "raw": 0, "status": "OK"},
        {"id": 241, "name": "Total_LBAs_Written", "value": 100, "worst": 100, "thresh": 0, "raw": 18420311, "status": "OK"},
    ]
    # se HDD warning simula un pending sector
    if "1" in device:
        attrs[6]["raw"] = 8
        attrs[6]["status"] = "WARN"
    info = {"model": device, "serial": "DEMO-0000", "temp_c": t,
            "health": "PASS" if "0" in device else "CAUTION",
            "power_on_hours": 8420, "demo": True}
    return attrs, info


def health_score(attrs: List[dict], temp_c) -> Tuple[int, str, str]:
    """0-100, etichetta, colore."""
    score = 100
    crit_fail = any(a["status"] == "FAIL" for a in attrs)
    warn = any(a["status"] == "WARN" for a in attrs)
    for a in attrs:
        if a["id"] == 5 and int(str(a["raw"]).split()[0] or 0) > 0:
            score -= 25
        if a["id"] in (197, 198) and str(a["raw"]) != "0":
            try:
                score -= min(20, int(str(a["raw"])) * 2)
            except Exception:
                score -= 10
    try:
        if temp_c and int(temp_c) > 55:
            score -= 15
        elif temp_c and int(temp_c) > 50:
            score -= 5
    except Exception:
        pass
    if crit_fail:
        return max(5, score - 40), "CRITICO", "red"
    if warn or score < 90:
        return max(10, score), "ATTENZIONE", "orange"
    return max(80, score), "BUONO", "green"
