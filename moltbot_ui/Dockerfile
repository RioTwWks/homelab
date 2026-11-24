# Статический UI для K8s-образа homelab/moltbot-ui (nginx conf монтируется из ConfigMap чарта).
# Сборка из корня репозитория: docker build -t homelab/moltbot-ui:latest -f moltbot_ui/Dockerfile .
# Compose-профиль `ui` этот образ не использует — там nginx:alpine + bind-mount (см. docker-compose.yml).
FROM nginx:alpine
COPY moltbot_ui/ /usr/share/nginx/html/
