#!/usr/bin/env bash
set -e

export LD_LIBRARY_PATH=/usr/local/lib:/usr/local/lib64:${LD_LIBRARY_PATH}
export OQS_INSTALL_PATH=/usr/local
export PYTHONPATH=/workspace:${PYTHONPATH}
export MPLBACKEND=Agg

service openvswitch-switch start || true
ovs-vsctl --no-wait init || true

mn -c >/dev/null 2>&1 || true

exec "$@"
