"""
Experiment client for the BKT Decision Service (Section 3.2).

Usage (from the repo root, in Cloud Shell):
    python3 scripts/replay_events.py e2 --label min0     # one cold-start probe + warm follow-ups
    python3 scripts/replay_events.py e3                  # load test at several concurrency levels
    python3 scripts/replay_events.py e4                  # replay full histories of a few test students

All raw measurements are appended to CSV files in results/.
"""

import argparse
import csv
import random
import statistics
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Experiment settings -- these are YOUR design decisions; change and justify.
# ---------------------------------------------------------------------------
URL = "https://bkt-decision-service-16189822363.europe-north1.run.app"
TEST_CSV = Path("data/processed/test.csv")
RESULTS = Path("results")

E2_WARM_FOLLOWUPS = 5             # warm requests sent right after each cold probe
E3_CONCURRENCY = [1, 10, 50]      # parallel clients per load level
E3_REQUESTS_PER_LEVEL = 200       # requests sent at each level
E3_TARGET_P95_MS = 200            # "real-time" target to compare against
E4_N_STUDENTS = 3                 # test students to replay
E4_PART = 5                       # skill whose trajectory is replayed
SEED = 42
# ---------------------------------------------------------------------------


def get_token() -> str:
    out = subprocess.run(
        ["gcloud", "auth", "print-identity-token"],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


HEADERS = {"Authorization": f"Bearer {get_token()}"}


def send_event(user_id: str, part: int, correct: int, session=None) -> dict:
    """POST one event; return client- and server-side timings plus the decision."""
    http = session or requests
    t0 = time.perf_counter()
    r = http.post(
        f"{URL}/event",
        json={"user_id": user_id, "part": part, "correct": correct},
        headers=HEADERS,
        timeout=60,
    )
    total_ms = (time.perf_counter() - t0) * 1000
    body = r.json() if r.ok else {}
    return {
        "sent_at_utc": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "part": part,
        "correct": correct,
        "status": r.status_code,
        "client_total_ms": round(total_ms, 2),
        "server_latency_ms": body.get("latency_ms"),
        "mastery_before": body.get("mastery_before"),
        "mastery_after": body.get("mastery_after"),
        "p_correct_next": body.get("p_correct_next"),
        "action": body.get("action"),
    }


def reset_state():
    r = requests.post(f"{URL}/reset", headers=HEADERS, timeout=60)
    r.raise_for_status()


def append_rows(path: Path, rows: list[dict]):
    RESULTS.mkdir(exist_ok=True)
    new_file = not path.exists()
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        if new_file:
            writer.writeheader()
        writer.writerows(rows)


def p95(values: list[float]) -> float:
    return statistics.quantiles(values, n=100)[94]


# --------------------------------- E2 ---------------------------------------
def run_e2(label: str):
    """
    Run ONLY when the service has scaled to zero (instance count 0 in the
    Cloud Run Metrics tab). The first request is the cold probe; the
    follow-ups measure warm latency for comparison.
    """
    rows = []
    first = send_event(f"e2_{label}", 5, 1)          # no session -> fresh connection
    first.update(experiment="e2", label=label, request_kind="first")
    rows.append(first)

    with requests.Session() as s:
        for i in range(E2_WARM_FOLLOWUPS):
            row = send_event(f"e2_{label}", 5, 1, session=s)
            row.update(experiment="e2", label=label, request_kind="followup")
            rows.append(row)

    append_rows(RESULTS / "e2_cold_start.csv", rows)
    warm = [r["client_total_ms"] for r in rows[1:]]
    print(f"[{label}] first request: {first['client_total_ms']:.0f} ms | "
          f"follow-up median: {statistics.median(warm):.0f} ms")


# --------------------------------- E3 ---------------------------------------
def run_e3():
    reset_state()
    rng = random.Random(SEED)
    summary = []

    for conc in E3_CONCURRENCY:
        events = [(f"e3_c{conc}_{i}", rng.randint(1, 7), rng.randint(0, 1))
                  for i in range(E3_REQUESTS_PER_LEVEL)]

        t_start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=conc) as pool:
            rows = list(pool.map(lambda e: send_event(*e), events))
        wall_s = time.perf_counter() - t_start

        for r in rows:
            r.update(experiment="e3", concurrency=conc)
        append_rows(RESULTS / "e3_load.csv", rows)

        ok = [r["client_total_ms"] for r in rows if r["status"] == 200]
        errors = len(rows) - len(ok)
        line = {
            "concurrency": conc,
            "requests": len(rows),
            "errors": errors,
            "median_ms": round(statistics.median(ok), 1),
            "p95_ms": round(p95(ok), 1),
            "throughput_rps": round(len(rows) / wall_s, 1),
            "meets_target": p95(ok) <= E3_TARGET_P95_MS,
        }
        summary.append(line)
        print(line)

    append_rows(RESULTS / "e3_summary.csv", summary)


# --------------------------------- E4 ---------------------------------------
def run_e4():
    import pandas as pd

    test = pd.read_csv(TEST_CSV)
    part_rows = test[test["part"] == E4_PART]
    top_users = part_rows["user_id"].value_counts().head(E4_N_STUDENTS).index

    reset_state()
    rows = []
    with requests.Session() as s:
        for uid in top_users:
            history = part_rows[part_rows["user_id"] == uid]   # already in time order
            for step, rec in enumerate(history.itertuples(), start=1):
                row = send_event(str(uid), int(rec.part), int(rec.correct), session=s)
                row.update(experiment="e4", step=step)
                rows.append(row)
            print(f"replayed {len(history)} events for student {uid}")

    append_rows(RESULTS / "e4_trajectories.csv", rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("experiment", choices=["e2", "e3", "e4"])
    parser.add_argument("--label", default="min0",
                        help="E2 setting label, e.g. min0 or min1")
    args = parser.parse_args()

    {"e2": lambda: run_e2(args.label), "e3": run_e3, "e4": run_e4}[args.experiment]()