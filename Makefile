# ══════════════════════════════════════════════════════════════════════════════
#  SDN Port Status Monitoring – Makefile
# ══════════════════════════════════════════════════════════════════════════════

.PHONY: help build up down clean logs alerts flow-tables scenario-a scenario-b full-demo status

COMPOSE = docker compose
CONTROLLER = sdn-controller

help:
	@echo ""
	@echo "SDN Port Status Monitoring – Commands"
	@echo "────────────────────────────────────────────────────────"
	@echo "  make build          Build all Docker images"
	@echo "  make up             Start controller + log viewer"
	@echo "  make scenario-a     Run Scenario A (normal forwarding)"
	@echo "  make scenario-b     Run Scenario B (port failure)"
	@echo "  make full-demo      Run both scenarios sequentially"
	@echo "  make down           Stop and remove containers"
	@echo "  make clean          Remove containers, images, volumes"
	@echo "  make logs           Tail controller logs"
	@echo "  make alerts         Show current alerts"
	@echo "  make flow-tables    Dump flow tables from OVS"
	@echo "  make status         Live port status dashboard"
	@echo "────────────────────────────────────────────────────────"

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up controller log-viewer

scenario-a:
	RUN_MODE=scenario_a $(COMPOSE) up --abort-on-container-exit

scenario-b:
	RUN_MODE=scenario_b $(COMPOSE) up --abort-on-container-exit

full-demo:
	RUN_MODE=full $(COMPOSE) up --abort-on-container-exit

down:
	$(COMPOSE) down

clean:
	$(COMPOSE) down --rmi all --volumes --remove-orphans

logs:
	$(COMPOSE) logs -f controller

alerts:
	docker exec $(CONTROLLER) python3 /app/view_status.py --alerts

status:
	docker exec -it $(CONTROLLER) python3 /app/view_status.py

flow-tables:
	@echo "=== s1 flow table ==="
	docker exec sdn-mininet ovs-ofctl -O OpenFlow13 dump-flows s1 2>/dev/null || echo "Mininet not running"
	@echo "=== s2 flow table ==="
	docker exec sdn-mininet ovs-ofctl -O OpenFlow13 dump-flows s2 2>/dev/null || echo "Mininet not running"