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
        "ends_with":   request.args.getlist("ends_with") or None,
        "bucket":      request.args.getlist("bucket") or None,
        "result":      request.args.getlist("result") or None,
        "season":      request.args.get("season") or queries.DEFAULT_SEASON,
    }


def get_filter_options(season=queries.DEFAULT_SEASON):
    conn = sqlite3.connect(queries.DB)
    cur = conn.cursor()
    def distinct(col, order):
        sql = f"SELECT DISTINCT {col} FROM possessions WHERE season = ? ORDER BY {order}"
        return [r[0] for r in cur.execute(sql, (season,)).fetchall()]
    players      = queries.get_players_from_descriptions(season)
    play_types   = distinct("play_type", "play_type")
    # Games ordered by their date (DISTINCT + ORDER BY a non-selected column is ambiguous)
    games        = [r[0] for r in cur.execute(
        "SELECT game FROM possessions WHERE season = ? GROUP BY game ORDER BY MIN(date)", (season,)).fetchall()]
    starts_with  = distinct("starts_with", "starts_with")
    ends_with    = distinct("player", "player")
    results      = distinct("result", "result")
    conn.close()
    return {"players": players, "play_types": play_types, "games": games, "starts_with": starts_with, "ends_with": ends_with, "results": results}


@app.route("/")
def index():
    options = get_filter_options()
    return render_template("index.html", **options)


@app.route("/api/filter-options")
def api_filter_options():
    return jsonify(get_filter_options(request.args.get("season") or queries.DEFAULT_SEASON))


@app.route("/api/turnover-rate")
def api_turnover_rate():
    return jsonify(queries.turnover_rate_by_duration(get_filters()))


@app.route("/api/fg-pct")
def api_fg_pct():
    return jsonify(queries.fg_pct_by_duration(get_filters()))


@app.route("/api/ppp")
def api_ppp():
    return jsonify(queries.ppp_by_duration(get_filters()))


@app.route("/api/game-scatter")
def api_game_scatter():
    return jsonify(queries.game_scatter(get_filters()))


@app.route("/api/possessions-table")
def api_possessions_table():
    return jsonify(queries.possessions_table(get_filters()))


@app.route("/api/pie-breakdowns")
def api_pie_breakdowns():
    return jsonify(queries.pie_breakdowns(get_filters()))



if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, port=port)
