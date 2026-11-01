# Lab 7: запуск навантажувального тесту (профіль ЛР №4) + збір CPU/RAM контейнерів.
# Використання:  python scripts/run_locust.py before
#                python scripts/run_locust.py after
# Результат:     reports/lab7_<name>_stats.csv, ..._stats_history.csv, ..._resources.csv
import csv
import subprocess
import sys
import threading
import time

name = sys.argv[1] if len(sys.argv) > 1 else "test"
prefix = f"reports/lab7_{name}"
running = True


def to_mb(text):
    """'123.4MiB' -> 123.4, '1.2GiB' -> 1228.8"""
    text = text.strip()
    if text.endswith("GiB"):
        return float(text[:-3]) * 1024
    if text.endswith("MiB"):
        return float(text[:-3])
    if text.endswith("KiB"):
        return float(text[:-3]) / 1024
    return 0.0


def collect_resources():
    """Кожні ~2 с записує CPU % і RAM (МБ) кожного контейнера з `docker stats`."""
    start = time.time()
    with open(f"{prefix}_resources.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["second", "container", "cpu_percent", "mem_mb"])
        while running:
            out = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", "{{.Name}};{{.CPUPerc}};{{.MemUsage}}"],
                capture_output=True,
                text=True,
            ).stdout
            second = round(time.time() - start)
            for line in out.strip().splitlines():
                container, cpu, mem = line.split(";")
                writer.writerow([second, container, cpu.strip("%"), round(to_mb(mem.split("/")[0]), 1)])
            f.flush()


if __name__ == "__main__":
    thread = threading.Thread(target=collect_resources)
    thread.start()

    # Той самий інструмент і профіль, що в ЛР №4 (TelegramSpikeLoadShape у locustfile.py, 60 с)
    subprocess.run(["locust", "-f", "locustfile.py", "--headless", "--host", "http://localhost", "--csv", prefix])

    running = False
    thread.join()
    print(f"Готово: {prefix}_stats.csv та {prefix}_resources.csv")
