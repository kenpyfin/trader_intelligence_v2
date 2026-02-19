# Recommended Agent Strategy for Trader Intelligence V2

Based on the analysis of the Product Requirement Document (`pdr.md`) and the current codebase state, here is the recommended agent strategy to accelerate development and ensure system robustness.

## 1. Development Agents (The "Team")
These are the roles that AI agents (or human-AI pairs) should adopt to drive the project forward.

| Agent Role | Primary Responsibility | Key Focus Areas |
| :--- | :--- | :--- |
| **1. The Architect (Product Owner)** | **Planning & Alignment** | Maintains `pdr.md`, `architecture_and_plan.md`, and `task.md`. Ensures all code changes align with the high-level goals. Breaks down complex features into actionable steps. |
| **2. The Quant Engineer** | **Core Logic & Math** | Focuses exclusively on `backend/src/analytics`. Responsible for `option_trade.py` migration, Binomial pricing models, Greeks calculation, and Volatility analysis. **Skillset:** Python, NumPy, Pandas, Financial Math. |
| **3. The Full-Stack Builder** | **Feature Implementation** | Connects the backend logic to the frontend UI. Works on `FastAPI` endpoints and `React` components. Ensures the "One-Click Execution" and "Dashboard" features work end-to-end. |
| **4. The Integration Specialist** | **External APIs & Broker** | Manages the fragile connections to FMP, Finviz, and Interactive Brokers. Handles API rate limits, error handling, and the `IBTrader` integration. |
| **5. The Quality Guardian** | **Testing & Stability** | Writes `pytest` cases and frontend tests. Enforces the "Definition of Done". Ensures no regression in the "Core Analysis" while new features are added. |

## 2. Runtime Agents (System Components)
These are the autonomous software agents/services that should exist within the running application, aligning with the microservices architecture.

### A. Data Ingestion Agent (The "Feeder")
*   **Role:** Continuously fetches and normalizes market data.
*   **Responsibilities:**
    *   Polls FMP/Finviz for real-time price and option chain data.
    *   Manages local caching (Redis/MongoDB) to reduce API calls.
    *   Detects data anomalies before they reach the analysis engine.

### B. Quantitative Analysis Agent (The "Brain")
*   **Role:** Processes raw data into actionable intelligence.
*   **Responsibilities:**
    *   Runs the `universal_binomial_pricer` and volatility surface models.
    *   Scans for "Unusual Option Activity" and "Volatility Compression".
    *   Generates the "Holistic Conclusion" (Bullish/Bearish/Neutral).

### C. Execution Agent (The "Trader")
*   **Role:** Safely executes orders with the broker.
*   **Responsibilities:**
    *   Translates abstract strategy requests (e.g., "Buy Iron Condor") into specific broker orders.
    *   Monitors order status (Submitted -> Filled).
    *   Handles order modifications and cancellations.

### D. Risk Guardian Agent (The "Watchdog")
*   **Role:** Protects the portfolio 24/7.
*   **Responsibilities:**
    *   Calculates real-time Portfolio Greeks (Net Delta, Gamma, etc.).
    *   Checks against defined risk limits (e.g., "Max Drawdown", "Delta Saturation").
    *   sends alerts or auto-liquidates positions if critical thresholds are breached.

## 3. Gap Analysis & Next Steps

### Critical Gaps Identified
1.  **Risk Management**: The PDR mentions "portfolio risk management" (Point 6), but the codebase is currently focused on *analysis* and *initial execution*. The **Risk Guardian Agent** is a high-priority need.
2.  **Macro Integration**: `macro_service.py` exists, but needs to be fully integrated into the "Holistic Synthesis" to impact trading decisions.
3.  **Automated Verification**: While tests exist, a robust "Backtesting Engine" (Future Enhancement) is needed to validate the **Quant Agent's** models.

### Recommended Immediate Action
1.  **Assign the "Quant Engineer"** to finish the migration of `option_trade.py` logic to `backend/src/analytics`.
2.  **Assign the "Integration Specialist"** to finalize the `IBTrader` connection for live execution.
3.  **Spin up the "Risk Guardian"** as a background service to start monitoring existing positions immediately.
