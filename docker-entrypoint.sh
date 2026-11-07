#!/usr/bin/env bash
set -e

export LD_LIBRARY_PATH=/usr/local/lib:/usr/local/lib64:${LD_LIBRARY_PATH}
export OQS_INSTALL_PATH=/usr/local
export PYTHONPATH=/workspace:${PYTHONPATH}
export MPLBACKEND=Agg

service openvswitch-switch start || true
ovs-vsctl --no-wait init || true

mn -c >/dev/null 2>&1 || true

# O Mininet-WiFi precisa permanecer como root dentro do contêiner. Como o
# repositório é montado em /workspace, detectamos o proprietário no host para
# devolver os artefatos gerados ao usuário ao fim de cada execução.
workspace_uid="${HOST_UID:-$(stat -c '%u' /workspace)}"
workspace_gid="${HOST_GID:-$(stat -c '%g' /workspace)}"
output_directories=(
    /workspace/results
)

if ! [[ "$workspace_uid" =~ ^[0-9]+$ && "$workspace_gid" =~ ^[0-9]+$ ]]; then
    echo "UID/GID do host inválidos: ${workspace_uid}:${workspace_gid}" >&2
    exit 2
fi

for output_directory in "${output_directories[@]}"; do
    if [ ! -d "$output_directory" ]; then
        continue
    fi
    chown "$workspace_uid:$workspace_gid" "$output_directory"
    chmod 2775 "$output_directory"
done

# Arquivos criados durante a simulação ficam graváveis pelo grupo do usuário,
# inclusive antes da normalização final de propriedade.
umask 0002

restore_output_ownership() {
    local output_directory
    for output_directory in "${output_directories[@]}"; do
        if [ -e "$output_directory" ]; then
            chown -R "$workspace_uid:$workspace_gid" "$output_directory" \
                2>/dev/null || true
            find "$output_directory" -type d -exec chmod 2775 {} + \
                2>/dev/null || true
            find "$output_directory" -type f -exec chmod u+rw,g+rw {} + \
                2>/dev/null || true
        fi
    done
}

child_pid=""
forward_signal() {
    local signal="$1"
    if [ -n "$child_pid" ]; then
        kill "-$signal" "$child_pid" 2>/dev/null || true
    fi
}

trap restore_output_ownership EXIT
trap 'forward_signal INT' INT
trap 'forward_signal TERM' TERM

"$@" &
child_pid=$!
set +e
wait "$child_pid"
status=$?
set -e
child_pid=""
exit "$status"
