# Trader Intelligence

A personal portfolio and options intelligence tool that turns fragmented market checks into one disciplined workflow. It ranks swing setups by market regime and implied-volatility rank, evaluates single-ticker trend, unusual options flow, and binomial option pricing, and scores portfolio tail risk (99% expected shortfall and five-factor Sharpe) while walling off research from broker execution.

## Workflow

One pass, in this order. Each step reads the market. None of them sends an order.

1. **Rank swing setups.** Names are bucketed by market regime (`calm_trend`, `volatile_trend`, `calm_mean_revert`, `stress`, `neutral`) and ranked inside those buckets. Implied-volatility rank splits the list into sell-premium and buy-premium. See `backend/src/analytics/swing_ranker.py`. The screen is `/stock-selection`.
2. **Evaluate one ticker.** The analysis pass reads trend (50-day and 200-day moving averages and recent candlestick patterns), unusual options flow (volume against open interest), and a binomial model price against the market. See `backend/src/analytics/analysis.py` (`universal_binomial_pricer`). The screen is `/`.
3. **Score the book.** Portfolio tail risk is a research score: 1-day 99% expected shortfall, and a Sharpe ratio from a Fama–French five-factor plus momentum expected return. Positions themselves are on `/portfolio`. The score does not place or resize an order.
4. **Stop at the research wall.** The verdict states a directional bias and a risk assessment for a person who executes. Ranking, pricing, and the verdict path do not call the broker. Order placement lives only in `backend/src/services/broker_service.py`.

## Layout

| Path | Role |
|---|---|
| `frontend/` | React app. Analysis, portfolio, yield curve, stock selection, prompt config. |
| `backend/` | FastAPI. Analytics, verdicts, and the separate broker service. |
| `docker-compose.yml` | Local frontend and backend. |
| `pdr.md`, `architecture_and_plan.md`, `AGENTS.md` | Product requirements, architecture, and engineering conventions. |
| `IV_AND_IV_RANK.md` | How implied volatility and IV rank are computed. |

## Run

```bash
docker compose up --build
```

API keys and broker settings belong in the repo-root `.env` (see `.env.example`). Do not commit that file.

The research workflow above is the product. Broker execution stays behind the wall in `broker_service`.
