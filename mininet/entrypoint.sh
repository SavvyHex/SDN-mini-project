#!/bin/bash
# Entrypoint for Mininet container
# Must start Open vSwitch before launching Mininet

set -e

echo "=== SDN Port Status Monitoring – Mininet Container ==="
echo "Controller IP   : ${CONTROLLER_IP:-controller}"
echo "Controller Port : ${CONTROLLER_PORT:-6633}"
echo "Run Mode        : ${RUN_MODE:-demo}"
echo "======================================================="

# Start Open vSwitch
echo "[*] Starting Open vSwitch..."
service openvswitch-switch start
sleep 2

# Verify OVS is running
if ! ovs-vsctl show > /dev/null 2>&1; then
    echo "[ERROR] Open vSwitch failed to start!"
    exit 1
fi
echo "[+] Open vSwitch is running."

# Clean up any stale Mininet state
echo "[*] Cleaning up stale Mininet state..."
mn -c 2>/dev/null || true

# Wait for the controller to be reachable
echo "[*] Waiting for controller at ${CONTROLLER_IP:-controller}:${CONTROLLER_PORT:-6633}..."
MAX_WAIT=60
COUNT=0
while ! nc -z "${CONTROLLER_IP:-controller}" "${CONTROLLER_PORT:-6633}" 2>/dev/null; do
    if [ $COUNT -ge $MAX_WAIT ]; then
        echo "[WARN] Controller not reachable after ${MAX_WAIT}s – starting anyway."
        break
    fi
    echo "    ...waiting (${COUNT}s)"
    sleep 2
    COUNT=$((COUNT + 2))
done

echo "[+] Starting Mininet topology..."
python3 /app/topology.py