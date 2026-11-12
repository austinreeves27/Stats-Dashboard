"""Load a season's Synergy export into possessions.db.

Usage: python3 load_season.py <path-to-xlsx> <season>
e.g.   python3 load_season.py ~/Documents/synergy_possessions-2026.xlsx 2026-27

Re-running for the same season replaces that season's rows.
"""
import re
import sqlite3
import sys
from datetime import datetime

import openpyxl

DB = "possessions.db"
COLUMNS = ["result", "description", "player", "duration", "game", "date"]


def bucket_for(duration):
    if duration < 5:
        return "0-5s"
    if duration < 10:
        return "5-10s"
    if duration < 15:
        return "10-15s"
    if duration < 20:
        return "15-20s"
    return "20+s"


def normalize_result(result):
    """Tidy spelling only, so the same outcome isn't split into two labels.
    The meaning is kept: 'Foul + 2pts' = 2 FTs made, '2pts + 1 Pt' = and-one (3 pts).
    '2pts + 1 Pts' -> '2pts + 1 Pt'     'Foul + 0 pts' -> 'Foul + 0pts'
    """
    r = " ".join(result.split())
    m = re.match(r"^(\d)\s*pts \+ (\d) pts?$", r, re.IGNORECASE)
    if m:
        fg, ft = m.groups()
        return f"{fg}pts + {ft} {'Pt' if ft == '1' else 'Pts'}"
    m = re.match(r"^Foul \+ (\d)\s*pts?$", r, re.IGNORECASE)
    if m:
        ft = m.group(1)
        return f"Foul + {ft}{'pt' if ft == '1' else 'pts'}"
    return r


def parse_date(value):
    """Excel gives either a real datetime or text like 'Nov 2, 2026'."""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    return datetime.strptime(str(value).strip(), "%b %d, %Y").strftime("%Y-%m-%d")


def read_rows(path, skipped):
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True).active
    rows = ws.iter_rows(values_only=True)
    # Numbers exports put a title row above the header, so find the header row.
    for header in rows:
        if header and [str(h).strip().lower() if h else "" for h in header[:6]] == COLUMNS:
            break
    else:
        sys.exit(f"Couldn't find a header row with columns {COLUMNS}")

    for row in rows:
        if not row or row[0] is None:
            continue
        result, desc, player, duration, game, date = row[:6]
        if duration is None:
            # Can't bucket a possession without a duration.
            skipped[f"{game} ({date})"] = skipped.get(f"{game} ({date})", 0) + 1
            continue
        segs = desc.split(" > ")
        m = re.match(r"^\d+\s+(.+)$", segs[0].strip())
        duration = float(duration)
        yield {
            "result": normalize_result(result),
            "description": desc.strip(),
            "player": player.strip(),
            "duration": duration,
            "game": game.strip(),
            "date": parse_date(date),
            "play_type": segs[1].strip() if len(segs) > 1 else None,
            "bucket": bucket_for(duration),
            "starts_with": m.group(1) if m else None,
        }


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    path, season = sys.argv[1], sys.argv[2]
    skipped = {}
    rows = list(read_rows(path, skipped))
    for game, n in skipped.items():
        print(f"WARNING: skipped {n} possessions with no duration from {game}")

    conn = sqlite3.connect(DB)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(possessions)")]
    if "season" not in cols:
        # Everything already in the table is the 2025-26 season.
        conn.execute("ALTER TABLE possessions ADD COLUMN season TEXT")
        conn.execute("UPDATE possessions SET season = '2025-26'")

    conn.execute("DELETE FROM possessions WHERE season = ?", (season,))
    conn.executemany(
        """INSERT INTO possessions
           (result, description, player, duration, game, date, play_type, bucket, starts_with, season)
           VALUES (:result, :description, :player, :duration, :game, :date, :play_type, :bucket, :starts_with, :season)""",
        [{**r, "season": season} for r in rows],
    )
    conn.commit()
    for s, n in conn.execute("SELECT season, COUNT(*) FROM possessions GROUP BY season"):
        print(f"{s}: {n} possessions")
    conn.close()


if __name__ == "__main__":
    main()
