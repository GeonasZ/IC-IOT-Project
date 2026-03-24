# Flask backend: FBox realtime data, history, box list APIs

import csv
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

from flask import Flask, request, jsonify, send_from_directory, abort
from backend.config_loader import load_config, get_data_points_for_api, translate_to_english
from backend import mqtt_box
from backend import analysis as analysis_module
import lib.fbox_login as fbox_login
import lib.fbox_client as fbox

app = Flask(
    __name__,
    static_folder=str(ROOT / "frontend" / "static"),
    static_url_path="",
)

_config = None
_token_cache = {}


def get_config():
    global _config
    if _config is None:
        _config = load_config()
    return _config


def get_token(force_refresh=False, abort_on_fail=True):
    """Get or refresh FBox access token; delegates to fbox_login."""
    return fbox_login.get_token(get_config, _token_cache, force_refresh=force_refresh, abort_on_fail=abort_on_fail)


def ensure_token():
    """Re-login if current token is invalid."""
    return fbox_login.ensure_token(get_config, _token_cache)


def with_fbox_token(f):
    """Decorator: inject token/address; delegates to fbox_login."""
    return fbox_login.with_fbox_token(get_config, _token_cache)(f)


# ---------- API routes ----------


@app.route("/api/realtime/get", methods=["POST"])
@with_fbox_token
def api_realtime_get(token, address):
    """Get realtime data. body: { "box_id": "xxx", "request": [{"name": "group name", "points": ["point1", "point2"]}] }"""
    data = request.get_json() or {}
    box_id = data.get("box_id")
    req = data.get("request")
    if not box_id or not req:
        return jsonify({"info": "missing box_id or request"}), 400
    err, result, msg = fbox.read_realtime_data(address, token, box_id, req)
    if err == 200:
        return jsonify(result)
    return jsonify({"info": msg or "Error"}), 400 if err == 400 else 401


@app.route("/api/history/get", methods=["POST"])
@with_fbox_token
def api_history_get(token, address):
    """
    Get history data.
    body: {
      "request": [{"box_id": "xxx", "request": [{"name": "group name", "channels": ["channel1", "channel2"]}]}],
      "begin": ms timestamp,
      "end": ms timestamp,
      "limit": -500,
      "flatten": true/false
    }
    """
    data = request.get_json() or {}
    boxes_request = data.get("request", [])
    begin = data.get("begin")
    end = data.get("end")
    if begin is None or end is None or not boxes_request:
        return jsonify({"info": "missing request / begin / end"}), 400
    try:
        begin = int(begin)
        end = int(end)
    except (TypeError, ValueError):
        return jsonify({"info": "begin / end must be numbers (ms timestamp)"}), 400
    limit = data.get("limit", -500)
    time_zone = data.get("time_zone", "Asia/Shanghai")
    time_boundary_type = data.get("time_boundary_type", 3)
    g = data.get("g", 2)
    err, result, msg = fbox.get_history_data_by_request(
        address, token, boxes_request, begin, end,
        limit=limit, time_zone=time_zone, time_boundary_type=time_boundary_type, g=g,
    )
    if err != 200:
        info = msg or "Error"
        if err == 400:
            info = info + "; ensure group/channel names in request exist for that box (e.g. replace placeholders with real names)"
        return jsonify({"info": info}), 400 if err == 400 else 401
    if data.get("flatten"):
        result = fbox.history_flatten(result)
    return jsonify(result)


def _get_box_id_from_config():
    """Read box_id list from config and return."""
    cfg = get_config()
    box_id = cfg.get("fbox", {}).get("box_id", [])
    if not isinstance(box_id, list):
        box_id = [box_id] if box_id else []
    return box_id


@app.route("/api/boxes/list_box_id", methods=["GET"])
def api_boxes_list_box_id():
    """Return configured box_id list and each box's group name (from data_points); does not call FBox API."""
    box_ids = _get_box_id_from_config()
    dp = get_config().get("fbox", {}).get("data_points", {})
    boxes = [{"box_id": bid, "group": dp.get(bid, {}).get("group", "")} for bid in box_ids]
    return jsonify({"box_id": box_ids, "boxes": boxes})


@app.route("/api/boxes/list", methods=["GET"])
def api_boxes_list():
    """Legacy frontend: return box_id from config, same as list_box_id; does not call FBox API."""
    return jsonify({"box_id": _get_box_id_from_config()})


@app.route("/api/boxes/single", methods=["POST"])
@with_fbox_token
def api_boxes_single(token, address):
    """Get single box info by box number. body: { "box_no": "box number" }"""
    data = request.get_json() or {}
    box_no = data.get("box_no") or (data.get("boxNo") or "").strip()
    if not box_no:
        return jsonify({"info": "missing box_no (or boxNo)"}), 400
    err, result, msg = fbox.get_box_single(address, token, box_no)
    if err == 200:
        return jsonify(result)
    if err == 404:
        return jsonify({"info": msg or "box not found"}), 404
    return jsonify({"info": msg or "Error"}), 400 if err == 400 else 401


@app.route("/api/boxes/dmon/groups", methods=["POST"])
@with_fbox_token
def api_boxes_dmon_groups(token, address):
    """Get monitor point group list for the given box. body: { "box_no": "FBox serial number" }"""
    data = request.get_json() or {}
    box_no = (data.get("box_no") or data.get("boxNo") or "").strip()
    if not box_no:
        return jsonify({"info": "missing box_no (or boxNo)"}), 400
    err, result, msg = fbox.get_dmon_groups(address, token, box_no)
    if err == 200:
        return jsonify(result)
    if err == 404:
        return jsonify({"info": msg or "API or box not found"}), 404
    if err == 429:
        return jsonify({"info": msg or "too many requests"}), 429
    return jsonify({"info": msg or "Error"}), 400 if err == 400 else 401


@app.route("/api/boxes/dmon/points", methods=["POST"])
@with_fbox_token
def api_boxes_dmon_points(token, address):
    """Get monitor points (data points) by group. body: { "box_id": "box UID", "group_id": "group Id" }"""
    data = request.get_json() or {}
    box_id = (data.get("box_id") or "").strip()
    group_id = (data.get("group_id") or "").strip()
    if not box_id or not group_id:
        return jsonify({"info": "missing box_id or group_id"}), 400
    cfg = get_config().get("fbox", {})
    client_id = cfg.get("client_id") or None
    err, result, msg = fbox.get_dmon_by_group(
        address, token, box_id, group_id, client_id=client_id
    )
    if err == 200:
        return jsonify(result)
    if err == 404:
        return jsonify({"info": msg or "API or group not found"}), 404
    if err == 429:
        return jsonify({"info": msg or "too many requests"}), 429
    return jsonify({"info": msg or "Error"}), 400 if err == 400 else 401


@app.route("/api/boxes/location", methods=["POST"])
@with_fbox_token
def api_boxes_location(token, address):
    """Get box locations. body: { "box_nos": ["id1", "id2"] } (box_No list)"""
    data = request.get_json() or {}
    box_nos = data.get("box_nos", [])
    if not box_nos:
        return jsonify({"info": "missing box_nos"}), 400
    err, result, msg = fbox.get_boxes_location(address, token, box_nos)
    if err != 200:
        return jsonify({"info": msg or "Error"}), 400 if err == 400 else 401
    return jsonify(result)


@app.route("/api/mqtt/subscribe", methods=["POST"])
def api_mqtt_subscribe():
    """Connect MQTT and subscribe to all topics for the selected box. body: { "box_id": "box number" }"""
    data = request.get_json() or {}
    box_id = (data.get("box_id") or data.get("boxNo") or "").strip()
    if not box_id:
        return jsonify({"info": "missing box_id"}), 400
    code, msg = mqtt_box.subscribe_box(get_config, box_id)
    if code != 200:
        return jsonify({"info": msg or "MQTT connect/subscribe failed"}), 400
    return jsonify({"info": "ok", "box_id": box_id})


@app.route("/api/mqtt/unsubscribe", methods=["POST"])
def api_mqtt_unsubscribe():
    """Disconnect current MQTT connection."""
    mqtt_box.unsubscribe_box()
    return jsonify({"info": "ok"})


@app.route("/api/mqtt/stream", methods=["GET"])
def api_mqtt_stream():
    """Get current box MQTT cached data for chart. query: box_id"""
    box_id = (request.args.get("box_id") or "").strip()
    if not box_id:
        return jsonify({"info": "missing box_id"}), 400
    out = mqtt_box.get_stream(box_id)
    return jsonify(out)


@app.route("/api/mqtt/status", methods=["GET"])
def api_mqtt_status():
    """Currently subscribed box_id, or null."""
    box_id = mqtt_box.get_current_subscribed_box()
    return jsonify({"box_id": box_id})


@app.route("/api/mqtt/stats", methods=["GET"])
def api_mqtt_stats():
    """MQTT total received count and current buffer points for frontend. query: box_id"""
    box_id = (request.args.get("box_id") or "").strip()
    if not box_id:
        return jsonify({"info": "missing box_id"}), 400
    return jsonify(mqtt_box.get_stream_stats(box_id))


@app.route("/api/boxes/history/chart", methods=["POST"])
@with_fbox_token
def api_boxes_history_chart(token, address):
    """
    Fetch history for data points configured in fbox.data_points[box_no], return flat list for frontend chart.
    body: { "box_no": "box number", "begin": ms timestamp, "end": ms timestamp }
    """
    data = request.get_json() or {}
    box_no = (data.get("box_no") or data.get("boxNo") or "").strip()
    begin = data.get("begin")
    end = data.get("end")
    if not box_no:
        return jsonify({"info": "missing box_no"}), 400
    try:
        begin = int(begin) if begin is not None else None
        end = int(end) if end is not None else None
    except (TypeError, ValueError):
        return jsonify({"info": "begin / end must be numbers (ms timestamp)"}), 400
    if begin is None or end is None:
        return jsonify({"info": "missing begin or end"}), 400
    dp_api = get_data_points_for_api(box_no)
    if not dp_api:
        return jsonify({"info": f"data_points for box_no={box_no} not configured in config (need group and points)"}), 400
    group_name = dp_api["group"]
    point_names = dp_api["point_names"]
    err, result, msg = fbox.get_box_data_points_history(
        address, token, box_no, begin, end, group_name, point_names,
        limit=data.get("limit", -500),
        g=data.get("g", 2),
    )
    if err != 200:
        return jsonify({"info": msg or "fetch history failed"}), 400 if err == 400 else 401
    # Frontend uses English names from config; replace Chinese names in result with English
    result_english = [
        {**item, "name": translate_to_english(item.get("name", ""))}
        for item in result
    ]
    return jsonify(result_english)


CSV_HISTORY_PATH = ROOT / "3.2_3.16history.csv"


def _load_csv_history_flat():
    """Read 3.2_3.16history.csv and return flat list [{ name, time, value }, ...] for chart."""
    if not CSV_HISTORY_PATH.is_file():
        return None
    flat = []
    with open(CSV_HISTORY_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or reader.fieldnames[0].lower() != "time":
            return None
        series_cols = [c for c in reader.fieldnames if c and c.lower() != "time"]
        for row in reader:
            try:
                t_str = row.get("time", "").strip()
                if not t_str:
                    continue
                dt = datetime.strptime(t_str, "%Y-%m-%d %H:%M:%S")
                t_ms = int(dt.timestamp() * 1000)
            except (ValueError, TypeError):
                continue
            for col in series_cols:
                try:
                    v = row.get(col, "")
                    if v == "":
                        continue
                    num = float(v)
                    if num == num:  # skip NaN
                        flat.append({"name": col, "time": t_ms, "value": num})
                except (ValueError, TypeError):
                    continue
    return flat


@app.route("/api/boxes/history/3_2_3_16", methods=["GET"])
def api_boxes_history_3_2_3_16():
    """
    Return history from 3.2_3.16history.csv in same flat format as /api/boxes/history/chart for frontend chart.
    """
    flat = _load_csv_history_flat()
    if flat is None:
        return jsonify({"info": "3.2_3.16history.csv not found or invalid"}), 404
    return jsonify(flat)


# ---------- Data analysis API: Pearson correlation coefficient, covariance matrix, etc. ----------


@app.route("/api/analysis/run", methods=["POST"])
def api_analysis_run():
    """
    Do correlation analysis on the history data (Pearson, covariance, optional Spearman).
    body one of the following:
      1) { "data": [ { "name", "time", "value" }, ... ] }  directly pass in flat data
      2) { "source": "3_2_3_16" }  use 3.2_3.16history.csv data
      3) { "box_no", "begin", "end" }  fetch history from FBox by time range and analyze
    Optional: "include_spearman": true
    Return: { "labels", "labels_short", "pearson", "covariance", "count", "spearman"? }
    """
    data = request.get_json() or {}
    flat = None

    if "data" in data and isinstance(data["data"], list):
        flat = data["data"]
    elif data.get("source") == "3_2_3_16":
        flat = _load_csv_history_flat()
        if flat is None:
            return jsonify({"info": "3.2_3.16history.csv not found or invalid"}), 404
    elif data.get("box_no") and data.get("begin") is not None and data.get("end") is not None:
        box_no = (data.get("box_no") or data.get("boxNo") or "").strip()
        try:
            begin = int(data.get("begin"))
            end = int(data.get("end"))
        except (TypeError, ValueError):
            return jsonify({"info": "begin/end must be numbers (ms timestamp)"}), 400
        dp_api = get_data_points_for_api(box_no)
        if not dp_api:
            return jsonify({"info": f"data_points for box_no={box_no} not configured"}), 400
        token, address = get_token(abort_on_fail=True)
        err, result, msg = fbox.get_box_data_points_history(
            address, token, box_no, begin, end,
            dp_api["group"], dp_api["point_names"],
            limit=data.get("limit", -2000),
            g=data.get("g", 2),
        )
        if err != 200:
            return jsonify({"info": msg or "fetch history failed"}), 400 if err == 400 else 401
        result_english = [
            {**item, "name": translate_to_english(item.get("name", ""))}
            for item in result
        ]
        flat = result_english
    else:
        return jsonify({"info": "provide 'data', or 'source':'3_2_3_16', or 'box_no'+'begin'+'end'"}), 400

    include_spearman = data.get("include_spearman", False)
    out = analysis_module.run_analysis(flat, include_spearman=include_spearman)
    if out is None:
        return jsonify({"info": "not enough data or cannot align by time (at least 2 time points and all series have values)"}), 400
    return jsonify(out)


# ---------- Error handlers: return JSON so frontend does not get HTML ----------


@app.errorhandler(401)
def error_401(e):
    return jsonify({"info": e.description or "Unauthorized"}), 401


@app.errorhandler(404)
def error_404(e):
    return jsonify({"info": "Not found"}), 404


@app.errorhandler(500)
def error_500(e):
    return jsonify({"info": "Internal server error"}), 500


# ---------- Frontend static page ----------


@app.route("/")
def index():
    # Pre-fetch token when serving frontend (non-blocking; still serve page on failure)
    get_token(abort_on_fail=False)
    static_dir = app.static_folder or str(ROOT / "frontend" / "static")
    return send_from_directory(static_dir, "index.html")


def create_app():
    return app
