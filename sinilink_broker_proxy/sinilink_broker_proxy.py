#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Proxy broker Sinilink: intermediario entre termostatos XY-WFT1 y Home Assistant.
- Descubre dispositivos por broadcast UDP SINILINK521.
- Se conecta al Mosquitto local y se suscribe a APPWT# (comandos de termostatos).
- Responde a find/findport/findisonline simulando el servidor Sinilink.
- Cuando llega un comando (stemp, swork, smode, spower): publica estado en HA y confirma en PROWT{MAC}.
- Polling cada 30 s por UDP; publica estado en HA y marca unavailable si no responde.
- Publica MQTT Discovery para cada dispositivo (climate).
Ejecutar en Home Assistant (add-on o /config/scripts). Requiere: paho-mqtt.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import sys
import threading
import time
from collections import defaultdict
from typing import Any

try:
    import paho.mqtt.client as mqtt
    PAHO_V2 = hasattr(mqtt, "CallbackAPIVersion")
except ImportError:
    print("Instalar paho-mqtt: pip install paho-mqtt")
    sys.exit(1)

# -----------------------------------------------------------------------------
# CONFIGURACIÓN (por defecto; puede sobreescribirse con variables de entorno)
# -----------------------------------------------------------------------------
MQTT_HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_WS_PORT = 8085       # Solo referencia; los termostatos conectan ahí
MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")

UDP_PORT = 1024
MAGIC = b"SINILINK521"
DISCOVERY_BROADCAST_INTERVAL = int(os.environ.get("DISCOVERY_INTERVAL", "300"))   # 5 min
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "30"))
# Rango opcional para escanear IPs directamente (además del broadcast)
SCAN_START_IP = os.environ.get("SCAN_START_IP") or ""
SCAN_END_IP = os.environ.get("SCAN_END_IP") or ""
UDP_TIMEOUT = 5
DISCOVERY_WAIT = 5        # Segundos recogiendo respuestas tras broadcast

HA_TOPIC_PREFIX = "homeassistant/climate/sinilink"
STATE_TOPIC_SUFFIX = "state"

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("sinilink_proxy")


def mac_col(mac: str) -> str:
    """Normalizar MAC con dos puntos: E8DB84493D50 -> E8:DB:84:49:3D:50"""
    m = (mac or "").replace(":", "").replace("-", "").upper()
    if len(m) != 12:
        return mac or ""
    return ":".join(m[i : i + 2] for i in range(0, 12, 2))


def mac_nocol(mac: str) -> str:
    """E8:DB:84:49:3D:50 -> E8DB84493D50"""
    return (mac or "").replace(":", "").replace("-", "").upper()


# -----------------------------------------------------------------------------
# UDP: descubrimiento y lectura de estado (JSON)
# -----------------------------------------------------------------------------
def parse_udp_json(data: bytes) -> dict[str, Any] | None:
    """Parsea respuesta JSON del termostato: {"MAC":"...", "time":..., "param":[...]}"""
    try:
        text = data.decode("utf-8", errors="replace").strip()
        return json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def udp_read_state(ip: str) -> dict[str, Any] | None:
    """Envía SINILINK521 a ip:1024 y devuelve el JSON parseado o None."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(UDP_TIMEOUT)
    try:
        sock.sendto(MAGIC, (ip, UDP_PORT))
        data, _ = sock.recvfrom(2048)
        return parse_udp_json(data)
    except (socket.timeout, OSError) as e:
        logger.debug("UDP read %s: %s", ip, e)
        return None
    finally:
        sock.close()


def _ip_to_int(ip: str) -> int | None:
    parts = ip.split(".")
    if len(parts) != 4:
        return None
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if any(n < 0 or n > 255 for n in nums):
        return None
    return (nums[0] << 24) | (nums[1] << 16) | (nums[2] << 8) | nums[3]


def _int_to_ip(value: int) -> str:
    return ".".join(str((value >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def udp_discovery() -> dict[str, str]:
    """Descubrimiento de termostatos.

    - Broadcast SINILINK521 a 255.255.255.255:1024.
    - Opcionalmente, escanea un rango SCAN_START_IP-SCAN_END_IP si se configura.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.5)
    result = {}
    try:
        sock.sendto(MAGIC, ("255.255.255.255", UDP_PORT))
        deadline = time.monotonic() + DISCOVERY_WAIT
        while time.monotonic() < deadline:
            try:
                data, addr = sock.recvfrom(2048)
                parsed = parse_udp_json(data)
                if parsed and parsed.get("MAC"):
                    mac = mac_col(parsed["MAC"])
                    result[mac] = addr[0]
            except socket.timeout:
                break
    finally:
        sock.close()

    # Escaneo adicional de rango explícito si está configurado
    start_int = _ip_to_int(SCAN_START_IP) if SCAN_START_IP else None
    end_int = _ip_to_int(SCAN_END_IP) if SCAN_END_IP else None
    if start_int is not None and end_int is not None and start_int <= end_int:
        logger.info(
            "Discovery extra scan: %s - %s", SCAN_START_IP, SCAN_END_IP
        )
        for value in range(start_int, end_int + 1):
            ip = _int_to_ip(value)
            parsed = udp_read_state(ip)
            if parsed and parsed.get("MAC"):
                mac = mac_col(parsed["MAC"])
                if mac and mac not in result:
                    result[mac] = ip

    return result


def state_from_param(param: list) -> dict[str, Any]:
    """Extrae estado HA desde param[] del JSON UDP. Índices según protocolo."""
    if not param or len(param) < 7:
        return {}
    relay = 1 if param[0] == 1 else 0
    mode = "A" if param[1] == "A" else "M"
    temp = float(param[3]) if len(param) > 3 else None
    unit = (param[4] or "C") if len(param) > 4 else "C"
    heat_cool = (param[5] or "H") if len(param) > 5 else "H"
    setpoint = float(param[6]) if len(param) > 6 else None
    return {
        "relay": relay,
        "mode": mode,
        "temperature": temp,
        "unit": unit,
        "heat_cool": heat_cool,
        "setpoint": setpoint,
        "hysteresis": float(param[7]) if len(param) > 7 else 0.5,
    }


# -----------------------------------------------------------------------------
# Estado en memoria y MQTT
# -----------------------------------------------------------------------------
class ProxyState:
    def __init__(self) -> None:
        self.mac_to_ip: dict[str, str] = {}
        self.lock = threading.Lock()
        self.last_state: dict[str, dict] = defaultdict(dict)

    def update_devices(self, mac_ip: dict[str, str]) -> None:
        with self.lock:
            self.mac_to_ip.update(mac_ip)

    def set_ip(self, mac: str, ip: str) -> None:
        with self.lock:
            self.mac_to_ip[mac] = ip

    def get_ip(self, mac: str) -> str | None:
        with self.lock:
            return self.mac_to_ip.get(mac)

    def devices(self) -> list[str]:
        with self.lock:
            return list(self.mac_to_ip.keys())


proxy_state = ProxyState()


def publish_ha_state(client: mqtt.Client, mac: str, st: dict[str, Any], available: bool) -> None:
    """Publica estado en topics de HA (temperatura, setpoint, modo, disponibilidad)."""
    uid = mac_nocol(mac)
    base = f"{HA_TOPIC_PREFIX}_{uid}"
    if st.get("temperature") is not None:
        client.publish(f"{base}/current_temperature", str(st["temperature"]), retain=True)
    if st.get("setpoint") is not None:
        client.publish(f"{base}/setpoint", str(st["setpoint"]), retain=True)
    mode_ha = "heat" if (st.get("heat_cool") or "H") == "H" else "cool"
    if (st.get("relay") or 0) == 0:
        mode_ha = "off"
    client.publish(f"{base}/mode", mode_ha, retain=True)
    client.publish(f"{base}/availability", "online" if available else "offline", retain=True)


def publish_discovery(client: mqtt.Client, mac: str, name: str | None) -> None:
    """Publica MQTT Discovery para climate.{unique_id}."""
    uid = mac_nocol(mac)
    config_topic = f"homeassistant/climate/sinilink_{uid}/config"
    base = f"{HA_TOPIC_PREFIX}_{uid}"
    config = {
        "name": name or f"Sinilink {mac}",
        "unique_id": f"sinilink_{uid}",
        "temperature_unit": "C",
        "current_temperature_topic": f"{base}/current_temperature",
        "temperature_command_topic": f"{base}/setpoint/set",
        "temperature_state_topic": f"{base}/setpoint",
        "mode_command_topic": f"{base}/mode/set",
        "mode_state_topic": f"{base}/mode",
        "modes": ["heat", "cool", "off"],
        "availability_topic": f"{base}/availability",
        "payload_available": "online",
        "payload_not_available": "offline",
        "min_temp": 5,
        "max_temp": 35,
        "temp_step": 0.5,
    }
    client.publish(config_topic, json.dumps(config), retain=True)
    logger.info("Discovery published: %s", config_topic)


def on_connect(client: mqtt.Client, userdata: Any, flags: Any, rc: int, *args: Any) -> None:
    if rc != 0:
        logger.warning("MQTT connect failed: rc=%s", rc)
        return
    logger.info("MQTT connected")
    client.subscribe("APPWT#", qos=0)
    client.subscribe(f"{HA_TOPIC_PREFIX}_+/setpoint/set", qos=0)
    client.subscribe(f"{HA_TOPIC_PREFIX}_+/mode/set", qos=0)
    for mac in proxy_state.devices():
        publish_discovery(client, mac, None)


def on_message(client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
    topic = msg.topic or ""
    payload_raw = (msg.payload or b"").decode("utf-8", errors="replace").strip()
    # Comandos desde Home Assistant (setpoint/set, mode/set)
    if topic.endswith("/setpoint/set"):
        try:
            uid = topic.replace(f"{HA_TOPIC_PREFIX}_", "").replace("/setpoint/set", "").strip()
            mac = mac_col(uid)
            if not mac or len(uid) != 12:
                return
            ts = int(time.time())
            client.publish(f"APPWT{mac}", json.dumps({"method": "stemp", "param": str(float(payload_raw)), "time": ts}), retain=False)
            logger.info("HA setpoint -> APPWT%s: %s", mac, payload_raw)
        except (ValueError, TypeError):
            pass
        return
    if topic.endswith("/mode/set"):
        try:
            uid = topic.replace(f"{HA_TOPIC_PREFIX}_", "").replace("/mode/set", "").strip()
            mac = mac_col(uid)
            if not mac or len(uid) != 12:
                return
            ts = int(time.time())
            pl = payload_raw.lower()
            if pl == "off":
                client.publish(f"APPWT{mac}", json.dumps({"method": "spower", "param": "0", "time": ts}), retain=False)
            elif pl == "heat":
                client.publish(f"APPWT{mac}", json.dumps({"method": "swork", "param": "H", "time": ts}), retain=False)
            elif pl == "cool":
                client.publish(f"APPWT{mac}", json.dumps({"method": "swork", "param": "C", "time": ts}), retain=False)
            logger.info("HA mode -> APPWT%s: %s", mac, payload_raw)
        except Exception:
            pass
        return

    if not topic.startswith("APPWT"):
        return
    mac_raw = topic[5:].strip()
    mac = mac_col(mac_raw) if mac_raw else ""

    if payload_raw in ("find", "findport", "findisonline"):
        ip = proxy_state.get_ip(mac)
        st = {}
        if ip:
            parsed = udp_read_state(ip)
            if parsed and parsed.get("param"):
                st = state_from_param(parsed["param"])
        mac_c = mac
        mac_n = mac_nocol(mac)
        client.publish(f"returnisonline{mac_c}", "1", retain=False)
        client.publish(f"{mac_c}/returnisonline", "1", retain=False)
        status = json.dumps({"param": st} if st else {})
        client.publish(f"returnnowstatus{mac_c}", status, retain=False)
        client.publish(f"{mac_c}/returnnowstatus", status, retain=False)
        try:
            host_ip = os.environ.get("HA_HOST_IP", "192.168.1.121")
            client.publish(f"returnport{mac_n}", json.dumps({"ip": host_ip, "port": 1024}), retain=False)
        except Exception:
            pass
        logger.debug("Responded find/findport/findisonline for %s", mac)
        return

    try:
        cmd = json.loads(payload_raw)
    except json.JSONDecodeError:
        return
    method = (cmd.get("method") or "").lower()
    param_val = cmd.get("param", "")
    ts = cmd.get("time", int(time.time()))

    if method not in ("stemp", "swork", "smode", "spower"):
        return

    ip = proxy_state.get_ip(mac)
    st = dict(proxy_state.last_state.get(mac, {}))
    if ip:
        parsed = udp_read_state(ip)
        if parsed and parsed.get("param"):
            st = state_from_param(parsed["param"])
            proxy_state.last_state[mac] = st

    if method == "stemp":
        try:
            st["setpoint"] = float(param_val)
        except (ValueError, TypeError):
            pass
    elif method == "swork":
        st["heat_cool"] = "H" if str(param_val).upper() == "H" else "C"
        st["relay"] = 1
    elif method == "smode":
        st["mode"] = "A" if str(param_val).upper() == "A" else "M"
    elif method == "spower":
        st["relay"] = 1 if str(param_val) == "1" else 0

    ack = {"method": method, "param": str(param_val), "time": ts}
    client.publish(f"PROWT{mac}", json.dumps(ack), retain=False)
    logger.info("Command %s %s -> PROWT%s", method, param_val, mac)

    publish_ha_state(client, mac, st, available=True)
    proxy_state.last_state[mac] = st


def poll_all_and_publish(client: mqtt.Client) -> None:
    for mac in proxy_state.devices():
        ip = proxy_state.get_ip(mac)
        if not ip:
            continue
        parsed = udp_read_state(ip)
        if parsed and parsed.get("param"):
            st = state_from_param(parsed["param"])
            proxy_state.last_state[mac] = st
            publish_ha_state(client, mac, st, available=True)
        else:
            publish_ha_state(client, mac, proxy_state.last_state.get(mac, {}), available=False)


def discovery_loop(client: mqtt.Client) -> None:
    while True:
        try:
            found = udp_discovery()
            if found:
                proxy_state.update_devices(found)
                logger.info("Discovery: %d devices", len(found))
                for mac in found:
                    publish_discovery(client, mac, None)
        except Exception as e:
            logger.exception("Discovery error: %s", e)
        time.sleep(DISCOVERY_BROADCAST_INTERVAL)


def poll_loop(client: mqtt.Client) -> None:
    time.sleep(POLL_INTERVAL)
    while True:
        try:
            poll_all_and_publish(client)
        except Exception as e:
            logger.exception("Poll error: %s", e)
        time.sleep(POLL_INTERVAL)


def main() -> None:
    if PAHO_V2:
        mqtt_client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="sinilink_broker_proxy",
            protocol=mqtt.MQTTv311,
        )
    else:
        mqtt_client = mqtt.Client(client_id="sinilink_broker_proxy", protocol=mqtt.MQTTv311)

    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    if MQTT_USER or MQTT_PASSWORD:
        mqtt_client.username_pw_set(MQTT_USER or None, MQTT_PASSWORD or None)

    try:
        mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
    except Exception as e:
        logger.error("Cannot connect to MQTT %s:%s: %s", MQTT_HOST, MQTT_PORT, e)
        sys.exit(1)

    mqtt_client.loop_start()

    try:
        found = udp_discovery()
        if found:
            proxy_state.update_devices(found)
            logger.info("Initial discovery: %d devices", len(found))
            for mac in found:
                publish_discovery(mqtt_client, mac, None)
    except Exception as e:
        logger.warning("Initial discovery failed: %s", e)

    threading.Thread(target=discovery_loop, args=(mqtt_client,), daemon=True).start()
    threading.Thread(target=poll_loop, args=(mqtt_client,), daemon=True).start()

    logger.info("Sinilink broker proxy running. MQTT %s:%s", MQTT_HOST, MQTT_PORT)

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Shutting down")
    finally:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()


if __name__ == "__main__":
    main()
