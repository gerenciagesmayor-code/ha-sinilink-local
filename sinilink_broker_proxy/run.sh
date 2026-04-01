#!/bin/sh
set -e

# Carga opciones del add-on desde /data/options.json de forma segura.
# Si algo falla, usa defaults y no rompe el arranque.
if [ -f /data/options.json ]; then
  python3 - <<'PY' > /tmp/sinilink_env.sh || true
import json
from pathlib import Path

defaults = {
    "mqtt_host": "127.0.0.1",
    "mqtt_port": 1883,
    "mqtt_user": "",
    "mqtt_password": "",
    "ha_host_ip": "192.168.1.121",
    "discovery_interval": 300,
    "poll_interval": 30,
    "scan_start_ip": "",
    "scan_end_ip": "",
}
try:
    data = json.loads(Path("/data/options.json").read_text(encoding="utf-8"))
except Exception:
    data = {}

for k, v in defaults.items():
    data.setdefault(k, v)

mapping = {
    "mqtt_host": "MQTT_HOST",
    "mqtt_port": "MQTT_PORT",
    "mqtt_user": "MQTT_USER",
    "mqtt_password": "MQTT_PASSWORD",
    "ha_host_ip": "HA_HOST_IP",
    "discovery_interval": "DISCOVERY_INTERVAL",
    "poll_interval": "POLL_INTERVAL",
    "scan_start_ip": "SCAN_START_IP",
    "scan_end_ip": "SCAN_END_IP",
}

for k, env_name in mapping.items():
    value = str(data.get(k, "")).replace("'", "'\"'\"'")
    print(f"export {env_name}='{value}'")
PY
  . /tmp/sinilink_env.sh
fi

export MQTT_HOST="${MQTT_HOST:-127.0.0.1}"
export MQTT_PORT="${MQTT_PORT:-1883}"
export MQTT_USER="${MQTT_USER:-}"
export MQTT_PASSWORD="${MQTT_PASSWORD:-}"
export HA_HOST_IP="${HA_HOST_IP:-192.168.1.121}"
export DISCOVERY_INTERVAL="${DISCOVERY_INTERVAL:-300}"
export POLL_INTERVAL="${POLL_INTERVAL:-30}"
export SCAN_START_IP="${SCAN_START_IP:-}"
export SCAN_END_IP="${SCAN_END_IP:-}"

echo "[sinilink] MQTT_HOST=${MQTT_HOST} MQTT_PORT=${MQTT_PORT} HA_HOST_IP=${HA_HOST_IP}"
echo "[sinilink] DISCOVERY_INTERVAL=${DISCOVERY_INTERVAL} POLL_INTERVAL=${POLL_INTERVAL}"

exec python3 /app/sinilink_broker_proxy.py
