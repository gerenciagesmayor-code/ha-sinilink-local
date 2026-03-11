# Add-on: Sinilink Broker Proxy

Proxy MQTT local para termostatos Sinilink XY-WFT1. Se ejecuta en Home Assistant y se reinicia con el sistema.

## Requisitos

- Home Assistant OS o Supervised con Supervisor.
- Add-on **Mosquitto broker** instalado (puerto 1883 y 8085 WebSocket).
- Regla DNS en AdGuard: `mq.sinilink.com` → IP de Home Assistant.

## Instalación desde repositorio

1. En HA: **Configuración** → **Add-ons** → **Repositorios** → **Añadir** la URL de este repositorio (la raíz debe contener `repository.yaml` y la carpeta `sinilink_broker_proxy`).
2. **Añadir add-on** → buscar "Sinilink Broker Proxy" → **Instalar**.
3. En **Configuración** del add-on revisar **ha_host_ip** (IP de HA en la LAN, p. ej. 192.168.1.121).
4. **Iniciar**.

## Opciones

| Opción | Por defecto | Descripción |
|--------|-------------|-------------|
| mqtt_host | 127.0.0.1 | Broker MQTT (con host_network es el host) |
| mqtt_port | 1883 | Puerto MQTT |
| mqtt_user / mqtt_password | vacío | Si Mosquitto 1883 usa auth |
| ha_host_ip | 192.168.1.121 | IP de HA para returnport |
| discovery_interval | 300 | Segundos entre descubrimientos UDP |
| poll_interval | 30 | Segundos entre sondeos de estado |
