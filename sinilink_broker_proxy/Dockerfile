ARG BUILD_FROM
FROM ${BUILD_FROM}

ARG BUILD_ARCH
RUN apk add --no-cache python3 py3-pip \
    && pip3 install --break-system-packages --no-cache-dir paho-mqtt>=1.6.0

WORKDIR /app
COPY sinilink_broker_proxy.py /app/

# Generar /run.sh dentro de la imagen (evita problemas de CRLF)
RUN printf '%s\n' \
  '#!/bin/sh' \
  'set -e' \
  '' \
  'export MQTT_HOST=\"${MQTT_HOST:-127.0.0.1}\"' \
  'export MQTT_PORT=\"${MQTT_PORT:-1883}\"' \
  'export MQTT_USER=\"${MQTT_USER:-}\"' \
  'export MQTT_PASSWORD=\"${MQTT_PASSWORD:-}\"' \
  'export HA_HOST_IP=\"${HA_HOST_IP:-192.168.1.121}\"' \
  'export DISCOVERY_INTERVAL=\"${DISCOVERY_INTERVAL:-300}\"' \
  'export POLL_INTERVAL=\"${POLL_INTERVAL:-30}\"' \
  '' \
  'exec python3 /app/sinilink_broker_proxy.py' \
  > /run.sh && chmod a+x /run.sh

CMD ["/run.sh"]
