# Hermes phase 1

1. Install: `curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash`
2. `cd ~/homelab && ./scripts/hermes-install-skills.sh` — copies `hermes/config/config.yaml.example` with **context_length: 65536**
3. `source scripts/hermes-env.sh`
4. `./scripts/hermes-validate-tools.sh`
5. `hermes run "Привет, что ты умеешь?"`

moltbot-api stays on port 18080 until acceptance.
