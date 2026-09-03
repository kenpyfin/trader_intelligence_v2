# RD-Agent Research Service

Standalone offline research loop for factor/model discovery. Integrates with the trader app only via Mongo `rd_agent_signals` (Phase 4+).

## Prerequisites

- Docker (user can run without sudo): `docker run hello-world`
- Conda env `rdagent` (Python 3.10)
- LLM credentials in `.env` (see `.env.example`)

## Setup

```bash
# From repo root
conda activate rdagent   # or: conda run -n rdagent bash

cd research/rd_agent
cp .env.example .env      # fill DEEPSEEK_API_KEY / GEMINI_API_KEY (or your provider)

pip install -r requirements.txt   # pins pydantic-ai==1.0.0 (rdagent 0.8.0 breaks on pydantic-ai 2.x)
```

Project root `.env` keys can be reused for DeepSeek/Gemini if present.

## Validate (Phase 1)

Uses bundled CSI300 demo data — no US export required yet.

```bash
cd research/rd_agent
rdagent fin_quant          # one optimization loop (~$10 LLM cost, 30–60+ min)
rdagent ui                 # inspect loop results (separate terminal)
```

Smoke checks without full loop:

```bash
rdagent --help
rdagent fin_quant --help
python -c "import rdagent; print('rdagent ok')"
docker run hello-world
```

## Layout (planned)

```
research/rd_agent/
  .env.example
  README.md
  export_qlib_data.py      # Phase 2 — Mongo → Qlib .bin
  publish_signals.py        # Phase 4 — run output → Mongo
  conf/us_quant.yaml        # Phase 3 — US market config
```

## Notes

- Keep this env **separate** from `backend/` (Python 3.10 vs 3.12, qlib/torch deps).
- Do not commit `.env` with API keys.
- Full US pipeline runs after `export_qlib_data.py` is built (Phase 2).
