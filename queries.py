import sqlite3

DB = "possessions.db"


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def build_where(filters):
    """Turns the active filters into a SQL WHERE clause.
    Each filter value can be a single string or a list of strings.
    """
    conditions = []
    params = []

    for key, col in [("player", "player"), ("play_type", "play_type"), ("game", "game"), ("starts_with", "starts_with")]:
        values = filters.get(key)
        if not values:
            continue
        if isinstance(values, list):
            placeholders = ",".join("?" * len(values))
            conditions.append(f"{col} IN ({placeholders})")
            params.extend(values)
        else:
            conditions.append(f"{col} = ?")
            params.append(values)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return where, params


def build_where_no_game(filters):
    """Same as build_where but ignores the game filter (used for per-game scatter)."""
    conditions = []
    params = []
    for key, col in [("player", "player"), ("play_type", "play_type"), ("starts_with", "starts_with")]:
        values = filters.get(key)
        if not values:
            continue
        if isinstance(values, list):
            placeholders = ",".join("?" * len(values))
            conditions.append(f"{col} IN ({placeholders})")
            params.extend(values)
        else:
            conditions.append(f"{col} = ?")
            params.append(values)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return where, params


def game_scatter(filters):
    """Per-game stats for scatter plots: avg duration, turnover rate, FG%, PPP."""
    where, params = build_where_no_game(filters)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT
            game,
            AVG(duration) as avg_duration,
            100.0 * SUM(CASE WHEN result = 'Turnover' THEN 1 ELSE 0 END) / COUNT(*) as turnover_rate,
            100.0 * SUM(CASE WHEN result IN ('Make 2 Pts','Make 3 Pts','Make 2 Pts + 1 Pts','Make 3 Pts + 1 Pts','Make 2 Pts + 0 Pts') THEN 1 ELSE 0 END)
                / NULLIF(SUM(CASE WHEN result IN ('Make 2 Pts','Make 3 Pts','Make 2 Pts + 1 Pts','Make 3 Pts + 1 Pts','Make 2 Pts + 0 Pts','Miss 2 Pts','Miss 3 Pts') THEN 1 ELSE 0 END), 0) as fg_pct,
            1.0 * SUM(CASE WHEN result = 'Make 2 Pts' THEN 2 WHEN result = 'Make 3 Pts' THEN 3
                           WHEN result = 'Make 2 Pts + 1 Pts' THEN 3 WHEN result = 'Make 3 Pts + 1 Pts' THEN 4
                           WHEN result = 'Make 2 Pts + 0 Pts' THEN 2 ELSE 0 END) / COUNT(*) as ppp,
            COUNT(*) as count
        FROM possessions {where}
        GROUP BY game
    """, params)
    rows = cur.fetchall()
    conn.close()
    return [{"game": r["game"], "avg_duration": r["avg_duration"], "turnover_rate": r["turnover_rate"],
             "fg_pct": r["fg_pct"], "ppp": r["ppp"], "count": r["count"]} for r in rows]


def possessions_for_scatter(filters):
    """Returns raw duration + result for every possession (for scatter plots)."""
    where, params = build_where(filters)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT duration, result FROM possessions {where}", params)
    rows = cur.fetchall()
    conn.close()
    return [{"duration": row["duration"], "result": row["result"]} for row in rows]


# ── YOUR QUERIES ──────────────────────────────────────────────────────────────
# Each function gets a filters dict and returns a list of rows for the chart.
# Duration buckets are already in the data as a "bucket" column — use them!
#
# Bucket values: '0-5s', '5-10s', '10-15s', '15-20s', '20+s'
#
# Useful columns in the possessions table:
#   result     TEXT  -- e.g. 'Make 2 Pts', 'Miss 3 Pts', 'Turnover', etc.
#   player     TEXT
#   play_type  TEXT
#   game       TEXT
#   duration   REAL  -- seconds
#   bucket     TEXT  -- duration bucket (already computed)


def turnover_rate_by_duration(filters):
    """
    Turnover rate per duration bucket.
    Return: [{"bucket": "0-5s", "turnover_rate": 12.5}, ...]
    Turnover rate = (# turnovers / total possessions) * 100
    """
    where, params = build_where(filters)
    conn = get_db()
    cur = conn.cursor()

    # TODO: write your SQL here
    cur.execute(f"SELECT bucket, COUNT(*) as count, SUM(CASE WHEN result = 'Turnover' THEN 1 ELSE 0 END) as turnovers, 100.0 * SUM(CASE WHEN result = 'Turnover' THEN 1 ELSE 0 END) / COUNT(*) as turnover_rate FROM possessions {where} GROUP BY bucket", params)
    rows = cur.fetchall()
    conn.close()
    return [{"bucket": row["bucket"], "turnover_rate": row["turnover_rate"], "count": row["count"], "turnovers": row["turnovers"]} for row in rows]


def fg_pct_by_duration(filters):
    """
    Field goal % per duration bucket.
    Return: [{"bucket": "0-5s", "fg_pct": 54.2}, ...]
    FG% = (makes / (makes + misses)) * 100
    Makes = 'Make 2 Pts' or 'Make 3 Pts'
    Misses = 'Miss 2 Pts' or 'Miss 3 Pts'
    """
    where, params = build_where(filters)
    conn = get_db()
    cur = conn.cursor()

    # TODO: write your SQL here
    cur.execute(f"SELECT bucket, COUNT(*) as count, SUM(CASE WHEN result IN ('Make 2 Pts', 'Make 3 Pts', 'Make 2 Pts + 1 Pts', 'Make 3 Pts + 1 Pts', 'Make 2 Pts + 0 Pts') THEN 1 ELSE 0 END) as makes, 100.0 * SUM(CASE WHEN result IN ('Make 2 Pts', 'Make 3 Pts', 'Make 2 Pts + 1 Pts', 'Make 3 Pts + 1 Pts', 'Make 2 Pts + 0 Pts') THEN 1 ELSE 0 END) / NULLIF(SUM(CASE WHEN result IN ('Make 2 Pts', 'Make 3 Pts', 'Make 2 Pts + 1 Pts', 'Make 3 Pts + 1 Pts', 'Make 2 Pts + 0 Pts', 'Miss 2 Pts', 'Miss 3 Pts') THEN 1 ELSE 0 END), 0) as fg_pct FROM possessions {where} GROUP BY bucket", params)
    rows = cur.fetchall()
    conn.close()
    return [{"bucket": row["bucket"], "fg_pct": row["fg_pct"], "count": row["count"], "makes": row["makes"]} for row in rows]


def ppp_by_duration(filters):
    """
    Points per possession per duration bucket.
    Return: [{"bucket": "0-5s", "ppp": 1.05}, ...]
    Points: Make 2 Pts = 2, Make 3 Pts = 3, 1 Pts = 1, everything else = 0
    PPP = total points / total possessions
    """
    where, params = build_where(filters)
    conn = get_db()
    cur = conn.cursor()

    # TODO: write your SQL here
    cur.execute(f"SELECT bucket, COUNT(*) as count, SUM(CASE WHEN result = 'Make 2 Pts' THEN 2 WHEN result = 'Make 3 Pts' THEN 3 WHEN result = 'Make 2 Pts + 1 Pts' THEN 3 WHEN result = 'Make 3 Pts + 1 Pts' THEN 4 WHEN result = 'Make 2 Pts + 0 Pts' THEN 2 ELSE 0 END) as total_points, 1.0 * SUM(CASE WHEN result = 'Make 2 Pts' THEN 2 WHEN result = 'Make 3 Pts' THEN 3 WHEN result = 'Make 2 Pts + 1 Pts' THEN 3 WHEN result = 'Make 3 Pts + 1 Pts' THEN 4 WHEN result = 'Make 2 Pts + 0 Pts' THEN 2 ELSE 0 END) / COUNT(*) as ppp FROM possessions {where} GROUP BY bucket", params)
    rows = cur.fetchall()
    conn.close()
    return [{"bucket": row["bucket"], "ppp": row["ppp"], "count": row["count"], "total_points": row["total_points"]} for row in rows]
