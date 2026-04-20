# SDN Mini Project Scenarios Guide

This document explains the two primary demonstration scenarios used in this project:

1. Scenario A: Normal forwarding with all links up
2. Scenario B: Port failure simulation with alert generation and recovery

Both scenarios run on the same Mininet topology and are monitored by the Ryu controller.

## Topology Used in Both Scenarios

```
h1 (10.0.0.1) --\
h2 (10.0.0.2) --- s1 ----- s2 --- h4 (10.0.0.4)
h3 (10.0.0.3) --/             \
                               h5 (10.0.0.5)
```

- `s1` and `s2` are Open vSwitch instances using OpenFlow 1.3.
- `h1`, `h2`, `h3` connect to `s1`.
- `h4`, `h5` connect to `s2`.
- The controller installs learning-switch flows and monitors port events.

## Before Running Any Scenario

1. Build images:

```bash
make build
```

2. Start controller and log viewer:

```bash
make up
```

3. Confirm controller readiness in logs:

```bash
make logs
```

You should see that the controller is listening on OpenFlow port `6633`.

## Scenario A: Normal Forwarding (All Ports Up)

## Goal

Validate baseline connectivity and forwarding performance when no link failures exist.

## What It Tests

- Basic L2 reachability on same switch (`h1 -> h2`)
- L2 reachability across switches (`h1 -> h4`)
- Throughput under normal conditions (`iperf` from `h1` to `h4`)
- Flow learning and flow table population

## How to Run

```bash
make scenario-a
```

Equivalent command:

```bash
RUN_MODE=scenario_a docker compose up --abort-on-container-exit
```

## Internal Steps Performed

The Mininet runner:

1. Creates the topology and connects to the remote controller.
2. Executes ping from `h1` to `h2`.
3. Executes ping from `h1` to `h4`.
4. Starts `iperf` server on `h4` and runs `iperf` client on `h1`.
5. Dumps flow tables (`s1`, `s2`) and port statistics to log files.

## Expected Behavior

- Pings should succeed with normal RTT values.
- `iperf` should report non-zero throughput.
- Controller should receive packet-in initially, then install unicast flows.
- No down alerts should be generated if all links stay healthy.

## Output Files to Check

- `/logs/scenario_a.log`
- `/logs/flow_table_s1.txt`
- `/logs/flow_table_s2.txt`
- `/logs/port_stats_s1.txt`
- `/logs/port_stats_s2.txt`
- `/logs/port_stats.json`

## Validation Checklist

- `h1 -> h2` ping success
- `h1 -> h4` ping success
- `iperf` throughput present
- Flow entries exist beyond table-miss rule
- No unexpected `down` alerts during test

## Scenario B: Port Failure Simulation

## Goal

Demonstrate SDN controller visibility and reaction when a switch port goes down and later recovers.

## What It Tests

- Real-time detection of OpenFlow port status changes
- Alert creation on down events
- Traffic impact during failure window
- Recovery behavior after port is restored

## How to Run

```bash
make scenario-b
```

Equivalent command:

```bash
RUN_MODE=scenario_b docker compose up --abort-on-container-exit
```

## Internal Steps Performed

The Mininet runner performs:

1. Baseline Scenario A traffic (to establish normal behavior first).
2. Baseline ping from `h1` to `h3` (expected success).
3. Administrative link shutdown on `s1-eth3`:

```bash
ip link set s1-eth3 down
```

4. Waits for controller to process port status update.
5. Pings `h1 -> h3` again (expected failure/timeout while port is down).
6. Restores the same link:

```bash
ip link set s1-eth3 up
```

7. Waits for status propagation and reruns `h1 -> h3` ping (expected success).
8. Dumps flow tables and port statistics.

## Expected Controller-Side Events

When the port is brought down:

- Controller receives `EventOFPPortStatus`.
- State is interpreted as `down`.
- Event is appended to `/logs/port_events.json`.
- Alert is appended to `/alerts/alerts.json`.

When the port is brought back up:

- Controller receives another port status event.
- State change `down -> up` is logged.
- Traffic to `h3` should recover.

## Expected Behavior During Failure Window

- `h1 -> h3` ping should fail or time out while `s1-eth3` is down.
- Other paths not using the failed edge can continue to work.
- After recovery, `h1 -> h3` ping should return to success.

## Output Files to Check

- `/logs/scenario_b.log`
- `/logs/port_events.json`
- `/alerts/alerts.json`
- `/logs/port_stats.json`

## Validation Checklist

- Baseline `h1 -> h3` success before failure
- Ping failure during `s1-eth3` down
- Alert entry generated with `state: down`
- Port event log contains both down and up transitions
- Ping success restored after interface is up again

## Useful Monitoring Commands

1. Live status dashboard:

```bash
make status
```

2. Alerts only:

```bash
make alerts
```

3. Flow tables:

```bash
make flow-tables
```

4. REST API examples:

```bash
curl http://localhost:8080/v1.0/topology/switches
curl http://localhost:8080/stats/port/<dpid>
```

## Common Troubleshooting

1. Mininet cannot reach controller
- Ensure controller service is healthy before starting Mininet.
- Verify `CONTROLLER_IP` and `CONTROLLER_PORT` values.

2. No alerts generated in Scenario B
- Confirm the exact interface toggled is `s1-eth3`.
- Check `/logs/port_events.json` first to verify event reception.

3. Empty flow table output
- Ensure Mininet was running when flow dump commands executed.
- Generate traffic first so learning-switch rules are installed.

4. Scenario hangs waiting for networking
- Ensure Docker is running with required privileges.
- Re-run cleanup and restart:

```bash
make down
make up
```

## Summary

- Scenario A proves expected forwarding and performance in healthy conditions.
- Scenario B proves fault detection, alert generation, and recovery behavior.
- Together, they demonstrate both normal SDN operation and failure observability.
