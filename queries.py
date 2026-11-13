import sqlite3
import re

DB = "possessions.db"
DEFAULT_SEASON = "2025-26"

# ── Result scoring (shared by every query) ────────────────────────────────────
# 2025-26 labels: 'Make 2 Pts + 1 Pts' = and-one, plain 'Foul' = 0 pts.
# 2026-27 labels: '2pts + 1 Pt' = and-one, 'Foul + 2pts' = foul with 2 FTs made.
# Foul + FT rows add points (PPP) but are NOT field goal attempts (FG%).
POINTS = {
    "Make 2 Pts": 2, "Make 3 Pts": 3,
    "Make 2 Pts + 0 Pts": 2, "Make 2 Pts + 1 Pts": 3, "Make 3 Pts + 1 Pts": 4,
    "2pts + 0 Pts": 2, "2pts + 1 Pt": 3, "3pts + 0 Pts": 3, "3pts + 1 Pt": 4,
    "Foul + 1pt": 1, "Foul + 2pts": 2, "Foul + 3pts": 3,
}
FG_MAKES  = [r for r in POINTS if not r.startswith("Foul")]
FG_MISSES = ["Miss 2 Pts", "Miss 3 Pts"]

def _sql_list(values):
    return ", ".join(f"'{v}'" for v in values)

# Play Result filter groups (match both seasons' labels; SQLite LIKE ignores case).
RESULT_GROUP_SQL = {
    "2pt":  "(result LIKE 'Make 2 Pts%' OR result LIKE 'Miss 2 Pts%' OR result LIKE '2pts%')",
    "3pt":  "(result LIKE 'Make 3 Pts%' OR result LIKE 'Miss 3 Pts%' OR result LIKE '3pts%')",
    "foul": "result LIKE 'Foul%'",
}


def add_result_group(filters, conditions):
    """Picking several groups (e.g. 2PT + 3PT) shows possessions in any of them."""
    picked = [RESULT_GROUP_SQL[g] for g in (filters.get("result_group") or []) if g in RESULT_GROUP_SQL]
    if picked:
        conditions.append("(" + " OR ".join(picked) + ")")

MAKES_SQL  = _sql_list(FG_MAKES)
FGA_SQL    = _sql_list(FG_MAKES + FG_MISSES)
POINTS_SQL = "CASE " + " ".join(f"WHEN result = '{r}' THEN {p}" for r, p in POINTS.items()) + " ELSE 0 END"


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def get_players_from_descriptions(season=DEFAULT_SEASON):
    """Parse all unique player names that appear anywhere in the description column."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT description FROM possessions WHERE season = ?", (season,))
    names = set()
    for (desc,) in cur.fetchall():
        for seg in desc.split(' > '):
            m = re.match(r'^\d+\s+(.+)$', seg.strip())
            if m:
                name = m.group(1)
                if name != 'Pts':  # filter out free throw notation false match
                    names.add(name)
    conn.close()
    return sorted(names)


def build_where(filters):
    """Turns the active filters into a SQL WHERE clause.
    Each filter value can be a single string or a list of strings.
    Player filter matches any player mentioned anywhere in the description.
    """
    conditions = ["season = ?"]
    params = [filters.get("season") or DEFAULT_SEASON]

    # Player filter: match any player mentioned in the description
    player_values = filters.get("player")
    if player_values:
        if isinstance(player_values, str):
            player_values = [player_values]
        like_clauses = ["description LIKE ?" for _ in player_values]
        conditions.append("(" + " OR ".join(like_clauses) + ")")
        params.extend(f"%{p}%" for p in player_values)

    for key, col in [("play_type", "play_type"), ("game", "game"), ("starts_with", "starts_with"), ("ends_with", "player"), ("bucket", "bucket")]:
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

    add_result_group(filters, conditions)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return where, params


def build_where_no_game(filters):
    """Same as build_where but ignores the game filter (used for per-game scatter)."""
    conditions = ["season = ?"]
    params = [filters.get("season") or DEFAULT_SEASON]

    player_values = filters.get("player")
    if player_values:
        if isinstance(player_values, str):
            player_values = [player_values]
        like_clauses = ["description LIKE ?" for _ in player_values]
        conditions.append("(" + " OR ".join(like_clauses) + ")")
        params.extend(f"%{p}%" for p in player_values)

    for key, col in [("play_type", "play_type"), ("starts_with", "starts_with"), ("ends_with", "player")]:
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
    add_result_group(filters, conditions)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return where, params


def game_scatter(filters):
    """Per-game stats for scatter plots: avg duration, turnover rate, FG%, PPP."""
    where, params = build_where(filters)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT
            game,
            AVG(duration) as avg_duration,
            100.0 * SUM(CASE WHEN result = 'Turnover' THEN 1 ELSE 0 END) / COUNT(*) as turnover_rate,
            100.0 * SUM(CASE WHEN result IN ({MAKES_SQL}) THEN 1 ELSE 0 END)
                / NULLIF(SUM(CASE WHEN result IN ({FGA_SQL}) THEN 1 ELSE 0 END), 0) as fg_pct,
            1.0 * SUM({POINTS_SQL}) / COUNT(*) as ppp,
            COUNT(*) as count
        FROM possessions {where}
        GROUP BY game
    """, params)
    rows = cur.fetchall()
    conn.close()
    return [{"game": r["game"], "avg_duration": r["avg_duration"], "turnover_rate": r["turnover_rate"],
             "fg_pct": r["fg_pct"], "ppp": r["ppp"], "count": r["count"]} for r in rows]


def game_pace(season=DEFAULT_SEASON):
    """Per-game total possessions and avg possession duration. Ignores filters on purpose."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT game, MIN(date) AS date, COUNT(*) AS possessions, AVG(duration) AS avg_duration
        FROM possessions
        WHERE season = ?
        GROUP BY game
        ORDER BY MIN(date)
    """, (season,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def pie_breakdowns(filters):
    """Returns counts grouped by result, play_type, starts_with, and player for pie charts."""
    where, params = build_where(filters)
    conn = get_db()
    cur = conn.cursor()
    def query(col, order="n DESC"):
        cur.execute(f"SELECT {col}, COUNT(*) as n FROM possessions {where} GROUP BY {col} ORDER BY {order}", params)
        return [{"label": r[0], "count": r[1]} for r in cur.fetchall()]
    bucket_order = "CASE bucket WHEN '0-5s' THEN 1 WHEN '5-10s' THEN 2 WHEN '10-15s' THEN 3 WHEN '15-20s' THEN 4 WHEN '20+s' THEN 5 END"
    data = {
        "bucket":      query("bucket", bucket_order),
        "result":      query("result"),
        "play_type":   query("play_type"),
        "starts_with": query("starts_with"),
        "ends_with":   query("player"),
    }
    conn.close()
    return data


def possessions_table(filters):
    """Returns filtered possession rows for the data table."""
    where, params = build_where(filters)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT game, date, starts_with, player, play_type, duration, result, description
        FROM possessions {where}
        ORDER BY date, game, id
    """, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


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
    cur.execute(f"SELECT bucket, COUNT(*) as count, SUM(CASE WHEN result IN ({MAKES_SQL}) THEN 1 ELSE 0 END) as makes, 100.0 * SUM(CASE WHEN result IN ({MAKES_SQL}) THEN 1 ELSE 0 END) / NULLIF(SUM(CASE WHEN result IN ({FGA_SQL}) THEN 1 ELSE 0 END), 0) as fg_pct FROM possessions {where} GROUP BY bucket", params)
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
    cur.execute(f"SELECT bucket, COUNT(*) as count, SUM({POINTS_SQL}) as total_points, 1.0 * SUM({POINTS_SQL}) / COUNT(*) as ppp FROM possessions {where} GROUP BY bucket", params)
    rows = cur.fetchall()
    conn.close()
    return [{"bucket": row["bucket"], "ppp": row["ppp"], "count": row["count"], "total_points": row["total_points"]} for row in rows]
