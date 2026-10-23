# Trader Intelligence

A personal portfolio and options intelligence tool that turns fragmented market checks into one disciplined workflow. It ranks swing setups by market regime and implied-volatility rank, evaluates single-ticker trend, unusual options flow, and binomial option pricing, and scores portfolio tail risk (99% expected shortfall and five-factor Sharpe) while walling off research from broker execution.

## Introduction

The checks are already on the desk. A regime read. An implied-volatility rank. A chart. An options chain. A book of positions. Each one answers a real question. They do not share a sequence, so the person running the book stitches them together by hand, and the order is whichever screen was open last. Trader Intelligence is that sequence. It turns the separate checks into one pass, and the pass ends before the order.

**Stock Selection** is the first sitting. Open `/stock-selection`. Setups are bucketed by the regime the tape is in: `calm_trend`, `volatile_trend`, `calm_mean_revert`, `stress`, or `neutral`. The rank is computed inside the bucket, so a calm-trend setup is scored against other calm-trend setups. Implied-volatility rank then splits that same universe into two sleeves. Sell-premium is the rich side. Buy-premium is the cheap side. You leave the screen knowing which sleeve the day belongs to. The bucketing and the split live in `backend/src/analytics/swing_ranker.py`.

**Analysis** is the second sitting. Open `/` and give it one ticker. The pass reads the 50-day and the 200-day trend, the recent candlestick patterns, and unusual options flow as volume against open interest. It prices the contract with `universal_binomial_pricer` in `backend/src/analytics/analysis.py` and sets that model price next to the market. What comes back is a directional bias and a risk assessment, written for the person who decides whether to trade. The screen produces a verdict. The account is still untouched.

**Portfolio** is the third sitting. Open `/portfolio`. The book is judged as a book. The research standard for that judgment is a 1-day 99% expected shortfall and a Sharpe ratio from a Fama–French five-factor plus momentum expected return. That pair is the standard this workflow is written against. This repository does not compute it yet.

**The wall** is part of the product. Ranking, the binomial price, and the verdict do not call the broker. Order placement lives only in `backend/src/services/broker_service.py`. A revised view of the market stays in the research pass. It reaches an account only when you send it there yourself.

| Fragmented check | One workflow |
|---|---|
| Regime is a feeling carried between tabs | Regime is a named bucket, and the rank lives inside it |
| Implied-volatility rank is a number on a chain | Implied-volatility rank splits the list into sell-premium and buy-premium |
| Trend, unusual flow, and a model price are three separate looks | One analysis pass writes the directional bias and the risk assessment |
| A position list stands in for the portfolio | The book is held to a tail-risk standard: 1-day 99% expected shortfall and five-factor Sharpe |

This is built for one personal book and one operator. Research runs first. Execution happens when you decide it does.

The yield curve on `/rates` and the verdict prompts on `/config` stay in the app. They support the pass. They sit beside the headline. They are the supporting screens.

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
