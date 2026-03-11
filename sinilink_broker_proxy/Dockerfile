ARG BUILD_FROM
FROM ${BUILD_FROM}

ARG BUILD_ARCH
RUN apk add --no-cache python3 py3-pip \
    && pip3 install --break-system-packages --no-cache-dir paho-mqtt>=1.6.0

WORKDIR /app
COPY sinilink_broker_proxy.py /app/

# Sin run.sh: el Supervisor inyecta MQTT_HOST, MQTT_PORT, etc. desde las opciones del add-on
CMD ["python3", "/app/sinilink_broker_proxy.py"]
