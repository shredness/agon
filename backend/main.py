from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import sqlite3, json, os
from datetime import datetime, timedelta

app = FastAPI(title="Prometheus API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = os.environ.get("DB_PATH", "/data/sessions.db")


def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            bw REAL NOT NULL,
            rd REAL NOT NULL,
            total_density REAL NOT NULL,
            exercises TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


init_db()


class SetData(BaseModel):
    reps: float
    rawLoad: float
    trueLbs: float
    vol: float


class ExerciseData(BaseModel):
    name: str
    time: float
    sets: list[SetData]
    totalVol: float
    density: float
    tool: Optional[str] = "Bar"
    mult: Optional[float] = 2.0
    isBW: Optional[bool] = False


class SessionIn(BaseModel):
    date: str
    bw: float
    rd: float
    total_density: float
    exercises: list[ExerciseData]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/sessions")
def get_sessions():
    conn = get_db()
    rows = conn.execute("SELECT * FROM sessions ORDER BY date ASC").fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "date": r["date"],
            "bw": r["bw"],
            "rd": r["rd"],
            "total_density": r["total_density"],
            "exercises": json.loads(r["exercises"]),
        }
        for r in rows
    ]


@app.post("/sessions")
def save_session(session: SessionIn):
    conn = get_db()
    try:
        conn.execute(
            """
            INSERT INTO sessions (date, bw, rd, total_density, exercises)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                bw=excluded.bw,
                rd=excluded.rd,
                total_density=excluded.total_density,
                exercises=excluded.exercises
            """,
            (
                session.date,
                session.bw,
                session.rd,
                session.total_density,
                json.dumps([e.dict() for e in session.exercises]),
            ),
        )
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))
    conn.close()
    return {"status": "saved", "date": session.date}


@app.delete("/sessions/{date}")
def delete_session(date: str):
    conn = get_db()
    conn.execute("DELETE FROM sessions WHERE date = ?", (date,))
    conn.commit()
    conn.close()
    return {"status": "deleted", "date": date}


@app.get("/trend")
def get_trend():
    conn = get_db()
    rows = conn.execute("SELECT date, bw, rd FROM sessions ORDER BY date ASC").fetchall()
    conn.close()

    by_week: dict = {}
    for r in rows:
        try:
            d = datetime.strptime(r["date"], "%Y-%m-%d")
        except ValueError:
            continue
        days_to_sunday = (6 - d.weekday()) % 7
        sun = d + timedelta(days=days_to_sunday)
        key = f"{sun.month}/{sun.day}/{sun.year}"
        if key not in by_week:
            by_week[key] = []
        by_week[key].append({"rd": r["rd"], "wt": r["bw"]})

    result = []
    for week, entries in by_week.items():
        avg_rd = sum(e["rd"] for e in entries) / len(entries)
        avg_wt = sum(e["wt"] for e in entries) / len(entries)
        result.append({
            "week": week,
            "rd": round(avg_rd, 2),
            "wt": round(avg_wt, 1),
        })

    result.sort(key=lambda w: datetime.strptime(w["week"], "%m/%d/%Y"))
    return result


@app.get("/progress/{exercise_name}")
def get_progress(exercise_name: str):
    """
    Returns per-session data for a specific exercise:
    date, top set load (trueLbs), total vol, density, session RD, bodyweight.
    Useful for graphing strength progression on a single lift over time.
    """
    conn = get_db()
    rows = conn.execute(
        "SELECT date, bw, rd, exercises FROM sessions ORDER BY date ASC"
    ).fetchall()
    conn.close()

    result = []
    for r in rows:
        exercises = json.loads(r["exercises"])
        match = next((e for e in exercises if e.get("name","").lower() == exercise_name.lower()), None)
        if not match:
            continue
        sets = match.get("sets", [])
        if not sets:
            continue
        top_set = max(sets, key=lambda s: s.get("trueLbs", 0))
        total_vol = sum(s.get("vol", 0) for s in sets)
        result.append({
            "date":      r["date"],
            "bw":        r["bw"],
            "rd":        r["rd"],
            "topLoad":   round(top_set.get("trueLbs", 0), 1),
            "topReps":   int(top_set.get("reps", 0)),
            "totalVol":  round(total_vol, 1),
            "density":   round(match.get("density", 0), 2),
            "sets":      len(sets),
        })

    return result


@app.get("/exercises/logged")
def get_logged_exercises():
    """Returns a sorted list of all exercise names that have at least one logged session."""
    conn = get_db()
    rows = conn.execute("SELECT exercises FROM sessions").fetchall()
    conn.close()
    names = set()
    for r in rows:
        for ex in json.loads(r["exercises"]):
            if ex.get("name"):
                names.add(ex["name"])
    return sorted(names)
