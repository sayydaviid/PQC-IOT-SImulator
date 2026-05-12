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
    && dpkg-reconfigure --frontend noninteractive tzdata

RUN python3 -m pip install --upgrade pip setuptools wheel

RUN git clone --depth 1 https://github.com/open-quantum-safe/liboqs.git /opt/liboqs && \
    cmake -S /opt/liboqs -B /opt/liboqs/build \
      -GNinja \
      -DBUILD_SHARED_LIBS=ON && \
    cmake --build /opt/liboqs/build --parallel 4 && \
    cmake --build /opt/liboqs/build --target install && \
    ldconfig

RUN git clone --depth 1 https://github.com/open-quantum-safe/liboqs-python.git /opt/liboqs-python && \
    python3 -m pip install /opt/liboqs-python

RUN apt-get update && \
    rm -rf /opt/mininet-wifi && \
    git clone --depth 1 https://github.com/intrig-unicamp/mininet-wifi.git /opt/mininet-wifi && \
    cd /opt/mininet-wifi && \
    DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC util/install.sh -Wlnfv

COPY pqc_iot_simulator/pqc_iot_sim/requirements-project.txt /workspace/requirements.txt

RUN python3 -m pip install --no-cache-dir -r /workspace/requirements.txt

COPY . /workspace

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python3", "-m", "pqc_iot_simulator.pqc_iot_sim.main"]
