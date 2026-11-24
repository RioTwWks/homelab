#!/usr/bin/env bash
# Валидация Helm-чартов и манифестов k8s/ (план docs/k8s-helm-plan.md, фазы 1 и 4).
# Требуются helm и kubeconform в PATH.
set -euo pipefail
ROOT="${HOMELAB_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

for tool in helm kubeconform; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "ERROR: $tool не найден в PATH" >&2
    exit 1
  fi
done

shopt -s nullglob
charts=("$ROOT"/k8s/charts/*/)
if ((${#charts[@]} == 0)); then
  echo "Нет чартов в k8s/charts/ — нечего валидировать"
  exit 0
fi

for chart in "${charts[@]}"; do
  name="$(basename "$chart")"
  echo "== helm lint: $name"
  helm lint "$chart"
  echo "== helm template | kubeconform: $name"
  helm template "$name" "$chart" --namespace moltbot | kubeconform -strict -summary
done

manifests=("$ROOT"/k8s/namespaces/*.yaml)
if ((${#manifests[@]})); then
  echo "== kubeconform: k8s/namespaces"
  kubeconform -strict -summary "${manifests[@]}"
fi

echo "OK: чарты и манифесты k8s/ валидны"
