ARG BUILD_FROM
FROM ${BUILD_FROM}

ARG BUILD_ARCH
RUN apk add --no-cache python3 py3-pip \
    && pip3 install --break-system-packages --no-cache-dir paho-mqtt>=1.6.0

WORKDIR /app
COPY run.sh /
COPY sinilink_broker_proxy.py /app/

RUN sed -i 's/\r$$//' /run.sh \
    && chmod a+x /run.sh

CMD ["/run.sh"]
