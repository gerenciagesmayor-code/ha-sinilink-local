#!/bin/sh
set -e

export MQTT_HOST="${MQTT_HOST:-127.0.0.1}"
export MQTT_PORT="${MQTT_PORT:-1883}"
export MQTT_USER="${MQTT_USER:-}"
export MQTT_PASSWORD="${MQTT_PASSWORD:-}"
export HA_HOST_IP="${HA_HOST_IP:-192.168.1.121}"
export DISCOVERY_INTERVAL="${DISCOVERY_INTERVAL:-300}"
export POLL_INTERVAL="${POLL_INTERVAL:-30}"

exec python3 /app/sinilink_broker_proxy.py
