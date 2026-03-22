# Fetch history from 2026-03-02 to 2026-03-16 and write to 3.2_3.16history.csv with English headers

import sys
import csv
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config_loader import load_config, get_data_points_for_api, translate_to_english
from lib.fbox_login import get_token
from lib.fbox_client import get_box_data_points_history

# Fixed range: 2026-03-02 00:00:00 ~ 2026-03-16 23:59:59 (local time)
START = datetime(2026, 3, 2, 0, 0, 0)
END = datetime(2026, 3, 16, 23, 59, 59)
OUTPUT_CSV = ROOT / "3.2_3.16history.csv"


def main():
    cfg = load_config()
    box_ids = cfg.get("fbox", {}).get("box_id", [])
    if not box_ids:
        print("fbox.box_id is empty in config, cannot fetch history")
        return
    box_no = box_ids[0] if isinstance(box_ids, list) else box_ids

    token_cache = {}
    token, address = get_token(load_config, token_cache, force_refresh=False, abort_on_fail=False)
    if not token:
        print("FBox login failed, check fbox and user in config")
        return

    dp = get_data_points_for_api(box_no)
    if not dp:
        print(f"box_no={box_no} data_points not configured in config (need group and points)")
        return
    group_name = dp["group"]
    point_names = dp["point_names"]

    begin_ms = int(START.timestamp() * 1000)
    end_ms = int(END.timestamp() * 1000)
    print(f"Fetching history: {START.isoformat()} ~ {END.isoformat()} (box={box_no})")

    err, flat_list, msg = get_box_data_points_history(
        address, token, box_no, begin_ms, end_ms,
        group_name, point_names,
        limit=-5000,
        time_zone="Asia/Shanghai",
        time_boundary_type=3,
        g=2,
    )
    if err != 200:
        print(f"Fetch failed: {msg}")
        return
    if not flat_list:
        print("No data, skipping CSV write")
        return

    # Translate name to English for CSV headers
    for item in flat_list:
        item["name_en"] = translate_to_english(item.get("name", ""))

    # Pivot to wide table: rows=time, columns=time, series1, series2, ...
    from collections import defaultdict
    time_to_values = defaultdict(dict)
    names_en = set()
    for item in flat_list:
        t = item.get("time")
        name_en = item.get("name_en", "unknown")
        val = item.get("value")
        if t is None:
            continue
        names_en.add(name_en)
        if name_en not in time_to_values[t]:
            time_to_values[t][name_en] = val
        else:
            time_to_values[t][name_en] = val

    names_en = sorted(names_en)
    rows = []
    for t_ms in sorted(time_to_values.keys()):
        row = {"time": datetime.fromtimestamp(t_ms / 1000.0).strftime("%Y-%m-%d %H:%M:%S")}
        for n in names_en:
            row[n] = time_to_values[t_ms].get(n, "")
        rows.append(row)

    headers = ["time"] + names_en
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} rows -> {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
