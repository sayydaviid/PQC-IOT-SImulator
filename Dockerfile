FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC
ENV PYTHONUNBUFFERED=1
ENV MPLBACKEND=Agg
ENV PYTHONPATH=/workspace
ENV LD_LIBRARY_PATH=/usr/local/lib:/usr/local/lib64
ENV OQS_INSTALL_PATH=/usr/local

WORKDIR /workspace

RUN apt-get update && apt-get install -y \
    tzdata \
    python3 \
    python3-pip \
    python3-dev \
    python3-venv \
    git \
    curl \
    wget \
    build-essential \
    cmake \
    ninja-build \
    libssl-dev \
    ca-certificates \
    lsb-release \
    software-properties-common \
    iproute2 \
    iputils-ping \
    net-tools \
    wireless-tools \
    iw \
    openvswitch-switch \
    openvswitch-common \
    openvswitch-testcontroller \
    sudo \
    tcpdump \
    iperf \
    psmisc \
    kmod \
    && ln -fs /usr/share/zoneinfo/Etc/UTC /etc/localtime \
    && dpkg-reconfigure --frontend noninteractive tzdata \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --upgrade \
    pip \
    setuptools \
    wheel

# A revisão dos bindings Python abaixo reporta versão 0.14.0. Fixar a mesma
# versão da biblioteca C evita misturar ABIs e mantém o build reprodutível.
ARG LIBOQS_TAG=0.14.0

RUN git clone --depth 1 --branch "$LIBOQS_TAG" \
    https://github.com/open-quantum-safe/liboqs.git \
    /opt/liboqs \
    && cmake \
        -S /opt/liboqs \
        -B /opt/liboqs/build \
        -GNinja \
        -DBUILD_SHARED_LIBS=ON \
    && cmake --build /opt/liboqs/build --parallel 4 \
    && cmake --build /opt/liboqs/build --target install \
    && ldconfig

# Instala uma revisão fixa dos bindings para manter o ambiente reprodutível.
ARG LIBOQS_PYTHON_COMMIT=9ab93b648e0253087f3c627af3674c058ede391b

RUN git init /opt/liboqs-python \
    && git -C /opt/liboqs-python remote add origin \
        https://github.com/open-quantum-safe/liboqs-python.git \
    && git -C /opt/liboqs-python fetch --depth 1 \
        origin "$LIBOQS_PYTHON_COMMIT" \
    && git -C /opt/liboqs-python checkout --detach FETCH_HEAD \
    && python3 -m pip install --no-cache-dir /opt/liboqs-python

# Instala uma revisão fixa do Mininet-WiFi. O espelho contém o mesmo commit
# Git do submódulo oficial e evita as transferências interrompidas do w1.fi.
ARG MININET_WIFI_COMMIT=99ba09b269f8e5e08cd9698c24b8b7e2949016a9

RUN rm -rf /opt/mininet-wifi \
    && git init /opt/mininet-wifi \
    && git -C /opt/mininet-wifi remote add origin \
        https://github.com/intrig-unicamp/mininet-wifi.git \
    && git -C /opt/mininet-wifi fetch --depth 1 \
        origin "$MININET_WIFI_COMMIT" \
    && git -C /opt/mininet-wifi checkout --detach FETCH_HEAD \
    && git -C /opt/mininet-wifi submodule set-url \
        hostap https://github.com/mikebdp2/hostap.git \
    && hostap_cloned=0 \
    && for attempt in 1 2 3 4 5; do \
        if timeout 600s git -c http.version=HTTP/1.1 \
            -c http.lowSpeedLimit=1000 \
            -c http.lowSpeedTime=60 \
            -C /opt/mininet-wifi submodule update \
            --init --depth 1 hostap; then \
            hostap_cloned=1; \
            break; \
        fi; \
        echo "Falha ao baixar hostap (tentativa ${attempt}/5)"; \
        rm -rf /opt/mininet-wifi/hostap \
            /opt/mininet-wifi/.git/modules/hostap; \
        sleep 5; \
    done \
    && test "$hostap_cloned" -eq 1

# A série 1.6 do FlightRadarAPI renomeou o módulo Python, mas esta revisão do
# Mininet-WiFi ainda importa FlightRadar24. Fixar 1.3.10 preserva essa API.
RUN apt-get update \
    && python3 -m pip install --no-cache-dir \
        "FlightRadarAPI==1.3.10" \
    && python3 -c \
        "from FlightRadar24 import FlightRadar24API; print(FlightRadar24API)" \
    && cd /opt/mininet-wifi \
    && DEBIAN_FRONTEND=noninteractive \
       TZ=Etc/UTC \
       util/install.sh -Wlnfv \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# O instalador do Mininet-WiFi inclui Matplotlib 3.5 pelo APT. Manter essa
# cópia junto da versão do requirements.txt mistura ``mpl_toolkits`` de duas
# instalações. Removemos apenas o pacote Python; o pip instala a versão única
# e compatível na etapa seguinte.
RUN apt-get purge -y python3-matplotlib \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Dependências Python do projeto
COPY requirements.txt /workspace/requirements.txt

RUN python3 -m pip install --no-cache-dir \
    -r /workspace/requirements.txt

# Falha ainda durante o build se a imagem não tiver os componentes exigidos
# pelo simulador e pelo notebook, evitando o erro só na hora da execução.
RUN command -v jupyter \
    && command -v mn \
    && command -v ovs-vsctl \
    && command -v tcpdump \
    && python3 -c 'from mn_wifi.net import Mininet_wifi; import jupyterlab, oqs; assert oqs.oqs_version().split(".")[:2] == oqs.oqs_python_version().split(".")[:2]; assert "ML-KEM-512" in oqs.get_enabled_kem_mechanisms(); assert "ML-DSA-44" in oqs.get_enabled_sig_mechanisms()'

# Registra o kernel do projeto
RUN python3 -m ipykernel install \
    --sys-prefix \
    --name pqc-iot-simulator \
    --display-name "Python 3 - PQC IoT Simulator"

COPY . /workspace

RUN python3 -c \
    'from pqc_iot_simulator.pqc_iot_sim import Network, Simulation; \
     print("PQC-IoT Simulator import: OK")'

COPY docker-entrypoint.sh /docker-entrypoint.sh

RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]

CMD ["python3" ,"-m", "pqc_iot_simulator.pqc_iot_sim.main"]
