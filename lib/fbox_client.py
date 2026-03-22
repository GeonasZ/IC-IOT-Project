# FBox cloud API: realtime data, history, box info
# Login logic in lib.fbox_login; this file only re-exports for compatibility

import copy
import requests
from datetime import datetime
from typing import Union, List, Dict, Optional

from lib.fbox_login import (
    login,
    login_client_credentials,
    login_password,
    FBOX_SCOPE_CLIENT_CREDENTIALS,
    FBOX_SCOPE_PASSWORD,
    LOGIN_MODE_CLIENT_CREDENTIALS,
    LOGIN_MODE_PASSWORD,
)

# ---------- Realtime data ----------


def _read_realtime_data(
    address: str, token: str, box_id: str, request: List[Dict]
) -> tuple:
    """Request realtime data for given points; returns raw values (no gain/offset transform)."""
    group_names = []
    names = []
    for group in request:
        group_names.extend([group["name"]] * len(group["points"]))
        names.extend(group["points"])

    headers = {"Authorization": f"Bearer {token}"}
    body = {"names": names, "groupNames": group_names, "timeOut": 5000}
    ans = requests.post(
        f"{address}/api/v2/dmon/value/get?boxNo={box_id}", headers=headers, json=body
    )

    if ans.status_code == 200:
        ans = ans.json()
        construct_obj = []
        for i in range(len(group_names)):
            if construct_obj == [] or construct_obj[-1]["name"] != group_names[i]:
                if ans[i] is not None:
                    construct_obj.append(
                        {
                            "name": group_names[i],
                            "points": [{"name": names[i], "value": ans[i]["value"]}],
                        }
                    )
                else:
                    construct_obj.append(
                        {
                            "name": group_names[i],
                            "points": [{"name": names[i], "value": None}],
                        }
                    )
            else:
                if ans[i] is not None:
                    construct_obj[-1]["points"].append(
                        {"name": names[i], "value": ans[i]["value"]}
                    )
                else:
                    construct_obj[-1]["points"].append(
                        {"name": names[i], "value": None}
                    )
        return 200, construct_obj, "Success."
    elif ans.status_code == 401:
        return 401, None, "Access token expired."
    return 400, None, "Unknown Error."


def _read_realtime_params_from_box(
    address: str, token: str, box_id: str
) -> tuple:
    """Get all realtime point definitions for one box (unit, gain, offset)."""
    headers = {"Authorization": f"Bearer {token}"}
    params = {"boxNo": box_id}
    ans = requests.get(
        f"{address}/api/v2/box/dmon/grouped", headers=headers, params=params
    )
    if ans.status_code == 200:
        return 200, ans.json(), "Success."
    elif ans.status_code == 401:
        return 401, None, "Access token expired."
    return 400, None, "Unknown Error."


def _get_realtime_value_transform_and_unit(
    address: str, token: str, box_id: str, request: List[Dict]
) -> tuple:
    """Get unit and valueTransform (gain/offset) for realtime points."""
    box_params = _read_realtime_params_from_box(address, token, box_id)
    if box_params[0] == 401:
        return 401, None, "Token Expired."
    if box_params[0] != 200:
        return 400, None, "Unknown Error."
    box_params = box_params[1]
    request = copy.deepcopy(request)
    for i in range(len(request)):
        for cat in box_params:
            if request[i]["name"] == cat["name"]:
                for j in range(len(request[i]["points"])):
                    for k in range(len(cat["items"])):
                        if cat["items"][k]["name"] == request[i]["points"][j]:
                            request[i]["points"][j] = {}
                            request[i]["points"][j]["unit"] = cat["items"][k].get(
                                "unit", ""
                            )
                            request[i]["points"][j]["gain"] = cat["items"][k][
                                "valueTransform"
                            ]["gain"]
                            request[i]["points"][j]["offset"] = cat["items"][k][
                                "valueTransform"
                            ]["offset"]
                            if request[i]["points"][j]["gain"] == 0:
                                request[i]["points"][j]["gain"] = 1
                            break
                break
    return 200, request, "Success."


def read_realtime_data(
    address: str, token: str, box_id: str, request: List[Dict]
) -> tuple:
    """
    Get FBox realtime data (public API). Applies gain/offset and attaches unit.
    :param address: cloud base URL
    :param token: access_token
    :param box_id: box boxNo
    :param request: point request, format [{"name": "group name", "points": ["point1", "point2"]}, ...]
    :return: (status_code, data list or None, message)
    """
    data = _read_realtime_data(address, token, box_id, request)
    params = _get_realtime_value_transform_and_unit(
        address, token, box_id, request
    )
    if data[0] == 200 and params[0] == 200:
        data = copy.deepcopy(data[1])
        params = params[1]
        for i in range(len(data)):
            for j in range(len(data[i]["points"])):
                if not isinstance(params[i]["points"][j], dict):
                    params[i]["points"][j] = {"gain": 1, "offset": 0, "unit": ""}
                if data[i]["points"][j]["value"] is not None:
                    data[i]["points"][j]["value"] = (
                        data[i]["points"][j]["value"] * params[i]["points"][j]["gain"]
                        + params[i]["points"][j]["offset"]
                    )
                    data[i]["points"][j]["unit"] = params[i]["points"][j]["unit"]
                else:
                    data[i]["points"][j]["value"] = None
                    data[i]["points"][j]["unit"] = ""
        return 200, data, "Success"
    if data[0] == 401 or params[0] == 401:
        return 401, None, "Token Expired."
    return 400, None, "Unknown Error."


# ---------- History data ----------


def _get_history_params(
    address: str,
    token: str,
    box_id: str,
    request_channel_names: Union[None, List[Dict]] = None,
) -> tuple:
    """Get history channel params; if request_channel_names given, resolve channel uid."""
    headers = {"Authorization": f"Bearer {token}"}
    ans = requests.get(
        f"{address}/api/v2/hdataitems?boxNo={box_id}", headers=headers
    )
    if ans.status_code == 401:
        return 401, ans, "Access token expired."
    if ans.status_code == 200:
        if request_channel_names is None:
            return 200, ans.json(), "Success."
        request_channel_names = copy.deepcopy(request_channel_names)
        ans = ans.json()
        for i in range(len(request_channel_names)):
            for cat in ans:
                if request_channel_names[i]["name"] == cat["name"]:
                    for j in range(len(request_channel_names[i]["channels"])):
                        for k in range(len(cat["channels"])):
                            if (
                                cat["channels"][k]["name"]
                                == request_channel_names[i]["channels"][j]
                            ):
                                request_channel_names[i]["channels"][j] = cat[
                                    "channels"
                                ][k]["uid"]
                                break
                    break
        return 200, ans, "Success.", request_channel_names
    try:
        err_body = ans.json() if ans.headers.get("content-type", "").startswith("application/json") else {}
        detail = err_body.get("error_description") or err_body.get("message") or ans.text[:200] or "Unknown Error."
    except Exception:
        detail = "Unknown Error."
    return 400, ans, detail


def boxes_get_history_params(
    address: str, token: str, boxes_request: List[Dict]
) -> tuple:
    """
    Batch get history channel params for multiple boxes (resolve channel names to uid).
    boxes_request: [{"box_id": "xxx", "request": [{"name": "group name", "channels": ["ch1", "ch2"]}]}, ...]
    """
    boxes_request = copy.deepcopy(boxes_request)
    for i in range(len(boxes_request)):
        ans = _get_history_params(
            address, token, boxes_request[i]["box_id"], boxes_request[i]["request"]
        )
        if len(ans) == 4 and ans[0] == 200:
            boxes_request[i]["request"] = ans[3]
        elif ans[0] == 401:
            return 401, None, "Token Expired."
        else:
            return 400, None, ans[2] if len(ans) > 2 else "Failed to get history channel params; ensure group/channel names exist for this box"
    return 200, boxes_request, "Success."


def get_history_data_by_list(
    address: str,
    token: str,
    channel_ids: list,
    channel_names: list,
    begin: int,
    end: int,
    limit: int = -500,
    time_zone: str = "Asia/Shanghai",
    time_boundary_type: int = 3,
    g: int = 2,
) -> tuple:
    """
    Fetch history by channel id list.
    :param begin/end: ms timestamp (since 1970-01-01)
    :param limit: max rows per request, default -500, max 1000
    :param time_boundary_type: tr, 0 open-open 1 open-close 2 close-open 3 close-close
    :param g: aggregation, 0 raw 1 min 2 hour 3 day; default 2 (hourly)
    """
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "type": 0,
        "format": 0,
        "ids": [str(cid) for cid in channel_ids],
        "names": channel_names,
        "g": g,
        "begin": begin,
        "end": end,
        "tr": time_boundary_type,
        "limit": limit,
        "tz": time_zone,
    }
    ans = requests.post(
        f"{address}/hs/v2/hdata/get", headers=headers, json=body
    )
    if ans.status_code == 401:
        return 401, None, "Access token expired."
    if ans.status_code == 429:
        return 429, None, "API access too fast."
    if ans.status_code == 200:
        return 200, ans.json(), "Success."
    try:
        err_body = ans.json() if ans.headers.get("content-type", "").startswith("application/json") else {}
        detail = err_body.get("error_description") or err_body.get("message") or ans.text[:200] or "Unknown Error."
    except Exception:
        detail = "Unknown Error."
    return 400, None, detail


def get_history_data_by_request(
    address: str,
    token: str,
    boxes_request: list,
    begin: int,
    end: int,
    limit: int = -500,
    time_zone: str = "Asia/Shanghai",
    time_boundary_type: int = 3,
    g: int = 2,
) -> tuple:
    """
    Fetch history by structured request (public API).
    boxes_request format same as boxes_get_history_params; channels can be names, resolved to uid internally.
    g: 0 raw 1 min 2 hour 3 day, default 2 (hourly).
    """
    boxes_request = copy.deepcopy(boxes_request)
    err, request_params_tree, msg = boxes_get_history_params(
        address, token, boxes_request
    )
    if err != 200:
        if err == 401:
            return 401, None, msg or "Token expired."
        return 400, None, msg or "Failed to get history channel params; check group/channel names and history collection config"

    channel_ids = []
    channel_names = []
    for box in request_params_tree:
        for group in box["request"]:
            channel_ids.extend(group["channels"])
    for box in boxes_request:
        for group in box["request"]:
            for name in group["channels"]:
                channel_names.append(
                    box["box_id"] + ">" + group["name"] + ">" + name
                )

    err, data, msg = get_history_data_by_list(
        address,
        token,
        channel_ids,
        channel_names,
        begin,
        end,
        limit,
        time_zone,
        time_boundary_type,
        g=g,
    )
    if err != 200:
        if err == 401:
            return 401, None, msg or "Token expired."
        return 400, None, msg or "History query failed; check time range and channel config"
    data["names"] = channel_names
    return 200, data, "Success."


def history_flatten(data: Dict) -> list:
    """
    Convert history API rows to flat list.
    Each item: {"name": "box_id>group>channel", "time": timestamp, "value": value}
    """
    result_list = []
    names = data["names"]
    rows = data["rows"]
    for i in range(len(names)):
        for j in range(len(rows)):
            temp = {
                "name": names[i],
                "time": rows[j]["t"],
                "value": rows[j]["c"][i],
            }
            result_list.append(temp)
    return result_list


# ---------- Box info ----------


def get_box_single(address: str, token: str, box_no: str) -> tuple:
    """
    Get single box info by box number.
    Docs: https://docs.flexem.net/fbox/zh-cn/tutorials/GetSingleFBox.html
    URL2: POST /api/client/v2/box/single, body: {"boxNo": box_no}
    :return: (200, box info dict, "Success.") or (401/404/400, None, message)
    """
    headers = {"Authorization": f"Bearer {token}"}
    body = {"boxNo": box_no}
    ans = requests.post(
        f"{address}/api/client/v2/box/single",
        headers=headers,
        json=body,
    )
    if ans.status_code == 200:
        return 200, ans.json(), "Success."
    if ans.status_code == 401:
        return 401, None, "Access token expired."
    if ans.status_code == 404:
        return 404, None, "Box not found"
    try:
        err_body = ans.json() if ans.headers.get("content-type", "").startswith("application/json") else {}
        detail = err_body.get("error_description") or err_body.get("message") or (ans.text or "")[:200]
    except Exception:
        detail = "Unknown Error."
    return 400, None, detail or "Unknown Error."


def get_dmon_groups(address: str, token: str, box_no: str) -> tuple:
    """
    Get monitor point group list for the given box.
    Docs: https://docs.flexem.net/fbox/zh-cn/tutorials/GetMonitoryPointGroup.html
    URL2: GET [Host Server]/api/v2/box/dmon/groups?boxNo={boxNo}
    :param box_no: FBox serial number (boxNo)
    :return: (200, [{ id, name }, ...], "Success.") or (401/404/429/400, None, message)
    """
    headers = {"Authorization": f"Bearer {token}"}
    ans = requests.get(
        f"{address}/api/v2/box/dmon/groups",
        headers=headers,
        params={"boxNo": box_no},
    )
    if ans.status_code == 200:
        data = ans.json()
        return 200, data if isinstance(data, list) else [], "Success."
    if ans.status_code == 401:
        return 401, None, "Access token expired."
    if ans.status_code == 404:
        return 404, None, "API or box not found"
    if ans.status_code == 429:
        return 429, None, "Too many requests"
    try:
        err_body = ans.json() if ans.headers.get("content-type", "").startswith("application/json") else {}
        detail = err_body.get("error_description") or err_body.get("message") or (ans.text or "")[:200]
    except Exception:
        detail = "Unknown Error."
    return 400, None, detail or "Unknown Error."


def get_dmon_by_group(
    address: str,
    token: str,
    box_id: str,
    group_id: str,
    client_id: Optional[str] = None,
) -> tuple:
    """
    Get monitor points (data points) for the given group.
    Docs: https://docs.flexem.net/fbox/zh-cn/tutorials/ReasonMonitoryPointGroupGetMonitoryPoint.html
    GET [Host Server]/api/v2/box/{boxId}/dmongroup/{groupId}/dmon
    :param box_id: box UID (id from get_box_single, not boxNo)
    :param group_id: monitor group id (from get_dmon_groups)
    :param client_id: optional, X-FBox-ClientId, required in some envs
    :return: (200, monitor point list, "Success.") or (401/400/404/429, None, message)
    """
    headers = {"Authorization": f"Bearer {token}"}
    if client_id:
        headers["X-FBox-ClientId"] = client_id
    ans = requests.get(
        f"{address}/api/v2/box/{box_id}/dmongroup/{group_id}/dmon",
        headers=headers,
    )
    if ans.status_code == 200:
        data = ans.json()
        return 200, data if isinstance(data, list) else [], "Success."
    if ans.status_code == 401:
        return 401, None, "Access token expired."
    if ans.status_code == 404:
        return 404, None, "API or group not found"
    if ans.status_code == 429:
        return 429, None, "Too many requests"
    if ans.status_code == 400:
        code = ans.headers.get("X-FBox-Code", "")
        detail = (code + " " + (ans.text or "")[:200]).strip() or "Request error"
        return 400, None, detail
    try:
        err_body = ans.json() if ans.headers.get("content-type", "").startswith("application/json") else {}
        detail = err_body.get("error_description") or err_body.get("message") or (ans.text or "")[:200]
    except Exception:
        detail = "Unknown Error."
    return 400, None, detail or "Unknown Error."


def get_box_groups_and_data_points(
    address: str, token: str, box_no: str
) -> Optional[Dict]:
    """
    Given a box number, get all monitor groups and for each group get all data points; print and return.
    :param address: cloud base URL
    :param token: access token
    :param box_no: box number (FBox serial boxNo)
    :return: {"groups": [...], "groups_with_points": [{"group": g, "points": [...]}, ...]}, or None on failure
    """
    err, box_info, msg = get_box_single(address, token, box_no)
    if err != 200 or not isinstance(box_info, dict):
        print(f"Failed to get box info: {msg}")
        return None
    box_id = box_info.get("id")
    if not box_id:
        print("Box info has no id field")
        return None

    err, groups, msg = get_dmon_groups(address, token, box_no)
    if err != 200:
        print(f"Failed to get groups: {msg}")
        return None
    if not groups:
        print(f"No monitor groups found for box {box_no}")
        return {"groups": [], "groups_with_points": []}

    print(f"Box {box_no} monitor groups ({len(groups)}):")
    for g in groups:
        print(f"  id: {g.get('id')}, name: {g.get('name')}")

    groups_with_points = []
    for g in groups:
        group_id = g.get("id")
        group_name = g.get("name")
        if not group_id:
            continue
        err, points, msg = get_dmon_by_group(address, token, box_id, group_id)
        if err != 200 or not isinstance(points, list):
            print(f"Group {group_name} failed to get data points: {msg}")
            groups_with_points.append({"group": g, "points": []})
            continue
        print(f"Group {group_name}({group_id}) data points ({len(points)}):")
        for p in points:
            print(f"  id: {p.get('id')}, name: {p.get('name')}")
        groups_with_points.append({"group": g, "points": points})

    return {"groups": groups, "groups_with_points": groups_with_points}


def get_box_data_points_history(
    address: str,
    token: str,
    box_no: str,
    begin: int,
    end: int,
    group_name: str,
    point_names: List[str],
    limit: int = -500,
    time_zone: str = "Asia/Shanghai",
    time_boundary_type: int = 3,
    g: int = 2,
) -> tuple:
    """
    Fetch history for data points configured in config (group name + point list); return flat list for frontend chart.
    g: 0 raw 1 min 2 hour 3 day, default 2 (hourly).
    :return: (200, flatten_list, "Success.") or (err, None, msg)
    """
    if not point_names:
        return 400, None, "point_names is empty"
    boxes_request = [
        {
            "box_id": box_no,
            "request": [{"name": group_name, "channels": point_names}],
        }
    ]
    err, data, msg = get_history_data_by_request(
        address,
        token,
        boxes_request,
        begin,
        end,
        limit=limit,
        time_zone=time_zone,
        time_boundary_type=time_boundary_type,
        g=g,
    )
    if err != 200 or not isinstance(data, dict):
        return err, None, msg or "Unknown Error."
    flat = history_flatten(data)
    return 200, flat, "Success."


def _get_all_boxes(address: str, token: str) -> tuple:
    """Get all boxes under account (grouped)."""
    headers = {"Authorization": f"Bearer {token}"}
    ans = requests.get(f"{address}/api/client/box/grouped", headers=headers)
    if ans.status_code == 200:
        return 200, ans.json(), "Success."
    if ans.status_code == 401:
        return 401, None, "Token Expired"
    return 400, None, "Unknown Error"


def flat_list_all_boxes(address: str, token: str) -> tuple:
    """Return flat list of all boxes; each item has box_name, box_id, box_No."""
    err, grouped_boxes, _ = _get_all_boxes(address, token)
    if err == 200:
        box_list = [
            {
                "box_name": box["alias"],
                "box_id": box["box"]["boxNo"],
                "box_No": box["box"]["id"],
            }
            for group in grouped_boxes
            for box in group["boxRegs"]
        ]
        return 200, box_list, "Success"
    if err == 401:
        return 401, None, "Token expired."
    return 400, None, "Unknown Error."


def grouped_list_all_boxes(address: str, token: str) -> tuple:
    """Return box list by group; each item has group_name, group_id, boxes."""
    err, grouped_boxes, _ = _get_all_boxes(address, token)
    if err == 200:
        box_list = []
        for group in grouped_boxes:
            box_list.append(
                {"group_name": group["name"], "group_id": group["id"], "boxes": []}
            )
            for box in group["boxRegs"]:
                box_list[-1]["boxes"].append(
                    {
                        "box_name": box["alias"],
                        "box_id": box["box"]["boxNo"],
                        "box_No": box["box"]["id"],
                    }
                )
        return 200, box_list, "Success"
    if err == 401:
        return 401, None, "Token expired."
    return 400, None, "Unknown Error."


def get_boxes_location(
    address: str, token: str, box_nos: List
) -> tuple:
    """Get location for given boxes. box_nos is list of box_No."""
    headers = {"Authorization": f"Bearer {token}"}
    body = {"ids": box_nos}
    ans = requests.post(
        f"{address}/api/client/v2/box/location", headers=headers, json=body
    )
    if ans.status_code == 200:
        data = ans.json()
        data = [
            {
                "box_No": box["boxId"],
                "longitude": box["longitude"],
                "latitude": box["latitude"],
                "address": box["address"],
            }
            for box in data
        ]
        return 200, data, "Success"
    if ans.status_code == 401:
        return 401, None, "Token expired."
    return 400, None, "Unknown Error."


# ---------- Utils ----------


def timestamp_ms(
    year=1970,
    month=1,
    day=1,
    hour=0,
    minute=0,
    second=0,
    microsecond=0,
) -> int:
    """Return ms timestamp for the given time."""
    return int(
        datetime(
            year, month, day, hour, minute, second, microsecond
        ).timestamp()
        * 1000
    )
