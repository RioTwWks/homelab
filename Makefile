# Moltbot homelab — Makefile + Ansible installer
#
# Quick start:
#   make configure    # interactive wizard → ansible/group_vars/local.yml
#   make install      # full deploy (preset from local.yml or minimal)
#   make health       # check API
#
# Presets (override moltbot_preset in local.yml or pass on CLI):
#   make install-minimal   # ui only
#   make install-voice     # ui + search + voice stack + whisper systemd
#   make install-full      # all optional profiles

SHELL := /bin/bash
ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ANSIBLE_DIR := $(ROOT_DIR)/ansible
export ANSIBLE_CONFIG := $(ANSIBLE_DIR)/ansible.cfg
INVENTORY := $(ANSIBLE_DIR)/inventory/hosts.yml
PLAYBOOK_SITE := playbooks/site.yml
PLAYBOOK_VOICE := playbooks/voice.yml
PLAYBOOK_REMOTE_ACCESS := playbooks/remote_access.yml
LOCAL_VARS := $(ANSIBLE_DIR)/group_vars/local.yml
ANSIBLE := cd $(ANSIBLE_DIR) && ansible-playbook
ANSIBLE_ARGS :=

# Optional extra vars from CLI: make deploy EXTRA_VARS="-e moltbot_preset=full"
ifdef EXTRA_VARS
  ANSIBLE_ARGS += $(EXTRA_VARS)
endif

.PHONY: help configure ansible-deps deploy install install-minimal install-voice install-voice-npu install-full \
        voice remote-access systemd up down ps health logs backup-timer check

help: ## Show targets
	@grep -E '^[a-zA-Z0-9_.-]+:.*##' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

configure: ## Interactive wizard → ansible/group_vars/local.yml
	@$(ROOT_DIR)/scripts/configure-wizard.sh

ansible-deps: ## Install Ansible collections (community.docker)
	@command -v ansible-galaxy >/dev/null || { echo "Install ansible: sudo apt install ansible-core"; exit 1; }
	ansible-galaxy collection install -r $(ANSIBLE_DIR)/requirements.yml

deploy: ansible-deps ## Run Ansible site playbook (idempotent)
	@test -f $(LOCAL_VARS) || { echo "Run 'make configure' first (missing $(LOCAL_VARS))"; exit 1; }
	$(ANSIBLE) $(PLAYBOOK_SITE) $(ANSIBLE_ARGS)

install: ## Configure (if needed) + deploy + health check
	@test -f $(LOCAL_VARS) || $(MAKE) configure
	@$(MAKE) deploy $(ANSIBLE_ARGS)
	@$(MAKE) health

install-minimal: ## Preset: core stack + web UI
	@$(MAKE) deploy EXTRA_VARS="-e moltbot_preset=minimal"

install-voice: ## Preset: minimal + search + Hermes voice (optional NPU STT systemd)
	@$(MAKE) deploy EXTRA_VARS="-e moltbot_preset=voice -e moltbot_enable_voice=true -e voice_backend=hermes -e moltbot_enable_systemd_whisper=false"

install-voice-npu: ## Hermes voice + FastFlowLM NPU STT (flm-asr systemd)
	@$(MAKE) deploy EXTRA_VARS="-e moltbot_preset=voice -e moltbot_enable_voice=true -e voice_backend=hermes -e hermes_enable_npu_stt=true -e moltbot_enable_systemd_flm_asr=true -e moltbot_enable_systemd_whisper=false"

install-full: ## Preset: all compose profiles + backup timer
	@$(MAKE) deploy EXTRA_VARS="-e moltbot_preset=full -e moltbot_enable_voice=true -e voice_backend=hermes -e moltbot_enable_systemd_whisper=false -e moltbot_enable_backup_timer=true"

voice: ansible-deps ## Voice stack only (whisper, TTS, voice_mvp.env)
	@test -f $(LOCAL_VARS) || { echo "Run 'make configure' first"; exit 1; }
	$(ANSIBLE) $(PLAYBOOK_VOICE) $(ANSIBLE_ARGS)

remote-access: ansible-deps ## Headscale client + cloudflared (see docs/remote-access.md)
	@test -f $(LOCAL_VARS) || { echo "Run 'make configure' first"; exit 1; }
	$(ANSIBLE) $(PLAYBOOK_REMOTE_ACCESS) $(ANSIBLE_ARGS)

systemd: ansible-deps ## Install systemd units (whisper, timer-worker, backup)
	@test -f $(LOCAL_VARS) || { echo "Run 'make configure' first"; exit 1; }
	$(ANSIBLE) $(PLAYBOOK_SITE) --tags systemd $(ANSIBLE_ARGS)

up: ## docker compose up (uses profiles from local.yml if present)
	@PROFILES=$$(grep -E '^moltbot_profiles:' $(LOCAL_VARS) 2>/dev/null | sed 's/.*\[//;s/\]//;s/"//g;s/,/ /g' || echo "ui"); \
		echo "Profiles: $$PROFILES"; \
		cd $(ROOT_DIR) && docker compose $$(for p in $$PROFILES; do echo --profile $$p; done) up -d --build

down: ## docker compose down
	@cd $(ROOT_DIR) && docker compose down

ps: ## docker compose ps
	@cd $(ROOT_DIR) && docker compose ps

health: ## curl moltbot-api /healthz
	@curl -sf http://localhost:18080/healthz | (command -v jq >/dev/null && jq . || cat) || \
		{ echo "API not reachable at http://localhost:18080/healthz"; exit 1; }

logs: ## follow moltbot-api logs
	@cd $(ROOT_DIR) && docker compose logs -f moltbot-api

backup-timer: ansible-deps ## Enable homelab-backup systemd timer
	@test -f $(LOCAL_VARS) || { echo "Run 'make configure' first"; exit 1; }
	$(ANSIBLE) $(PLAYBOOK_SITE) --tags backup $(ANSIBLE_ARGS)

check: ## Syntax-check Ansible + monitoring configs (no NPU/host required)
	@command -v ansible-playbook >/dev/null || { echo "ansible-playbook not found"; exit 1; }
	$(ANSIBLE) $(PLAYBOOK_SITE) --syntax-check
	$(ANSIBLE) $(PLAYBOOK_VOICE) --syntax-check
	$(ANSIBLE) $(PLAYBOOK_REMOTE_ACCESS) --syntax-check
	@command -v jq >/dev/null || { echo "jq not found (needed for OpenCode config)"; exit 1; }
	@jq empty $(ROOT_DIR)/config/opencode/opencode.json
	@if command -v docker >/dev/null; then \
		docker compose -f $(ROOT_DIR)/docker-compose.yml --profile monitoring config --quiet; \
	else \
		echo "docker not found (skip compose monitoring validate)"; \
	fi
	@bash -n $(ROOT_DIR)/scripts/flm_validate.sh
	@python3 $(ROOT_DIR)/scripts/validate_monitoring_configs.py
