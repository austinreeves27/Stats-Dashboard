from flask import Flask, jsonify, render_template, request
import sqlite3
import queries

app = Flask(__name__)


def get_filters():
    return {
        "player":      request.args.getlist("player") or None,
        "play_type":   request.args.getlist("play_type") or None,
        "game":        request.args.getlist("game") or None,
        "starts_with": request.args.getlist("starts_with") or None,
    }


def get_filter_options():
    conn = sqlite3.connect(queries.DB)
    cur = conn.cursor()
    players      = [r[0] for r in cur.execute("SELECT DISTINCT player      FROM possessions ORDER BY player").fetchall()]
    play_types   = [r[0] for r in cur.execute("SELECT DISTINCT play_type   FROM possessions ORDER BY play_type").fetchall()]
    games        = [r[0] for r in cur.execute("SELECT DISTINCT game        FROM possessions ORDER BY date").fetchall()]
    starts_with  = [r[0] for r in cur.execute("SELECT DISTINCT starts_with FROM possessions ORDER BY starts_with").fetchall()]
    conn.close()
    return {"players": players, "play_types": play_types, "games": games, "starts_with": starts_with}


@app.route("/")
def index():
    options = get_filter_options()
    return render_template("index.html", **options)


@app.route("/api/turnover-rate")
def api_turnover_rate():
    return jsonify(queries.turnover_rate_by_duration(get_filters()))


@app.route("/api/fg-pct")
def api_fg_pct():
    return jsonify(queries.fg_pct_by_duration(get_filters()))


@app.route("/api/ppp")
def api_ppp():
    return jsonify(queries.ppp_by_duration(get_filters()))


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, port=port)
