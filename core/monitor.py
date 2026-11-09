"""DiskGuard Pro - monitoraggio temperatura in background + benchmark."""
import csv
import os
import time
import threading
import random
from datetime import datetime

class TempMonitor:
    def __init__(self, get_temp_fn, interval_s=5, log_dir="logs", alert_temp=55, on_alert=None):
        self.get_temp_fn = get_temp_fn
        self.interval = interval_s
        self.log_dir = log_dir
        self.alert_temp = alert_temp
        self.on_alert = on_alert
        self._stop = {"stop": True}
        self._thread = None
        self.history = []  # (time_str, device, temp)
        os.makedirs(log_dir, exist_ok=True)
        self.csv_path = os.path.join(log_dir, f"temp_{datetime.now():%Y%m%d}.csv")
        if not os.path.exists(self.csv_path):
            with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(["timestamp", "device", "temp_c"])

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop = {"stop": False}
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop["stop"] = True

    def _loop(self):
        alerted = set()
        while not self._stop["stop"]:
            try:
                temps = self.get_temp_fn()  # dict device->temp
                ts = datetime.now().strftime("%H:%M:%S")
                with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    for dev, t in temps.items():
                        if t is None:
                            continue
                        w.writerow([datetime.now().isoformat(timespec="seconds"), dev, t])
                        self.history.append((ts, dev, t))
                        if len(self.history) > 500:
                            self.history.pop(0)
                        if t >= self.alert_temp and dev not in alerted:
                            alerted.add(dev)
                            if self.on_alert:
                                self.on_alert(dev, t)
                        elif t < self.alert_temp - 3 and dev in alerted:
                            alerted.discard(dev)
            except Exception:
                pass
            for _ in range(int(self.interval * 10)):
                if self._stop["stop"]:
                    break
                time.sleep(0.1)


def disk_benchmark(folder: str, size_mb: int = 100, progress=None) -> dict:
    """Test scrittura/lettura sequenziale con file temporaneo."""
    import tempfile
    testfile = os.path.join(folder, ".diskguard_bench.tmp")
    block = os.urandom(1024 * 1024)  # 1 MB
    try:
        t0 = time.time()
        with open(testfile, "wb") as f:
            for i in range(size_mb):
                f.write(block)
                if progress:
                    progress(i / size_mb * 50, f"Scrittura {i+1}/{size_mb} MB")
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        t1 = time.time()
        write_s = size_mb / max(0.01, t1 - t0)
        t2 = time.time()
        with open(testfile, "rb") as f:
            while f.read(4 * 1024 * 1024):
                pass
        t3 = time.time()
        read_s = size_mb / max(0.01, t3 - t2)
        if progress:
            progress(100, "Completato")
        return {"write_mbs": round(write_s, 1), "read_mbs": round(read_s, 1),
                "size_mb": size_mb, "ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        try:
            if os.path.exists(testfile):
                os.remove(testfile)
        except Exception:
            pass
