# DK2500 Deployment

This guide describes the conservative manual setup path for the DK2500.

## 1. Clone the Repository

```bash
git clone <repo-url>
cd xiao-an-robot
```

## 2. Check the Environment

```bash
bash scripts/check_env.sh
```

## 3. Create the Base Station Virtual Environment

```bash
cd base_station
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd ..
```

## 4. Create the Agent Virtual Environment

```bash
cd agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd ..
```

## 5. Initialize SQLite

```bash
bash scripts/init_db.sh
```

This creates `agent/data/xiao_an.db` from `agent/data/schema.sql`.

## 6. Start the Base Station

```bash
bash scripts/start_base_station.sh
```

The script enters `base_station/` and starts the server with:

```bash
python -m ws_server.server
```

## 7. Start the Agent

Open a second terminal:

```bash
bash scripts/start_agent.sh
```

## 8. Start the Mock Robot

Open a third terminal:

```bash
bash scripts/run_mock_robot.sh
```

The mock robot connects to `/control`, sends `device.hello`, and keeps sending heartbeats. Use it before the real ESP32 firmware is ready.
