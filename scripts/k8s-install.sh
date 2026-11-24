#!/usr/bin/env bash
# Фаза 0 плана docs/k8s-helm-plan.md: установка K3s + helm на homelab-хост.
# Запускать НА ХОСТЕ (Linux) рядом с существующим Docker/compose — порты не конфликтуют
# (K3s API :6443, NodePort 30000+; compose-порты сохраняются).
set -euo pipefail

# shellcheck disable=SC2086
K3S_ARGS="${K3S_ARGS:---disable=traefik --write-kubeconfig-mode=644}"

if command -v k3s >/dev/null 2>&1; then
  echo "k3s уже установлен: $(k3s --version | head -1)"
else
  echo "== Установка K3s (server): $K3S_ARGS"
  curl -sfL https://get.k3s.io | sh -s - server $K3S_ARGS
fi

if command -v helm >/dev/null 2>&1; then
  echo "helm уже установлен: $(helm version --short)"
else
  echo "== Установка helm"
  curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"
echo "== Проверка узла"
kubectl get nodes
echo "OK: K3s + helm готовы. Compose-стек не затронут — проверь: curl -s localhost:18080/healthz"
