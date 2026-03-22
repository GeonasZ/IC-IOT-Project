# IoT FBox Frontend + Backend

Fetch **realtime** and **history** data from FBox cloud, expose APIs via a local Python backend, with a simple frontend page.

## Project structure

```
Project/
├── entrance.py          # Entry: start combined backend + frontend
├── config.example.json  # Config example (copy to config.json and fill)
├── config.json          # Config file (use this name only; do not commit)
├── lib/                 # Local lib: FBox data API
│   ├── __init__.py
│   └── fbox_client.py   # Login, realtime, history, box list
├── backend/             # Backend
│   ├── __init__.py
│   ├── config_loader.py # Load config / env vars
│   └── app.py           # Flask API + static frontend
└── frontend/
    └── static/          # Frontend static assets
        └── index.html   # Simple debug page
```

## How to run

1. **Config**  
   Use **config.json** as the config file. Copy `config.example.json` to `config.json` and fill:
   - `fbox`: `address`, `client_id`, `client_secret`, **`login_mode`**, **`box_id`** (list of box IDs)
   - **`login_mode`**: login method, one of:
     - `"client_credentials"`: method 1, developer account from Manager, client_id/client_secret only
     - `"password"`: method 2, developer account from sales, FBox client username/password; set `user.name`, `user.password`
   - `user`: `name`, `password` (required when `login_mode` is `"password"`)
   - **`mqtt`** (optional): per-box MQTT for frontend "Live MQTT" chart. Example:
     ```json
     "mqtt": {
       "301525111298": {
         "broker": "101.227.40.126",
         "broker_port": 1883,
         "client_id": "ZhiyangGao",
         "sub_topic": "301525111298/ZhiyangGao/Gexin/",
         "username": "ZhiyangGao",
         "password": "ZhiyangGao"
       }
     }
     ```
     Subscribes to all topics under `sub_topic` (`sub_topic#`); data is cached on the backend, frontend polls every second for the chart.
   Env vars can override: `FBOX_ADDRESS`, `FBOX_CLIENT_ID`, `FBOX_CLIENT_SECRET`, `FBOX_LOGIN_MODE`, `FBOX_USER_NAME`, `FBOX_USER_PASSWORD`.

2. **Install dependencies**  
   ```bash
   pip install flask requests paho-mqtt
   ```

3. **Start server**  
   ```bash
   python entrance.py
   ```

4. Open **http://127.0.0.1:5000** in a browser for the frontend, or call APIs directly:
   - `POST /api/realtime/get` — realtime data
   - `POST /api/history/get` — history data
   - `GET /api/boxes/list_box_id` — box_id list from config (no FBox API)
   - `POST /api/boxes/location` — box locations
   - `POST /api/mqtt/subscribe` — connect and subscribe MQTT for current box (body: `{ "box_id": "xxx" }`)
   - `GET /api/mqtt/stream?box_id=xxx` — get MQTT cached data for that box (for chart)
   - `POST /api/mqtt/unsubscribe` — disconnect MQTT
