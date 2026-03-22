# Load FBox and server config from config.json or env vars
# Bidirectional translation: translation.json may be { "en_to_zh": {...}, "zh_to_en": {...} } or legacy single dict (en_to_zh)

import os
import json
import pickle
from pathlib import Path
from typing import Dict, Optional, Any
from warnings import warn

# Project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"
TRANSLATION_JSON_PATH = PROJECT_ROOT / "translation.json"
TRANSLATION_PKL_PATH = PROJECT_ROOT / "translation.pkl"

_translation_data: Optional[Dict[str, Dict[str, str]]] = None


def _load_translation_dict() -> Dict[str, Dict[str, str]]:
    """Load bidirectional translation: returns {"en_to_zh": {...}, "zh_to_en": {...}}."""
    global _translation_data
    if _translation_data is not None:
        return _translation_data
    if TRANSLATION_PKL_PATH.exists():
        with open(TRANSLATION_PKL_PATH, "rb") as f:
            _translation_data = pickle.load(f)
        if isinstance(_translation_data, dict) and "en_to_zh" in _translation_data:
            return _translation_data
        _translation_data = _normalize_translation(_translation_data)
        return _translation_data
    if TRANSLATION_JSON_PATH.exists():
        with open(TRANSLATION_JSON_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        _translation_data = _normalize_translation(raw)
        with open(TRANSLATION_PKL_PATH, "wb") as f:
            pickle.dump(_translation_data, f)
        return _translation_data
    warn("translation.json not found, using empty translation dict")
    _translation_data = {"en_to_zh": {}, "zh_to_en": {}}
    return _translation_data


def _normalize_translation(raw: Any) -> Dict[str, Dict[str, str]]:
    """Convert JSON to {"en_to_zh": {...}, "zh_to_en": {...}}. Supports new structure or legacy single dict."""
    if isinstance(raw, dict) and "en_to_zh" in raw and "zh_to_en" in raw:
        en_to_zh = raw["en_to_zh"] or {}
        zh_to_en = raw["zh_to_en"] or {}
        return {"en_to_zh": dict(en_to_zh), "zh_to_en": dict(zh_to_en)}
    if isinstance(raw, dict) and not any(k in raw for k in ("en_to_zh", "zh_to_en")):
        en_to_zh = {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)}
        zh_to_en = {v: k for k, v in en_to_zh.items()}
        return {"en_to_zh": en_to_zh, "zh_to_en": zh_to_en}
    return {"en_to_zh": {}, "zh_to_en": {}}


def translate_to_chinese(english_name: str) -> str:
    """Replace English name from config with Chinese (for FBox API calls). Returns original if no mapping."""
    d = _load_translation_dict()
    return d["en_to_zh"].get(english_name, english_name)


def translate_to_english(chinese_name: str) -> str:
    """Replace Chinese name with English (for frontend, CSV headers). Lookup zh_to_en first, then fragment replace."""
    d = _load_translation_dict()
    zh_to_en = d["zh_to_en"]
    if chinese_name in zh_to_en:
        return zh_to_en[chinese_name]
    out = chinese_name
    for zh, en in zh_to_en.items():
        out = out.replace(zh, en)
    return out


def get_data_points_for_api(box_no: str) -> Optional[Dict]:
    """
    Get data_points for the given box from config and translate group/point names from English to Chinese for FBox history API.
    Returns {"group": "Chinese group name", "point_names": ["Chinese point name", ...]}, or None if not configured/invalid.
    """
    cfg = load_config()
    dp = cfg.get("fbox", {}).get("data_points", {}).get(box_no)
    if not dp or not isinstance(dp.get("points"), dict):
        return None
    group_en = (dp.get("group") or "").strip()
    points = dp["points"]
    if not group_en or not points:
        return None
    group_zh = translate_to_chinese(group_en)
    point_names_zh = [translate_to_chinese(k) for k in points.keys()]
    return {"group": group_zh, "point_names": point_names_zh}


def load_config():
    """Load config.json and allow env vars to override."""
    if not CONFIG_PATH.exists():
        config_file_path = PROJECT_ROOT / "config.json"
        if config_file_path.exists():
            with open(config_file_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        else:
            warn("config.json not found, using default config")
            cfg = {
                "fbox": {
                    "address": "https://fbox360.com",
                    "client_id": "",
                    "client_secret": "",
                },
                "server": {"host": "0.0.0.0", "port": 5000},
            }
        cfg.setdefault("fbox", {})
        cfg.setdefault("server", {})
        cfg["fbox"]["address"] = os.environ.get("FBOX_ADDRESS", cfg["fbox"].get("address", "https://fbox360.com"))
        cfg["fbox"]["client_id"] = os.environ.get("FBOX_CLIENT_ID", cfg["fbox"].get("client_id", ""))
        cfg["fbox"]["client_secret"] = os.environ.get("FBOX_CLIENT_SECRET", cfg["fbox"].get("client_secret", ""))
        cfg["fbox"]["login_mode"] = os.environ.get("FBOX_LOGIN_MODE", cfg["fbox"].get("login_mode", "client_credentials"))
        cfg["fbox"]["box_id"] = cfg["fbox"].get("box_id", [])
        if not isinstance(cfg["fbox"]["box_id"], list):
            cfg["fbox"]["box_id"] = [cfg["fbox"]["box_id"]] if cfg["fbox"]["box_id"] else []
        cfg["fbox"]["data_points"] = cfg["fbox"].get("data_points", {})
        cfg["server"]["host"] = os.environ.get("SERVER_HOST", cfg["server"].get("host", "0.0.0.0"))
        cfg["server"]["port"] = int(os.environ.get("SERVER_PORT", str(cfg["server"].get("port", 5000))))
        cfg.setdefault("user", {})
        cfg.setdefault("mqtt", {})
        cfg["user"]["name"] = os.environ.get("FBOX_USER_NAME", cfg["user"].get("name", ""))
        cfg["user"]["password"] = os.environ.get("FBOX_USER_PASSWORD", cfg["user"].get("password", ""))
        return cfg
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("fbox", {})
    cfg.setdefault("server", {})
    cfg.setdefault("user", {})
    cfg["fbox"]["address"] = os.environ.get("FBOX_ADDRESS", cfg["fbox"].get("address", "https://fbox360.com"))
    cfg["fbox"]["client_id"] = os.environ.get("FBOX_CLIENT_ID", cfg["fbox"].get("client_id", ""))
    cfg["fbox"]["client_secret"] = os.environ.get("FBOX_CLIENT_SECRET", cfg["fbox"].get("client_secret", ""))
    cfg["fbox"]["login_mode"] = os.environ.get("FBOX_LOGIN_MODE", cfg["fbox"].get("login_mode", "client_credentials"))
    cfg["fbox"]["box_id"] = cfg["fbox"].get("box_id", [])
    if not isinstance(cfg["fbox"]["box_id"], list):
        cfg["fbox"]["box_id"] = [cfg["fbox"]["box_id"]] if cfg["fbox"]["box_id"] else []
    cfg["fbox"]["data_points"] = cfg["fbox"].get("data_points", {})
    cfg["server"]["host"] = os.environ.get("SERVER_HOST", cfg["server"].get("host", "0.0.0.0"))
    cfg["server"]["port"] = int(os.environ.get("SERVER_PORT", str(cfg["server"].get("port", 5000))))
    cfg.setdefault("mqtt", {})
    cfg["user"]["name"] = os.environ.get("FBOX_USER_NAME", cfg["user"].get("name", ""))
    cfg["user"]["password"] = os.environ.get("FBOX_USER_PASSWORD", cfg["user"].get("password", ""))
    return cfg


# Load translation dict from pickle on module load (or generate from translation.json and write pickle)
_load_translation_dict()
