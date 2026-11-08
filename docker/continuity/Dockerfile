FROM pqc-iot-tls:organizacao
COPY pqc_iot_simulator/pqc_iot_sim/engines/native/continuity/native.c /opt/pqc-tls/continuity/native.c
RUN cd /opt/pqc-tls/continuity \
    && gcc -shared -fPIC -Wall -Wextra -Werror -Wno-unused-parameter \
       $(python3-config --includes) -I/opt/pqc-tls/include native.c \
       -L/opt/pqc-tls/lib -Wl,-rpath,/opt/pqc-tls/lib -lssl -lcrypto \
       -o _continuity_tls$(python3-config --extension-suffix)
ENV PYTHONPATH=/workspace:/opt/pqc-tls/native:/opt/pqc-tls/continuity
