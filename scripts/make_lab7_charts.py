# Lab 7: порівняльна таблиця та графіки «ДО» / «ПІСЛЯ» за CSV-звітами Locust і docker stats.
# Запуск: python scripts/make_lab7_charts.py   ->  docs/lab7_*.png + таблиця в консолі
import csv
from collections import defaultdict

import matplotlib.pyplot as plt

RUNS = {
    "before": "ДО",
    "after_db": "ПІСЛЯ: запити + індекси",
    "after_cache": "ПІСЛЯ: + кеш Redis",
}
COLORS = ["#2a78d6", "#eb6834", "#1baf7a"]  # фіксований порядок кольорів для трьох прогонів
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})


def read_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def aggregated(run):
    """Підсумковий рядок Aggregated з reports/lab7_<run>_stats.csv"""
    rows = read_csv(f"reports/lab7_{run}_stats.csv")
    return {r["Name"]: r for r in rows}


def resources(run):
    """Сумарне CPU (%) і RAM (МБ) трьох реплік web та БД за кожен замір."""
    per_sample = defaultdict(lambda: {"web_cpu": 0.0, "web_mem": 0.0, "db_cpu": 0.0, "db_mem": 0.0})
    for r in read_csv(f"reports/lab7_{run}_resources.csv"):
        key = "web" if "-web-" in r["container"] else "db" if "-db-" in r["container"] else None
        if key:
            per_sample[r["second"]][f"{key}_cpu"] += float(r["cpu_percent"])
            per_sample[r["second"]][f"{key}_mem"] += float(r["mem_mb"])
    samples = list(per_sample.values())
    result = {}
    for metric in ["web_cpu", "web_mem", "db_cpu", "db_mem"]:
        values = [s[metric] for s in samples]
        result[metric + "_avg"] = sum(values) / len(values)
        result[metric + "_max"] = max(values)
    return result


def bar_labels(ax, bars, fmt="{:.0f}"):
    for b in bars:
        ax.annotate(
            fmt.format(b.get_height()),
            (b.get_x() + b.get_width() / 2, b.get_height()),
            ha="center",
            va="bottom",
            fontsize=8,
            xytext=(0, 2),
            textcoords="offset points",
        )


stats = {run: aggregated(run) for run in RUNS}
res = {run: resources(run) for run in RUNS}

# ---------- 1. Таблиця в консолі (для звіту) ----------
rows = [
    ("Запитів усього", "Request Count", "{:.0f}"),
    ("RPS", "Requests/s", "{:.2f}"),
    ("Середня затримка, мс", "Average Response Time", "{:.0f}"),
    ("Медіана p50, мс", "50%", "{:.0f}"),
    ("p95, мс", "95%", "{:.0f}"),
    ("p99, мс", "99%", "{:.0f}"),
    ("Максимум, мс", "Max Response Time", "{:.0f}"),
    ("Помилки", "Failure Count", "{:.0f}"),
]
print("| Метрика | " + " | ".join(RUNS.values()) + " |")
print("|---|" + "---|" * len(RUNS))
for title, col, fmt in rows:
    print(f"| {title} | " + " | ".join(fmt.format(float(stats[r]["Aggregated"][col])) for r in RUNS) + " |")
for title, key in [
    ("CPU web (3 репліки), середнє %", "web_cpu_avg"),
    ("CPU web, пік %", "web_cpu_max"),
    ("CPU PostgreSQL, середнє %", "db_cpu_avg"),
    ("RAM web (3 репліки), середнє МБ", "web_mem_avg"),
    ("RAM web, пік МБ", "web_mem_max"),
    ("RAM PostgreSQL, середнє МБ", "db_mem_avg"),
]:
    print(f"| {title} | " + " | ".join(f"{res[r][key]:.1f}" for r in RUNS) + " |")

print("\nМедіана по ендпоінтах, мс:")
for name in stats["before"]:
    if name != "Aggregated":
        print(f"| {name} | " + " | ".join(stats[r][name]["50%"] for r in RUNS) + " |")

# ---------- 2. Затримка: середня / p50 / p95 / p99 ----------
metrics = [("Середня", "Average Response Time"), ("p50", "50%"), ("p95", "95%"), ("p99", "99%")]
fig, ax = plt.subplots(figsize=(8, 4.2))
width = 0.26
for i, run in enumerate(RUNS):
    values = [float(stats[run]["Aggregated"][col]) for _, col in metrics]
    bars = ax.bar([x + (i - 1) * width for x in range(len(metrics))], values, width - 0.03, color=COLORS[i], label=RUNS[run])
    bar_labels(ax, bars)
ax.set_xticks(range(len(metrics)), [m for m, _ in metrics])
ax.set_ylabel("мс (менше — краще)")
ax.set_title("Затримка відповіді (усі запити)")
ax.grid(axis="y", alpha=0.3)
ax.legend(frameon=False)
fig.tight_layout()
fig.savefig("docs/lab7_latency.png", dpi=130)

# ---------- 3. Пропускна здатність (RPS) ----------
fig, ax = plt.subplots(figsize=(6, 3.6))
values = [float(stats[r]["Aggregated"]["Requests/s"]) for r in RUNS]
bars = ax.bar(list(RUNS.values()), values, color=COLORS, width=0.55)
bar_labels(ax, bars, "{:.2f}")
ax.set_ylabel("запитів/с (більше — краще)")
ax.set_title("Пропускна здатність, RPS")
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
fig.savefig("docs/lab7_rps.png", dpi=130)

# ---------- 4. Динаміка під час тесту: p95 і RPS по секундах ----------
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
for i, run in enumerate(RUNS):
    history = [r for r in read_csv(f"reports/lab7_{run}_stats_history.csv") if r["Name"] == "Aggregated"]
    t0 = int(history[0]["Timestamp"])
    seconds = [int(r["Timestamp"]) - t0 for r in history]
    p95 = [float(r["95%"]) if r["95%"] != "N/A" else None for r in history]
    rps = [float(r["Requests/s"]) for r in history]
    ax1.plot(seconds, p95, color=COLORS[i], linewidth=2, label=RUNS[run])
    ax2.plot(seconds, rps, color=COLORS[i], linewidth=2, label=RUNS[run])
ax1.set_title("Накопичувальний p95 затримки (сірим — сплеск 10–35 с)")
ax1.set_ylabel("мс")
ax2.set_title("RPS під час тесту")
ax2.set_ylabel("запитів/с")
ax2.set_xlabel("секунда тесту")
for ax in (ax1, ax2):
    ax.axvspan(10, 35, color="#888888", alpha=0.08)
    ax.grid(alpha=0.3)
ax1.legend(frameon=False)
fig.tight_layout()
fig.savefig("docs/lab7_timeline.png", dpi=130)

# ---------- 5. Медіана по ендпоінтах ----------
endpoints = [n for n in stats["before"] if n != "Aggregated"]
short = [n.split("] ")[1] if "] " in n else n for n in endpoints]
fig, ax = plt.subplots(figsize=(9, 4.2))
for i, run in enumerate(RUNS):
    values = [float(stats[run][n]["50%"]) for n in endpoints]
    bars = ax.bar([x + (i - 1) * width for x in range(len(endpoints))], values, width - 0.03, color=COLORS[i], label=RUNS[run])
    bar_labels(ax, bars)
ax.set_xticks(range(len(endpoints)), short, fontsize=8)
ax.set_ylabel("мс")
ax.set_title("Медіанна затримка по ендпоінтах")
ax.grid(axis="y", alpha=0.3)
ax.legend(frameon=False)
fig.tight_layout()
fig.savefig("docs/lab7_endpoints.png", dpi=130)

# ---------- 6. Ресурси: CPU та RAM (два окремі графіки — різні одиниці) ----------
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 3.8))
names = list(RUNS.values())
bars = ax1.bar(names, [res[r]["web_cpu_avg"] for r in RUNS], color=COLORS, width=0.55)
bar_labels(ax1, bars, "{:.0f}%")
ax1.set_title("CPU реплік web, середнє\n(100% = 1 ядро)")
bars = ax2.bar(names, [res[r]["web_mem_max"] for r in RUNS], color=COLORS, width=0.55)
bar_labels(ax2, bars, "{:.0f}")
ax2.set_title("RAM реплік web, пік, МБ")
for ax in (ax1, ax2):
    ax.tick_params(axis="x", labelsize=7)
    ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
fig.savefig("docs/lab7_resources.png", dpi=130)

print("\nГрафіки збережено в docs/lab7_*.png")
