import json
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

PARAMS_PATH = Path(__file__).parent / "bkt_params.json"
with open(PARAMS_PATH) as f:
    PARAMS = json.load(f)          # {"1": {"prior":..,"learn":..,"guess":..,"slip":..}, ...}

STATE: dict[tuple[str, int], float] = {}   # (user_id, part) -> mastery

app = FastAPI(title="BKT Decision Service")


class Event(BaseModel):
    user_id: str
    question_id: str | None = None
    part: int = Field(ge=1, le=7)
    correct: Literal[0, 1]
    timestamp: int | None = None


class Decision(BaseModel):
    user_id: str
    part: int
    mastery_before: float
    mastery_after: float
    p_correct_next: float
    action: str
    latency_ms: float


def bkt_update(mastery: float, correct: int, p: dict) -> tuple[float, float]:
    """Return (new_mastery, p_correct_next)."""
    G = p["guess"]
    S = p["slip"]
    T = p["learn"]
    if correct ==1:
        posterior = mastery * (1 - S) / (mastery * (1 - S) + (1 - mastery) * G)
    else:
        posterior = mastery * S / (mastery * S + (1 - mastery) * (1 - G))

    new_mastery = posterior + (1 - posterior) * T
    p_correct_next = new_mastery * (1 - S) + (1 - new_mastery) * G
    return (new_mastery, p_correct_next)

def decide(mastery: float) -> str:
    if mastery < 0.5:
        return 'hint'
    elif mastery < 0.95:
        return 'practice'
    else:
        return 'next_skill'

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/event", response_model=Decision)
def handle_event(event: Event):
    start = time.perf_counter()
    p = PARAMS[str(event.part)]
    key = (event.user_id, event.part)

    before = STATE.get(key, p["prior"])
    after, p_next = bkt_update(before, event.correct, p)
    STATE[key] = after

    return Decision(
        user_id=event.user_id,
        part=event.part,
        mastery_before=round(before, 4),
        mastery_after=round(after, 4),
        p_correct_next=round(p_next, 4),
        action=decide(after),
        latency_ms=round((time.perf_counter() - start) * 1000, 3),
    )


@app.get("/state/{user_id}")
def get_state(user_id: str):
    parts = {part: m for (uid, part), m in STATE.items() if uid == user_id}
    if not parts:
        raise HTTPException(status_code=404, detail="unknown user")
    return {"user_id": user_id, "mastery": parts}


@app.post("/reset")
def reset():
    STATE.clear()
    return {"status": "cleared"}