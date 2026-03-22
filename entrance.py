# Project entry: start combined backend + frontend (Flask API + static frontend)

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config_loader import load_config
from backend.app import app, get_token
from lib.fbox_client import get_box_groups_and_data_points


def main():
    cfg = load_config()
    # To fetch and print monitor point groups for a box at startup, get token then call (no with_fbox_token)
    token, address = get_token(abort_on_fail=False)
    # if token and cfg.get("fbox", {}).get("box_id"):
        # box_no = cfg["fbox"]["box_id"][0] if isinstance(cfg["fbox"]["box_id"], list) else cfg["fbox"]["box_id"]
        # get_box_groups_and_data_points(address, token, box_no)
    host = cfg["server"]["host"]
    port = cfg["server"]["port"]
    print(f"Server: http://{host}:{port}")
    if host == "0.0.0.0":
        print("Local: http://localhost:{port} or http://127.0.0.1:{port}".format(port=port))
    print("API: /api/realtime/get, /api/history/get, /api/boxes/list, /api/boxes/list_box_id, /api/boxes/location")
    app.run(host=host, port=port, debug=True)


if __name__ == "__main__":
    main()
