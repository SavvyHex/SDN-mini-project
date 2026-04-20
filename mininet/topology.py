#!/usr/bin/env python3
"""
Mininet Topology for SDN Port Status Monitoring Project
========================================================
Topology:
    h1 ──┐
    h2 ──┤── s1 (OVS) ── s2 (OVS) ──┬── h4
    h3 ──┘                           └── h5

Two switches (s1, s2) connected via a trunk link.
Hosts h1–h3 connect to s1; h4–h5 connect to s2.

Test Scenarios
--------------
  Scenario A – Normal forwarding: ping between hosts while ports are up.
  Scenario B – Port failure simulation: bring s1-eth3 down, observe alerts.
"""

import sys
import time
import os
import subprocess
import signal

from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.link import TCLink
from mininet.log import setLogLevel, info
from mininet.cli import CLI


CONTROLLER_IP = os.environ.get("CONTROLLER_IP", "127.0.0.1")
CONTROLLER_PORT = int(os.environ.get("CONTROLLER_PORT", "6633"))
LOG_DIR = "/logs"
os.makedirs(LOG_DIR, exist_ok=True)


def build_topology():
    """Build and return a Mininet network with two switches."""
    net = Mininet(
        switch=OVSSwitch,
        controller=None,      # we add it manually
        link=TCLink,
        autoSetMacs=True,
        autoStaticArp=False,
    )

    info("*** Adding remote controller\n")
    c0 = net.addController(
        "c0",
        controller=RemoteController,
        ip=CONTROLLER_IP,
        port=CONTROLLER_PORT,
    )

    info("*** Adding switches\n")
    s1 = net.addSwitch("s1", protocols="OpenFlow13")
    s2 = net.addSwitch("s2", protocols="OpenFlow13")

    info("*** Adding hosts\n")
    h1 = net.addHost("h1", ip="10.0.0.1/24")
    h2 = net.addHost("h2", ip="10.0.0.2/24")
    h3 = net.addHost("h3", ip="10.0.0.3/24")
    h4 = net.addHost("h4", ip="10.0.0.4/24")
    h5 = net.addHost("h5", ip="10.0.0.5/24")

    info("*** Creating links\n")
    # Hosts → s1
    net.addLink(h1, s1, bw=100)
    net.addLink(h2, s1, bw=100)
    net.addLink(h3, s1, bw=100)
    # Hosts → s2
    net.addLink(h4, s2, bw=100)
    net.addLink(h5, s2, bw=100)
    # Inter-switch trunk link
    net.addLink(s1, s2, bw=1000)

    return net, c0, s1, s2, h1, h2, h3, h4, h5


def run_scenario_a(net, h1, h2, h4):
    """Scenario A: Normal forwarding – all ports up."""
    info("\n" + "="*60 + "\n")
    info("SCENARIO A: Normal Forwarding (all ports UP)\n")
    info("="*60 + "\n")

    info("* Pinging h1 → h2 (same switch)\n")
    result_local = h1.cmd("ping -c 4 10.0.0.2")
    info(result_local)

    info("* Pinging h1 → h4 (cross-switch)\n")
    result_cross = h1.cmd("ping -c 4 10.0.0.4")
    info(result_cross)

    info("* iperf throughput h1 → h4\n")
    h4.cmd("iperf -s -D")
    time.sleep(1)
    result_iperf = h1.cmd("iperf -c 10.0.0.4 -t 5")
    info(result_iperf)
    h4.cmd("kill %iperf")

    # Save results
    with open(f"{LOG_DIR}/scenario_a.log", "w") as f:
        f.write("=== SCENARIO A: Normal Forwarding ===\n")
        f.write(f"h1->h2 ping:\n{result_local}\n")
        f.write(f"h1->h4 ping:\n{result_cross}\n")
        f.write(f"h1->h4 iperf:\n{result_iperf}\n")

    info("Scenario A complete. Results saved to /logs/scenario_a.log\n")


def run_scenario_b(net, s1, h1, h3):
    """Scenario B: Port failure simulation – bring h3's port down."""
    info("\n" + "="*60 + "\n")
    info("SCENARIO B: Port Failure Simulation\n")
    info("="*60 + "\n")

    info("* Baseline: h1 can reach h3\n")
    before = h1.cmd("ping -c 2 10.0.0.3")
    info(before)

    info("* Bringing s1-eth3 (h3 port) DOWN...\n")
    s1.cmd("ip link set s1-eth3 down")
    time.sleep(3)   # wait for PortStatus event to propagate

    info("* h1 pings h3 after port is DOWN (should fail/timeout)\n")
    during = h1.cmd("ping -c 4 -W 1 10.0.0.3")
    info(during)

    info("* Restoring s1-eth3 UP...\n")
    s1.cmd("ip link set s1-eth3 up")
    time.sleep(3)

    info("* h1 pings h3 after port is UP again\n")
    after = h1.cmd("ping -c 4 10.0.0.3")
    info(after)

    with open(f"{LOG_DIR}/scenario_b.log", "w") as f:
        f.write("=== SCENARIO B: Port Failure Simulation ===\n")
        f.write(f"Before down:\n{before}\n")
        f.write(f"During down:\n{during}\n")
        f.write(f"After restore:\n{after}\n")

    info("Scenario B complete. Results saved to /logs/scenario_b.log\n")
    info("Check /alerts/alerts.json for generated alerts!\n")


def dump_flow_tables(net):
    """Dump OpenFlow flow tables for both switches."""
    info("\n*** Dumping flow tables\n")
    for sw_name in ["s1", "s2"]:
        sw = net.get(sw_name)
        result = sw.cmd("ovs-ofctl -O OpenFlow13 dump-flows " + sw_name)
        info(f"\n--- {sw_name} flow table ---\n{result}\n")
        with open(f"{LOG_DIR}/flow_table_{sw_name}.txt", "w") as f:
            f.write(result)

    info("Flow tables saved to /logs/\n")


def dump_port_stats(net):
    """Dump port statistics for all switches."""
    info("\n*** Dumping port statistics\n")
    for sw_name in ["s1", "s2"]:
        sw = net.get(sw_name)
        result = sw.cmd("ovs-ofctl -O OpenFlow13 dump-ports " + sw_name)
        info(f"\n--- {sw_name} port stats ---\n{result}\n")
        with open(f"{LOG_DIR}/port_stats_{sw_name}.txt", "w") as f:
            f.write(result)

    info("Port stats saved to /logs/\n")


def main():
    setLogLevel("info")

    info("*** Building topology\n")
    net, c0, s1, s2, h1, h2, h3, h4, h5 = build_topology()

    info("*** Starting network\n")
    net.start()

    info("*** Waiting for controller to connect (5s)...\n")
    time.sleep(5)

    # ── Run scenarios ──────────────────────────────────────────────────────────
    mode = os.environ.get("RUN_MODE", "demo")

    if mode == "scenario_a":
        run_scenario_a(net, h1, h2, h4)
        dump_flow_tables(net)
        dump_port_stats(net)

    elif mode == "scenario_b":
        run_scenario_a(net, h1, h2, h4)   # establish baseline first
        run_scenario_b(net, s1, h1, h3)
        dump_flow_tables(net)
        dump_port_stats(net)

    elif mode == "full":
        run_scenario_a(net, h1, h2, h4)
        run_scenario_b(net, s1, h1, h3)
        dump_flow_tables(net)
        dump_port_stats(net)

    else:  # interactive CLI
        info("*** Entering interactive CLI (type 'exit' to quit)\n")
        CLI(net)

    info("*** Stopping network\n")
    net.stop()


if __name__ == "__main__":
    main()