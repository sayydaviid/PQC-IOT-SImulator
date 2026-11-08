FROM pqc_iot_simulator:latest
ARG OPENSSL_TAG=openssl-3.5.9
RUN git clone --depth 1 --branch "$OPENSSL_TAG" https://github.com/openssl/openssl.git /tmp/tls-openssl \
    && cd /tmp/tls-openssl \
    && mkdir -p /opt/pqc-tls \
    && git rev-parse HEAD > /opt/pqc-tls/source-commit \
    && ./Configure --prefix=/opt/pqc-tls --libdir=lib shared no-tests \
    && make -j4 \
    && make install_sw \
    && rm -rf /tmp/tls-openssl
ENV LD_LIBRARY_PATH=/opt/pqc-tls/lib:/usr/local/lib:/usr/local/lib64
ENV PATH=/opt/pqc-tls/bin:$PATH
ENV OPENSSL_CONF=/etc/ssl/openssl.cnf
ENV PYTHONPATH=/workspace:/opt/pqc-tls/native
COPY pqc_iot_simulator/pqc_iot_sim/engines/native/tls/native.c /opt/pqc-tls/native/native.c
RUN cd /opt/pqc-tls/native \
    && gcc -shared -fPIC -Wall -Wextra -Werror -Wno-unused-parameter \
       $(python3-config --includes) -I/opt/pqc-tls/include native.c \
       -L/opt/pqc-tls/lib -Wl,-rpath,/opt/pqc-tls/lib -lssl -lcrypto \
       -o _pqc_tls$(python3-config --extension-suffix) \
    && sha256sum native.c > source.sha256
