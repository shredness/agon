"""
One-time script to recalculate RD correctly for all sessions.
Formula: density = Σ(set.vol / set.time) per exercise, summed across exercises
         rd = total_density / bodyweight

Run inside the container:
  docker exec rdtracker-backend-1 python3 /app/fix_rd.py
Or copy into container and run.
"""
import sqlite3, json, os

DB_PATH = os.environ.get("DB_PATH", "/data/sessions.db")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

rows = conn.execute("SELECT id, bw, exercises FROM sessions").fetchall()

fixed = 0
errors = 0

for r in rows:
    bw = r["bw"]
    try:
        exercises = json.loads(r["exercises"])
    except Exception as e:
        print(f"  ERROR parsing session {r['id']}: {e}")
        errors += 1
        continue

    total_density = 0.0
    for ex in exercises:
        ex_density = 0.0
        for s in ex.get("sets", []):
            vol  = s.get("vol", 0)
            time = s.get("time", 2)   # default 2 if somehow missing
            if time > 0:
                ex_density += vol / time
        ex["density"] = round(ex_density, 2)
        ex["totalVol"] = round(sum(s.get("vol", 0) for s in ex.get("sets", [])), 1)
        total_density += ex_density

    rd = round(total_density / bw, 2) if bw else 0

    conn.execute(
        "UPDATE sessions SET rd=?, total_density=?, exercises=? WHERE id=?",
        (rd, round(total_density, 2), json.dumps(exercises), r["id"])
    )
    fixed += 1

conn.commit()
conn.close()

print(f"Done. Fixed {fixed} sessions, {errors} errors.")
