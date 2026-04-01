#!/usr/bin/with-contenv bashio
set -e

export MQTT_HOST="$(bashio::config 'mqtt_host')"
export MQTT_PORT="$(bashio::config 'mqtt_port')"
export MQTT_USER="$(bashio::config 'mqtt_user')"
export MQTT_PASSWORD="$(bashio::config 'mqtt_password')"
export HA_HOST_IP="$(bashio::config 'ha_host_ip')"
export DISCOVERY_INTERVAL="$(bashio::config 'discovery_interval')"
export POLL_INTERVAL="$(bashio::config 'poll_interval')"
export SCAN_START_IP="$(bashio::config 'scan_start_ip')"
export SCAN_END_IP="$(bashio::config 'scan_end_ip')"

echo "[sinilink] MQTT_HOST=${MQTT_HOST} MQTT_PORT=${MQTT_PORT} HA_HOST_IP=${HA_HOST_IP}"
echo "[sinilink] DISCOVERY_INTERVAL=${DISCOVERY_INTERVAL} POLL_INTERVAL=${POLL_INTERVAL}"

exec python3 /app/sinilink_broker_proxy.py
