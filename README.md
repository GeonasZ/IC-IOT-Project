# IoT FBox Frontend + Backend

Fetch **realtime** and **history** data from FBox cloud, expose APIs via a local Python backend, with a simple frontend page.

## Project structure

```
Project/
├── entrance.py              # Entry: Flask server (API + static frontend)
├── pyproject.toml           # uv / project metadata
├── uv.lock
├── requirements.txt         # pip fallback
├── config.json              # Local FBox / MQTT / server config (do not commit)
├── 3.2_3.16history.csv      # Sample history for the fixed-range chart API
├── get_history.py           # Helper script to pull history (optional)
├── main.py                  # Placeholder, not in used
├── backend/
│   ├── app.py               # Flask routes: FBox, MQTT, history chart, analysis
│   ├── config_loader.py     # Load config, data points, etc
│   ├── mqtt_box.py          # MQTT client, subscribe, etc
│   └── analysis.py          # Correlation / matrix helpers for /api/analysis/run
├── lib/
│   ├── fbox_login.py        # Token acquisition / refresh
│   └── fbox_client.py       # FBox realtime, history, box / dmon APIs
└── frontend/
    └── static/
        └── index.html       # Dashboard (charts, MQTT live, water quality UI)
```

## How to run

1. **Install dependencies**  
  **uv** is suggested to be used for virtual environment management. Synchronize your local venv with: 
  ```bash
   uv sync
  ```
  Or alternatively, installing dependencies with pip:
  ```bash
   pip install -r requirements.txt
  ```
2. **Start server**
  ```bash
   python entrance.py
  ```
3. Open **[http://127.0.0.1:5000](http://127.0.0.1:5000)** in a browser for the frontend.

