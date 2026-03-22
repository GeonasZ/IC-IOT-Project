# FBox login: mode 1 client_credentials / mode 2 password; token cache and decorator
# Docs: https://docs.flexem.net/fbox/zh-cn/tutorials/Login.html
# Used by backend, scripts, etc.

from functools import wraps
from typing import Optional, Callable, Any, Dict

import requests

# Mode 1 (Manager): scope=fbox, grant_type=client_credentials
# Mode 2 (sales): scope=openid offline_access fbox email profile, grant_type=password
FBOX_SCOPE_CLIENT_CREDENTIALS = "fbox"
FBOX_SCOPE_PASSWORD = "openid offline_access fbox email profile"

LOGIN_MODE_CLIENT_CREDENTIALS = "client_credentials"
LOGIN_MODE_PASSWORD = "password"


def login_client_credentials(address: str, client_id: str, client_secret: str) -> str:
    """
    Mode 1: Developer account created in Manager; use client_id + client_secret to get token.
    """
    body = {
        "scope": FBOX_SCOPE_CLIENT_CREDENTIALS,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": LOGIN_MODE_CLIENT_CREDENTIALS,
    }
    ans = requests.post(f"{address}/idserver/core/connect/token", data=body).json()
    return ans["access_token"]


def login_password(
    address: str,
    client_id: str,
    client_secret: str,
    username: str,
    password: str,
) -> str:
    """
    Mode 2: Developer account from sales; login with FBox client username/password.
    """
    body = {
        "username": username,
        "password": password,
        "scope": FBOX_SCOPE_PASSWORD,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": LOGIN_MODE_PASSWORD,
    }
    ans = requests.post(f"{address}/idserver/core/connect/token", data=body).json()
    return ans["access_token"]


def login(
    address: str,
    client_id: str,
    client_secret: str,
    login_mode: str = LOGIN_MODE_CLIENT_CREDENTIALS,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> str:
    """
    Choose login method by login_mode.
    If login_mode is "password" and username/password provided, use mode 2; else mode 1 (client_credentials).
    """
    if login_mode == LOGIN_MODE_PASSWORD and username and password:
        return login_password(address, client_id, client_secret, username, password)
    return login_client_credentials(address, client_id, client_secret)


# ---------- Token cache and decorator (depends on get_config and token_cache) ----------


def _has_user_credentials(full_cfg: dict) -> bool:
    """Whether config has username and password set."""
    user = full_cfg.get("user") or {}
    return bool(user.get("name") and user.get("password"))


def get_token(
    get_config: Callable[[], dict],
    token_cache: Dict[str, Any],
    force_refresh: bool = False,
    abort_on_fail: bool = True,
):
    """
    Get or refresh FBox access token (writes to token_cache).
    :param get_config: no-arg callable returning full config dict
    :param token_cache: mutable dict for token/address, e.g. {"token": None, "address": None}
    :return: (token, address); on failure (None, address); if abort_on_fail then raise 401
    """
    cfg = get_config().get("fbox", {})
    address = cfg.get("address", "")
    client_id = cfg.get("client_id", "")
    client_secret = cfg.get("client_secret", "")
    login_mode = (cfg.get("login_mode") or "client_credentials").strip().lower()
    user = get_config().get("user") or {}
    username = user.get("name") or ""
    password = user.get("password") or ""
    if not client_id or not client_secret:
        return None, None
    if login_mode == LOGIN_MODE_PASSWORD and (not username or not password):
        return None, None
    if not force_refresh and token_cache.get("token"):
        return token_cache["token"], token_cache.get("address") or address
    try:
        token = login(
            address, client_id, client_secret,
            login_mode=login_mode,
            username=username or None, password=password or None,
        )
        token_cache["token"] = token
        token_cache["address"] = address
        return token, address
    except Exception:
        token_cache["token"] = None
        token_cache["address"] = address
        if abort_on_fail:
            try:
                from flask import abort
                abort(401, description="FBox login failed, unauthorized")
            except Exception:
                pass
        return None, address


def ensure_token(get_config: Callable[[], dict], token_cache: Dict[str, Any]):
    """Re-login if current token invalid; return (token, address) or (None, address)."""
    return get_token(get_config, token_cache, force_refresh=False, abort_on_fail=True)


def with_fbox_token(get_config: Callable[[], dict], token_cache: Dict[str, Any]):
    """Decorator: inject token/address; return 503 when no token; on 401 with credentials, retry once after re-login."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            try:
                from flask import jsonify
            except Exception:
                jsonify = lambda x: x
            token, address = ensure_token(get_config, token_cache)
            if not token:
                return jsonify({"info": "FBox not configured or login failed; check config.json fbox.client_id / client_secret"}), 503
            result = f(token, address, *args, **kwargs)
            if isinstance(result, tuple) and len(result) >= 2 and result[1] == 401 and _has_user_credentials(get_config()):
                token, address = get_token(get_config, token_cache, force_refresh=True, abort_on_fail=False)
                result = f(token, address, *args, **kwargs)
            return result
        return wrapped
    return decorator
