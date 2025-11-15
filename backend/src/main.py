from fastapi import FastAPI, HTTPException
import traceback
import asyncio
from datetime import date, timedelta

from .models.analysis_models import AnalysisRequest, RiskFreeRateRequest, SaveVerdictRequest
from .models.order_models import StrategyOrderRequest
from .services.analysis_service import run_full_analysis, get_option_expirations
from .services.analysis_history_service import (
    save_analysis_record,
    list_history as list_analysis_history,
    delete_history_entry,
    clear_history_for_ticker,
)
from .services.macro_service import get_macro_futures_data, calculate_market_implied_risk_free_rate
from .services import broker_service, analysis_service
from .routers import portfolio
from .my_libs_py3.my_data import PriceDataFetcher
from .analytics.treasury_curve import build_treasury_curve
from .my_libs_py3.fmp import FMPClient
from .analytics.methodologies.gpt_verdict import generate_gpt_verdict
from .services.verdict_service import save_verdict_document, list_verdicts, get_verdict_by_id
import numpy as np
import math
import os
import requests


app = FastAPI(
    title="Trader Intelligence API",
    description="API for stock and option analysis.",
    version="1.0.0",
)

app.include_router(portfolio.router)

@app.get("/")
def read_root():
    """A simple endpoint to check if the API is running."""
    return {"message": "Welcome to the Trader Intelligence API"}

@app.get("/macro-data")
@app.get("/api/macro-data")  # Alias for nginx proxy compatibility
def get_macro_data():
    """Endpoint to fetch macro economic data (futures). Falls back to Finviz if the primary service fails."""
    def _df_to_mapping(df):
        """Convert a pandas DataFrame of futures into a dict-of-rows mapping suitable for the frontend table."""
        if df is None or getattr(df, "empty", True):
            return {}
        records = df.to_dict(orient="records")
        # Choose a stable key column if present; otherwise use row index
        key_col = None
        for cand in ("Ticker", "Symbol", "Name"):
            if cand in getattr(df, "columns", []):
                key_col = cand
                break

        def _clean_val(v):
            try:
                if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                    return None
                if hasattr(v, "item"):
                    vi = v.item()
                    if isinstance(vi, float) and (np.isnan(vi) or np.isinf(vi)):
                        return None
                    return vi
            except Exception:
                pass
            return v

        out = {}
        for idx, row in enumerate(records):
            key_val = row.get(key_col) if key_col else None
            key = str(key_val) if key_val not in (None, np.nan) else str(idx)
            out[key] = {k: _clean_val(v) for k, v in row.items()}
        return out

    try:
        data = get_macro_futures_data()
        # If the primary service returns a usable mapping, normalize numpy/pandas scalars to JSON-safe types.
        if isinstance(data, dict) and "error" not in data and len(data) > 0:
            def _clean_scalar(v):
                try:
                    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                        return None
                    if hasattr(v, "item"):
                        vi = v.item()
                        if isinstance(vi, float) and (np.isnan(vi) or np.isinf(vi)):
                            return None
                        return vi
                except Exception:
                    pass
                return v

            cleaned = {}
            for k, row in data.items():
                if isinstance(row, dict):
                    cleaned[k] = {kk: _clean_scalar(vv) for kk, vv in row.items()}
                else:
                    cleaned[k] = _clean_scalar(row)
            return cleaned

        # Fallback to direct Finviz fetch
        fetcher = PriceDataFetcher()
        df = fetcher.get_futures_data_finviz()
        if df is not None and not df.empty:
            return _df_to_mapping(df)

        # Gracefully return an error payload the frontend can handle (HTTP 200)
        return {"error": "No futures data available from Finviz. Verify API access and availability."}
    except Exception as e:
        print(traceback.format_exc())
        # Return an error payload instead of a 500 to let the frontend render a friendly message
        return {"error": f"An unexpected error occurred while fetching macro data: {e}"}

@app.get("/yield-curve")
@app.get("/api/yield-curve")
async def get_yield_curve(source: str = "treasury", tickers: str = "SPY, QQQ, IWM"):
    try:
        standard = [
            ("1M", 1/12), ("3M", 3/12), ("6M", 6/12), ("1Y", 1.0), ("2Y", 2.0),
            ("3Y", 3.0), ("5Y", 5.0), ("7Y", 7.0), ("10Y", 10.0), ("20Y", 20.0), ("30Y", 30.0)
        ]
        if source.lower() == "treasury":
            curve = build_treasury_curve(FMPClient())
            # If FMP yields are unavailable, fall back to a flat curve using ETF-implied rate
            if not curve.get("terms"):
                ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
                rate, logs = await calculate_market_implied_risk_free_rate(ticker_list)
                if rate is not None:
                    out = [{"tenor": t, "rate": float(rate)} for t, _ in standard]
                    return {
                        "source": "treasury",
                        "as_of": curve.get("as_of"),
                        "curve": out,
                        "logs": logs,
                        "note": "FMP treasury yields unavailable; using ETF-implied flat curve."
                    }
                # As a last resort, keep the internal default rate function (likely 4.5%)
            rate_fn = curve["rate_fn"]
            out = [{"tenor": t, "rate": float(rate_fn(T))} for t, T in standard]
            return {"source": "treasury", "as_of": curve["as_of"], "curve": out}
        elif source.lower() == "etf":
            ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
            rate, logs = await calculate_market_implied_risk_free_rate(ticker_list)
            if rate is None:
                return {"source": "etf", "curve": [], "logs": logs, "error": "Could not compute implied rate"}
            out = [{"tenor": t, "rate": float(rate)} for t, _ in standard]
            return {"source": "etf", "curve": out, "logs": logs}
        else:
            raise HTTPException(status_code=400, detail="Invalid source. Use 'treasury' or 'etf'.")
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to build yield curve: {e}")

@app.post("/calculate-risk-free-rate")
@app.post("/api/calculate-risk-free-rate")  # Alias for nginx proxy compatibility
async def get_risk_free_rate(request: RiskFreeRateRequest):
    """Calculates the market-implied risk-free rate from a basket of ETFs."""
    try:
        # The service now calculates the rate across multiple standard expiries automatically.
        rate, logs = await calculate_market_implied_risk_free_rate(
            tickers=request.tickers
        )
        return {"risk_free_rate": rate, "logs": logs}
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")

@app.post("/analysis/verdicts")
@app.post("/api/analysis/verdicts")
async def save_verdict(request: SaveVerdictRequest):
    """Save an analysis verdict snapshot for later retrieval/compare."""
    try:
        result = save_verdict_document(request.verdict, request.label)
        return result
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to save verdict: {e}")

@app.get("/analysis/verdicts/{ticker}")
@app.get("/api/analysis/verdicts/{ticker}")
async def list_saved_verdicts(ticker: str, page: int = 1, page_size: int = 25):
    """List saved verdicts for a ticker with pagination (most recent first)."""
    try:
        data = list_verdicts(ticker.upper(), page=page, page_size=page_size)
        data['status'] = 'success'
        return data
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to list verdicts: {e}")

@app.get("/analysis/verdicts/id/{doc_id}")
@app.get("/api/analysis/verdicts/id/{doc_id}")
async def get_saved_verdict(doc_id: str):
    """Fetch a saved verdict by its ID."""
    try:
        doc = get_verdict_by_id(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Verdict not found")
        return {"status": "success", "item": doc}
    except HTTPException:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch verdict: {e}")

@app.post("/analysis/stock-gpt")
async def analyze_stock_with_gpt(request: AnalysisRequest):
    """
    Alternative methodology: run the standard sub-analyses, then ask an LLM (gpt-5) to produce the final verdict
    and enhanced conclusion, including a brief external search if available.
    """
    from datetime import datetime
    try:
        # Parse expiration date
        try:
            expiration_date = datetime.strptime(request.expiration_date, '%Y%m%d').date()
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid expiration_date format. Expected 'YYYYMMDD'.")

        print(
            f"INFO: Received GPT analysis request for ticker={request.ticker}, "
            f"expiration={request.expiration_date}, model={request.gpt_model}"
        )

        # Run the full analysis pipeline with the GPT methodology enabled.
        base_result = await run_full_analysis(
            ticker=request.ticker.upper(),
            expiration_date=expiration_date,
            r_current=request.risk_free_rate,
            methodology='gpt-verdict',  # Use the gpt-verdict methodology
            gpt_model=request.gpt_model,
            override_price=request.override_price
        )

        if base_result.get("status") != "success":
            error_message = base_result.get("message", "Analysis failed for the selected date.")
            raise HTTPException(status_code=400, detail=error_message)

        # The GPT verdict is now part of the base_result.
        ai = base_result.get('gpt_verdict', {})

        # Merge AI verdict into the response while retaining the original model-based content
        final_bias = ai.get("final_bias", base_result.get("final_bias", "Neutral"))

        ai_html = ai.get("summary_html") or "<h5>AI Verdict</h5><p>No summary provided.</p>"
        rationale = ai.get("rationale", "")
        ideas = ai.get("actionable_ideas", [])
        risks = ai.get("risk_factors", [])
        sources = ai.get("sources", [])

        enhanced_html = (
            f"{ai_html}"
            f"<h5>AI Rationale</h5><p>{rationale}</p>"
            f"{'<h5>Actionable Ideas</h5><ul>' + ''.join(f'<li>{x}</li>' for x in ideas) + '</ul>' if ideas else ''}"
            f"{'<h5>Key Risks</h5><ul>' + ''.join(f'<li>{x}</li>' for x in risks) + '</ul>' if risks else ''}"
            f"{'<h5>Sources</h5><ul>' + ''.join(f'<li>{x}</li>' for x in sources) + '</ul>' if sources else ''}"
            f"<hr/><h5>Model-Based Summary</h5>{base_result.get('final_conclusion_html', '')}"
        )

        # Construct final payload
        result = dict(base_result)
        result["final_bias"] = final_bias
        result["final_conclusion_html"] = enhanced_html
        result["ai_meta"] = {
            "search_performed": bool(ai.get("search_performed", False)),
            "sources": sources,
        }
        result['expiration_date'] = request.expiration_date
        result['dte'] = (expiration_date - date.today()).days

        payload_to_persist = {
            'ticker': request.ticker,
            'expiration_date': request.expiration_date,
            'risk_free_rate': request.risk_free_rate,
            'analysis_method': 'gpt-verdict',
            'gpt_model': request.gpt_model,
            'override_price': request.override_price,
        }

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: save_analysis_record(payload_to_persist, [result])
            )
        except Exception as history_err:
            print(f"WARNING: Failed to persist GPT analysis history: {history_err}")

        # Auto-save verdict history (best-effort)
        try:
            save_verdict_document(result, None)
        except Exception as _e:
            print(f"WARNING: Autosave of GPT verdict failed: {_e}")

        return [result]
    except Exception as e:
        print(traceback.format_exc())
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")

@app.post("/orders/strategy")
@app.post("/api/orders/strategy")  # Alias for nginx proxy compatibility
async def create_strategy_order(request: StrategyOrderRequest):
    """
    Places a multi-leg strategy order via the connected broker.
    This corresponds to Key Feature 3 in the PDR.
    """
    try:
        result = await broker_service.place_strategy_order(request)
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])
        return result
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")


@app.get("/analysis/expirations/{ticker}")
@app.get("/api/analysis/expirations/{ticker}")  # Alias for nginx proxy compatibility
async def fetch_expirations(ticker: str):
    """Fetches available option expiration dates for a given ticker."""
    try:
        expirations = await get_option_expirations(ticker)
        # Frontend is designed to handle an empty list gracefully.
        return expirations
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")

@app.get("/api/gpt-models")
@app.get("/gpt-models")  # Alias for Docker/proxy compatibility
async def get_available_gpt_models():
    """Fetches available models from OpenWebUI API for GPT verdict analysis."""
    try:
        base_url = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")
        api_key = os.getenv("OPENAI_API_KEY")
        
        if not api_key:
            raise HTTPException(status_code=500, detail="OpenAI API key not configured")
        
        # Fetch models from OpenWebUI API
        response = requests.get(
            f"{base_url}/models",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            timeout=10
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Failed to fetch models: {response.status_code}")
        
        models_data = response.json()
        
        # Extract model list from OpenAI API response format
        if "data" in models_data:
            models = [
                {
                    "id": model["id"],
                    "name": model.get("id", model["id"]),  # Use id as display name if no name field
                    "created": model.get("created", 0)
                }
                for model in models_data["data"]
            ]
        else:
            models = []
        
        # Sort models by name for better UX
        models.sort(key=lambda x: x["name"])
        
        return {
            "status": "success",
            "models": models,
            "default": "gpt-5"  # Default model to select
        }
        
    except requests.RequestException as e:
        print(f"Error fetching models: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to connect to model service: {e}")
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")


@app.post("/analysis/stock")
@app.post("/api/analysis/stock")  # Alias for nginx proxy compatibility
async def analyze_stock(request: AnalysisRequest):
    """
    Runs a full stock and option analysis for a single, user-selected expiration date.
    This endpoint serves as the core of Key Feature 1.
    """
    from datetime import datetime
    try:
        # The frontend sends expiration_date as a 'YYYYMMDD' string.
        # We need to parse it into a date object for the analysis service.
        try:
            expiration_date = datetime.strptime(request.expiration_date, '%Y%m%d').date()
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid expiration_date format. Expected 'YYYYMMDD'.")

        print(
            f"INFO: Received analysis request for ticker={request.ticker}, "
            f"expiration={request.expiration_date}, method={request.analysis_method}"
        )

        analysis_result = await run_full_analysis(
            ticker=request.ticker.upper(),
            expiration_date=expiration_date,
            r_current=request.risk_free_rate,
            methodology=request.analysis_method,
            gpt_model=request.gpt_model,
            override_price=request.override_price
        )

        # Check if the single analysis was successful
        if analysis_result.get("status") != "success":
            error_message = analysis_result.get("message", "Analysis failed for the selected date.")
            raise HTTPException(status_code=400, detail=error_message)

        # The frontend expects an array of results, so we wrap the single result in a list.
        # We also calculate and add the DTE (days to expiration) for display purposes.
        analysis_result['expiration_date'] = request.expiration_date
        analysis_result['dte'] = (expiration_date - date.today()).days

        payload_to_persist = {
            'ticker': request.ticker,
            'expiration_date': request.expiration_date,
            'risk_free_rate': request.risk_free_rate,
            'analysis_method': request.analysis_method,
            'gpt_model': request.gpt_model,
            'override_price': request.override_price,
        }

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: save_analysis_record(payload_to_persist, [analysis_result])
            )
        except Exception as history_err:
            print(f"WARNING: Failed to persist analysis history: {history_err}")

        # Auto-save verdict history (best-effort)
        try:
            save_verdict_document(analysis_result, None)
        except Exception as _e:
            # Do not fail the request if autosave fails
            print(f"WARNING: Autosave of verdict failed: {_e}")

        return [analysis_result]

    except Exception as e:
        # Print the full error to the console for debugging
        print(traceback.format_exc())
        # Re-raise HTTP exceptions, otherwise wrap as a 500 error.
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")


@app.get("/analysis/history")
@app.get("/api/analysis/history")
async def get_all_analysis_history(ticker: str = "", page: int = 1, page_size: int = 20):
    """Retrieve paginated analysis history entries, optionally filtered by ticker."""
    try:
        loop = asyncio.get_running_loop()
        history = await loop.run_in_executor(
            None,
            lambda: list_analysis_history(ticker, page=page, page_size=page_size)
        )
        history['status'] = 'success'
        return history
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch analysis history: {e}")


@app.get("/analysis/history/{ticker}")
@app.get("/api/analysis/history/{ticker}")
async def get_analysis_history(ticker: str, page: int = 1, page_size: int = 20):
    """Retrieve paginated analysis history entries for a ticker."""
    return await get_all_analysis_history(ticker=ticker, page=page, page_size=page_size)


@app.delete("/analysis/history/id/{entry_id}")
@app.delete("/api/analysis/history/id/{entry_id}")
async def delete_analysis_history(entry_id: str):
    """Delete a single history entry by ID."""
    try:
        loop = asyncio.get_running_loop()
        deleted = await loop.run_in_executor(
            None,
            lambda: delete_history_entry(entry_id)
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="History entry not found")
        return {'status': 'success'}
    except HTTPException:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to delete history entry: {e}")


@app.delete("/analysis/history/{ticker}")
@app.delete("/api/analysis/history/{ticker}")
async def clear_analysis_history(ticker: str):
    """Remove all stored history entries for a ticker."""
    try:
        loop = asyncio.get_running_loop()
        deleted_count = await loop.run_in_executor(
            None,
            lambda: clear_history_for_ticker(ticker)
        )
        return {'status': 'success', 'deleted': deleted_count}
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to clear analysis history: {e}")


@app.get("/analysis/debug-option-chain")
@app.get("/api/analysis/debug-option-chain")
async def debug_option_chain(ticker: str, expiration_date: str):
    """
    Debug endpoint to fetch and return the raw option chain DataFrame from Alpaca.
    Expiration date should be in YYYYMMDD format.
    """
    try:
        df = await analysis_service.get_raw_option_chain(ticker, expiration_date)
        if df is None or df.empty:
            return {"message": "No option chain data returned from broker."}
        
        # Convert NaN to None for JSON compatibility and return as records
        df_serializable = df.replace({np.nan: None})
        return df_serializable.to_dict('records')
    except Exception as e:
        import traceback
        print(f"Error in debug_option_chain endpoint: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
