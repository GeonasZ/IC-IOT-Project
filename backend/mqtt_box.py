# MQTT connect and subscribe: use config mqtt[box_id], subscribe to all topics under that box, cache data for frontend chart
# Reference PLC-Connection connection.py / server_initializer.py
# If payload is JSON object (multiple data points), split by key into multiple series, one legend per series like history

import json
import time
import threading
from typing import Callable, Dict, List, Optional, Any

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

# Current connected box_id -> client; only one box connection at a time (disconnect old when switching box)
_mqtt_client: Optional[Any] = None
_mqtt_box_id: Optional[str] = None
_mqtt_lock = threading.Lock()

# box_id -> topic -> [(timestamp_ms, value), ...], max points per topic
_mqtt_stream: Dict[str, Dict[str, List[tuple]]] = {}
_MAX_POINTS_PER_TOPIC = 2000
_mqtt_received_count = 0  # Total messages received, for debugging


def _on_message(_client, _userdata, msg):
    global _mqtt_received_count
    try:
        payload = msg.payload.decode("utf-8", errors="replace").strip()
        topic = msg.topic
        box_id = _userdata.get("box_id")
        if not box_id:
            return
        ts_ms = int(time.time() * 1000)
        _mqtt_received_count += 1
        with _mqtt_lock:
            if box_id not in _mqtt_stream:
                _mqtt_stream[box_id] = {}
            try:
                data = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                data = None
            if isinstance(data, dict):
                for key, val in data.items():
                    try:
                        num_val = float(val)
                    except (TypeError, ValueError):
                        continue
                    series_key = topic + ">" + str(key)
                    if series_key not in _mqtt_stream[box_id]:
                        _mqtt_stream[box_id][series_key] = []
                    buf = _mqtt_stream[box_id][series_key]
                    buf.append((ts_ms, num_val))
                    if len(buf) > _MAX_POINTS_PER_TOPIC:
                        buf.pop(0)
            else:
                try:
                    value = float(payload) if data is None else float(data)
                except (TypeError, ValueError):
                    value = 0
                if topic not in _mqtt_stream[box_id]:
                    _mqtt_stream[box_id][topic] = []
                buf = _mqtt_stream[box_id][topic]
                buf.append((ts_ms, value))
                if len(buf) > _MAX_POINTS_PER_TOPIC:
                    buf.pop(0)
    except Exception:
        pass


def get_mqtt_config(get_config: Callable[[], dict], box_id: str) -> Optional[Dict]:
    """Read mqtt[box_id] from config. Format: broker, broker_port, client_id, sub_topic, username, password"""
    cfg = get_config()
    m = cfg.get("mqtt", {}).get(box_id)
    if not m or not isinstance(m, dict):
        return None
    broker = (m.get("broker") or "").strip()
    if not broker:
        return None
    return {
        "broker": broker,
        "broker_port": int(m.get("broker_port") or 1883),
        "client_id": (m.get("client_id") or "").strip() or None,
        "sub_topic": (m.get("sub_topic") or "").strip() or "",
        "username": (m.get("username") or "").strip() or None,
        "password": (m.get("password") or "").strip() or None,
    }


def subscribe_box(get_config: Callable[[], dict], box_id: str) -> tuple:
    """
    Connect and subscribe MQTT for the given box; subscribe to sub_topic and sub_topic# (all topics under that box).
    If already connected to another box, disconnect first.
    :return: (200, "ok") or (400, error_msg)
    """
    global _mqtt_client, _mqtt_box_id
    if mqtt is None:
        return 400, "paho-mqtt not installed"
    opts = get_mqtt_config(get_config, box_id)
    if not opts:
        return 400, f"mqtt.{box_id} not configured in config (need broker, sub_topic, etc.)"
    with _mqtt_lock:
        if _mqtt_client is not None:
            try:
                _mqtt_client.loop_stop()
                _mqtt_client.disconnect()
            except Exception:
                pass
            _mqtt_client = None
            _mqtt_box_id = None
        if box_id not in _mqtt_stream:
            _mqtt_stream[box_id] = {}
        client = mqtt.Client(
            client_id=opts["client_id"] or f"iot_project_{box_id}_{int(time.time())}",
            userdata={"box_id": box_id},
        )
        client.on_message = _on_message
        if opts["username"]:
            client.username_pw_set(username=opts["username"], password=opts["password"] or "")
        try:
            err = client.connect(opts["broker"], opts["broker_port"], keepalive=60)
        except Exception as e:
            return 400, str(e)
        if err != 0:
            return 400, f"connect failed with code {err}"
        client.loop_start()
        topic = (opts["sub_topic"] or "").strip().rstrip("/")
        if not topic:
            return 400, "sub_topic is empty"
        subscribe_topic = topic + "/#" if not topic.endswith("#") else topic
        rc, _ = client.subscribe(subscribe_topic, qos=0)
        if rc != 0:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:
                pass
            return 400, f"subscribe failed with code {rc}"
        _mqtt_client = client
        _mqtt_box_id = box_id
    return 200, "ok"


def unsubscribe_box() -> None:
    """Disconnect current MQTT connection if any."""
    global _mqtt_client, _mqtt_box_id
    with _mqtt_lock:
        if _mqtt_client is not None:
            try:
                _mqtt_client.loop_stop()
                _mqtt_client.disconnect()
            except Exception:
                pass
            _mqtt_client = None
            _mqtt_box_id = None


def get_stream(box_id: str) -> List[Dict]:
    """
    Return cached MQTT data for the given box, same format as history flat list for frontend chart.
    value is numeric (plottable); non-numeric payload stored as 0.
    [{ "name": topic, "time": ts_ms, "value": v }, ...]
    """
    with _mqtt_lock:
        if box_id not in _mqtt_stream:
            return []
        out = []
        for topic, points in _mqtt_stream[box_id].items():
            for ts, v in points:
                if not isinstance(v, (int, float)):
                    try:
                        v = float(v)
                    except (TypeError, ValueError):
                        v = 0
                out.append({"name": topic, "time": ts, "value": v})
    out.sort(key=lambda x: (x["time"], x["name"]))
    return out


def get_current_subscribed_box() -> Optional[str]:
    """Currently subscribed box_id, or None."""
    with _mqtt_lock:
        return _mqtt_box_id


def get_stream_stats(box_id: str) -> Dict:
    """Return cached point count and total received count for this box, for frontend hint."""
    with _mqtt_lock:
        points = 0
        if box_id in _mqtt_stream:
            for buf in _mqtt_stream[box_id].values():
                points += len(buf)
        return {"box_id": box_id, "points_in_buffer": points, "received_count": _mqtt_received_count}
