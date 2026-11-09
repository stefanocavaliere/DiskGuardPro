"""
DiskGuard Pro - core/smart.py (v2.0)
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


def smartctl_available() -> str:
    for c in ["smartctl.exe", "smartctl"]:
        p = shutil.which(c)
        if p:
            return p
    import os
    for p in [r"C:\Program Files\smartmontools\bin\smartctl.exe"]:
        if os.path.exists(p):
            return p
    return ""


def read_smart(device: str) -> Tuple[List[dict], dict]:
    """
    Ritorna (attributi SMART, info).
    attributo: {id, name, value, worst, thresh, raw, status}
    info: {model, serial, temp_c, health, power_on_hours, interface,...}
    """
    exe = smartctl_available()
    if exe and platform.system() == "Windows":
        try:
            m = re.search(r"(\d+)", device)
            dev = f"/dev/pd{m.group(1)}" if m and "Physical" in device else device
            out = subprocess.run([exe, "-a", "-j", dev],
                                 capture_output=True, text=True, timeout=20).stdout
            import json
            j = json.loads(out)
            attrs = []
            for a in j.get("ata_smart_attributes", {}).get("table", []):
                raw = a.get("raw", {})
                raw = raw.get("value", raw) if isinstance(raw, dict) else raw
                attrs.append({
                    "id": a.get("id"), "name": a.get("name"),
                    "value": a.get("value"), "worst": a.get("worst"),
                    "thresh": a.get("thresh"), "raw": raw,
                    "status": "OK" if (a.get("value", 100) or 100) >= (a.get("thresh", 0) or 0) else "FAIL",
                })
            t = j.get("temperature", {}).get("current")
            if t is None:
                t = j.get("nvme_smart_health_information_log", {}).get("temperature")
            info = {
                "model": j.get("model_name", device),
                "serial": j.get("serial_number", "—"),
                "firmware": j.get("firmware_version", ""),
                "temp_c": t,
                "health": "Buono" if j.get("smart_status", {}).get("passed", True) else "Critico",
                "power_on_hours": (j.get("power_on_time") or {}).get("hours"),
                "interface": j.get("device", {}).get("protocol", ""),
            }
            return attrs, info
        except Exception:
            pass

    # Fallback PowerShell
    try:
        from .disks import get_reliability_counters
        c = get_reliability_counters(device)
        if c:
            attrs = [
                {"id": 9, "name": "Power_On_Hours", "value": 100, "worst": 100,
                 "thresh": 0, "raw": c.get("PowerOnHours", "—"), "status": "OK"},
                {"id": 194, "name": "Temperature_Celsius", "value": 100, "worst": 100,
                 "thresh": 0, "raw": c.get("Temperature"), "status": "OK"},
                {"id": 199, "name": "UDMA_CRC_Errors", "value": 100, "worst": 100,
                 "thresh": 0, "raw": 0, "status": "OK"},
            ]
            info = {"model": device, "serial": "—", "temp_c": c.get("Temperature"),
                    "health": "Buono", "power_on_hours": c.get("PowerOnHours"),
                    "wear": c.get("Wear"), "interface": ""}
            return attrs, info
    except Exception:
        pass

    # ---------- DEMO ----------
    base_temp = 37 if ("SSD" in device or "0" in device) else 41
    t = base_temp + random.randint(-1, 6)
    warn = "1" in device  # secondo disco demo = attenzione
    attrs = [
        {"id": 5, "name": "Reallocated_Sector_Ct", "value": 100, "worst": 100, "thresh": 10, "raw": 0, "status": "OK"},
        {"id": 9, "name": "Power_On_Hours", "value": 96, "worst": 96, "thresh": 0, "raw": 8420 if not warn else 31200, "status": "OK"},
        {"id": 12, "name": "Power_Cycle_Count", "value": 99, "worst": 99, "thresh": 0, "raw": 1240, "status": "OK"},
        {"id": 177, "name": "Wear_Leveling_Count", "value": 92, "worst": 92, "thresh": 0, "raw": 38, "status": "OK"},
        {"id": 194, "name": "Temperature_Celsius", "value": 100 - t + 60, "worst": 90, "thresh": 0, "raw": t if not warn else 48, "status": "OK"},
        {"id": 196, "name": "Reallocated_Event_Count", "value": 100, "worst": 100, "thresh": 0, "raw": 0, "status": "OK"},
        {"id": 197, "name": "Current_Pending_Sector", "value": 100, "worst": 100, "thresh": 0,
         "raw": 0 if not warn else 8, "status": "OK" if not warn else "WARN"},
        {"id": 198, "name": "Offline_Uncorrectable", "value": 100, "worst": 100, "thresh": 0, "raw": 0, "status": "OK"},
        {"id": 241, "name": "Total_LBAs_Written", "value": 100, "worst": 100, "thresh": 0, "raw": 18420311, "status": "OK"},
    ]
    info = {"model": device, "serial": "DEMO-0000", "firmware": "5B2QGXA7",
            "temp_c": t if not warn else 48,
            "health": "Buono" if not warn else "Attenzione",
            "power_on_hours": 8420 if not warn else 31200,
            "interface": "NVMe" if not warn else "SATA", "demo": True}
    return attrs, info


def health_score(attrs: List[dict], temp_c) -> Tuple[int, str, str]:
    """0-100, etichetta, chiave colore (green/orange/red)."""
    score = 100
    crit_fail = any(a.get("status") == "FAIL" for a in attrs)
    warn = any(a.get("status") == "WARN" for a in attrs)
    for a in attrs:
        try:
            raw = int(str(a.get("raw", "0")).split()[0])
        except Exception:
            raw = 0
        if a.get("id") == 5 and raw > 0:
            score -= 25
        if a.get("id") in (197, 198) and raw:
            score -= min(20, raw * 2)
    try:
        if temp_c is not None:
            if int(temp_c) > 55:
                score -= 15
            elif int(temp_c) > 50:
                score -= 5
    except Exception:
        pass
    if crit_fail:
        return max(5, score - 40), "Critico", "red"
    if warn or score < 90:
        return max(10, score), "Attenzione", "orange"
    return max(80, score), "Buono", "green"
