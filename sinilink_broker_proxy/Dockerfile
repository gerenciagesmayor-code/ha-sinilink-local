ARG BUILD_FROM
FROM ${BUILD_FROM}

ARG BUILD_ARCH
RUN apk add --no-cache python3 py3-pip \
    && pip3 install --break-system-packages --no-cache-dir paho-mqtt>=1.6.0

WORKDIR /app
COPY sinilink_broker_proxy.py /app/

# La imagen base del add-on HA ejecuta siempre /run.sh; hay que crearlo aquí (sin COPY para evitar CRLF)
RUN set -e && \
    echo '#!/bin/sh' > /run.sh && \
    echo 'set -e' >> /run.sh && \
    echo 'export MQTT_HOST="${MQTT_HOST:-127.0.0.1}"' >> /run.sh && \
    echo 'export MQTT_PORT="${MQTT_PORT:-1883}"' >> /run.sh && \
    echo 'export MQTT_USER="${MQTT_USER:-}"' >> /run.sh && \
    echo 'export MQTT_PASSWORD="${MQTT_PASSWORD:-}"' >> /run.sh && \
    echo 'export HA_HOST_IP="${HA_HOST_IP:-192.168.1.121}"' >> /run.sh && \
    echo 'export DISCOVERY_INTERVAL="${DISCOVERY_INTERVAL:-300}"' >> /run.sh && \
    echo 'export POLL_INTERVAL="${POLL_INTERVAL:-30}"' >> /run.sh && \
    echo 'exec python3 /app/sinilink_broker_proxy.py' >> /run.sh && \
    chmod a+x /run.sh
