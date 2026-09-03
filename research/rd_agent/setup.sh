#!/usr/bin/env bash
# Bootstrap RD-Agent research env (Phase 1)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

ENV_NAME="${RDAGENT_CONDA_ENV:-rdagent}"

if ! conda env list | grep -qE "^${ENV_NAME}[[:space:]]"; then
  echo "Creating conda env ${ENV_NAME} (python 3.10)..."
  conda create -n "${ENV_NAME}" python=3.10 -y
fi

echo "Installing rdagent + pinned deps..."
conda run -n "${ENV_NAME}" pip install -r "${SCRIPT_DIR}/requirements.txt"

if [[ ! -f "${SCRIPT_DIR}/.env" ]]; then
  cp "${SCRIPT_DIR}/.env.example" "${SCRIPT_DIR}/.env"
  echo "Created ${SCRIPT_DIR}/.env — fill LLM keys before running fin_quant."
fi

# Optionally seed keys from project root .env
if [[ -f "${ROOT_DIR}/.env" ]]; then
  python3 << PY
from pathlib import Path
root = Path("${ROOT_DIR}")
rd = Path("${SCRIPT_DIR}")
env_path = rd / ".env"
text = env_path.read_text()
for line in root.joinpath(".env").read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    k, v = k.strip(), v.strip()
    if k in ("DEEPSEEK_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY") and v:
        needle = f"{k}="
        if needle in text and f"{k}={v}" not in text:
            import re
            text = re.sub(rf"^{re.escape(k)}=.*$", f"{k}={v}", text, flags=re.M)
env_path.write_text(text)
PY
fi

echo "Smoke checks..."
docker run --rm hello-world >/dev/null
conda run -n "${ENV_NAME}" python -c "import rdagent; print('rdagent import ok')"
conda run -n "${ENV_NAME}" rdagent --help | head -5

echo ""
echo "Setup complete. Validate with:"
echo "  conda activate ${ENV_NAME}"
echo "  cd ${SCRIPT_DIR}"
echo "  rdagent fin_quant    # ~30-60 min, ~\$10 LLM cost"
echo "  rdagent ui           # separate terminal"
