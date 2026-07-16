from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import traceback
import asyncio
from contextlib import asynccontextmanager
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
from .services import broker_service, analysis_service, company_intel_service
from .routers import portfolio, stock_selection
from .my_libs_py3.my_data import PriceDataFetcher
from .analytics.methodologies.gpt_verdict import generate_gpt_verdict
from .services.verdict_service import save_verdict_document, list_verdicts, get_verdict_by_id
from .services.risk_free_rate_history_service import list_risk_free_rate_history
from .services.risk_free_rate_scheduler_service import (
    get_health as get_risk_free_rate_health,
    get_latest_daily_rate,
    is_us_market_hours,
    run_daily_risk_free_rate_if_stale,
)
from .services.task_manager import task_manager
from .services.background_scheduler_service import (
    start_background_scheduler,
    stop_background_scheduler,
)
import numpy as np
import math
import os
import requests

# [NEW] Import fallback management components
from .analytics.expiration_fallback_config import create_default_fallback_config, FallbackStrategyConfig
from .analytics.data_quality_fallback_manager import DataQualityFallbackManager

# [NEW] Global fallback configuration instance
_global_fallback_config = None


def get_fallback_config() -> FallbackStrategyConfig:
    """Get or initialize the global fallback configuration."""
    global _global_fallback_config
    if _global_fallback_config is None:
        _global_fallback_config = create_default_fallback_config()
    return _global_fallback_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_background_scheduler()
    try:
        yield
    finally:
        await stop_background_scheduler()


app = FastAPI(
    title="Trader Intelligence API",
    description="API for stock and option analysis.",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS middleware to allow cross-origin requests from the frontend
# This is essential for frontend-backend communication in containerized environments
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3111",  # Frontend development server
        "http://host.docker.internal:3111",  # Docker internal frontend
        "http://127.0.0.1:3111",  # Alternative localhost format
        "*",  # Allow all origins for development (restrict in production)
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Allow all headers
)

app.include_router(portfolio.router)
app.include_router(stock_selection.router)

@app.get("/")
def read_root():
    """A simple endpoint to check if the API is running."""
    return {"message": "Welcome to the Trader Intelligence API"}

@app.get("/health")
@app.get("/api/health")  # Alias for nginx proxy compatibility
def health_check():
    """Health check endpoint for monitoring and load balancers."""
    return {
        "status": "healthy",
        "service": "trader-intelligence-backend",
        "version": "1.0.0",
        "timestamp": date.today().isoformat(),
        "cors_enabled": True
    }

@app.get("/cors-test")
@app.get("/api/cors-test")  # Alias for nginx proxy compatibility
def cors_test():
    """Test endpoint to verify CORS configuration is working."""
    return {
        "message": "CORS is working correctly",
        "origin_allowed": True,
        "timestamp": date.today().isoformat()
    }


@app.get("/tasks/{task_id}")
@app.get("/api/tasks/{task_id}")
async def get_background_task_status(task_id: str):
    task = task_manager.get_status(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "success", "task": task}


@app.get("/tasks/{task_id}/result")
@app.get("/api/tasks/{task_id}/result")
async def get_background_task_result(task_id: str):
    task = task_manager.get_result(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    state = task.get("state")
    if state == "SUCCESS":
        return {"status": "success", "task_id": task_id, "result": task.get("result")}
    if state == "FAILURE":
        return {"status": "failure", "task_id": task_id, "error": task.get("error")}
    return {"status": "pending", "task_id": task_id, "state": state}

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

@app.post("/calculate-risk-free-rate")
@app.post("/api/calculate-risk-free-rate")  # Alias for nginx proxy compatibility
async def get_risk_free_rate(request: RiskFreeRateRequest):
    """Calculates the market-implied risk-free rate from a basket of ETFs."""
    try:
        if not is_us_market_hours():
            return {
                "risk_free_rate": None,
                "logs": ["Skipped: US equity market is closed."],
                "skipped": True,
                "reason": "outside_market_hours",
            }
        # The service now calculates the rate across multiple standard expiries automatically.
        rate, logs = await calculate_market_implied_risk_free_rate(
            tickers=request.tickers
        )
        return {"risk_free_rate": rate, "logs": logs}
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")

@app.get("/risk-free-rate/history")
@app.get("/api/risk-free-rate/history")
async def get_risk_free_rate_history(ticker: str = "", limit: int = 200, days: int = 365):
    """Return historical risk-free rates used in past analyses."""
    try:
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(
            None,
            lambda: list_risk_free_rate_history(ticker=ticker, limit=limit, days=days),
        )
        return data
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch risk-free rate history: {e}")


@app.get("/risk-free-rate/health")
@app.get("/api/risk-free-rate/health")
async def get_daily_risk_free_rate_health():
    """Return whether today's market-implied risk-free rate has been calculated."""
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, get_risk_free_rate_health)
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch risk-free rate health: {e}")


@app.get("/risk-free-rate/latest")
@app.get("/api/risk-free-rate/latest")
async def get_latest_risk_free_rate():
    """Return the most recently calculated daily risk-free rate."""
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, get_latest_daily_rate)
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch latest risk-free rate: {e}")


@app.post("/risk-free-rate/run/async")
@app.post("/api/risk-free-rate/run/async")
async def run_daily_risk_free_rate_async():
    """Calculate today's risk-free rate in the background if missing (trading days and market hours only)."""
    try:
        task_id = task_manager.submit("RiskFreeRate", run_daily_risk_free_rate_if_stale)
        return {"task_id": task_id, "status_url": f"/api/tasks/{task_id}"}
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to queue risk-free rate calculation: {e}")

@app.post("/analysis/verdicts")
@app.post("/api/analysis/verdicts")
async def save_verdict(request: SaveVerdictRequest):
    """Save an analysis verdict snapshot for later retrieval/compare."""
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: save_verdict_document(request.verdict, request.label)
        )
        return result
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to save verdict: {e}")

@app.get("/analysis/verdicts/{ticker}")
@app.get("/api/analysis/verdicts/{ticker}")
async def list_saved_verdicts(ticker: str, page: int = 1, page_size: int = 25):
    """List saved verdicts for a ticker with pagination (most recent first)."""
    try:
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(
            None,
            lambda: list_verdicts(ticker.upper(), page=page, page_size=page_size)
        )
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
        loop = asyncio.get_running_loop()
        doc = await loop.run_in_executor(None, lambda: get_verdict_by_id(doc_id))
        if not doc:
            raise HTTPException(status_code=404, detail="Verdict not found")
        return {"status": "success", "item": doc}
    except HTTPException:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch verdict: {e}")

@app.get("/analysis/company/fundamentals/{ticker}")
@app.get("/api/analysis/company/fundamentals/{ticker}")
async def company_fundamentals(ticker: str):
    """Fetch company fundamentals from Mongo screener + Finviz."""
    try:
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(
            None,
            lambda: company_intel_service.get_fundamentals(ticker.upper()),
        )
        return {"status": "success", "fundamentals": data}
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch fundamentals: {e}")


@app.get("/analysis/company/deep-dive/{ticker}")
@app.get("/api/analysis/company/deep-dive/{ticker}")
async def company_deep_dive(ticker: str, force: bool = False):
    """Return cached company deep dive or generate from Finviz + Mongo via Gemini."""
    try:
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(
            None,
            lambda: company_intel_service.get_or_create_deep_dive(ticker.upper(), force=force),
        )
        return {"status": "success", "deep_dive": data}
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch company deep dive: {e}")

@app.post("/analysis/stock-gpt")
async def analyze_stock_with_gpt(request: AnalysisRequest):
    """
    Alternative methodology: run the standard sub-analyses, then ask an LLM to produce the final verdict
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
            if "Could not fetch valid current price" in error_message:
                print(f"INFO: Price fetch failed for {request.ticker}, attempting broker fallback.")
                fetcher = PriceDataFetcher()
                new_price = await fetcher.get_current_price_from_broker_async(request.ticker.upper())
                if new_price:
                    print(f"INFO: Retrying analysis for {request.ticker} with broker price: {new_price}")
                    base_result = await run_full_analysis(
                        ticker=request.ticker.upper(),
                        expiration_date=expiration_date,
                        r_current=request.risk_free_rate,
                        methodology='gpt-verdict',  # Use the gpt-verdict methodology
                        gpt_model=request.gpt_model,
                        override_price=new_price
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
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: save_verdict_document(result, None)
            )
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

@app.get("/api/perplexity-models")
@app.get("/perplexity-models")  # Alias for Docker/proxy compatibility
async def get_available_perplexity_models():
    """Static list of Perplexity Sonar models for Web Verdict analysis."""
    from .analytics.methodologies.perplexity_research import (
        list_perplexity_models,
        resolve_perplexity_model,
    )

    default_model = resolve_perplexity_model(os.getenv("PERPLEXITY_MODEL", "sonar"))
    return {
        "status": "success",
        "models": list_perplexity_models(),
        "default": default_model,
    }


@app.get("/api/gpt-models")
@app.get("/gpt-models")  # Alias for Docker/proxy compatibility
async def get_available_gpt_models():
    """Fetches available Gemini models for GPT verdict analysis."""
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        
        if not api_key:
            raise HTTPException(status_code=500, detail="Gemini API key not configured")
        
        # Fetch available models from Gemini API.
        response = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key},
            timeout=10
        )
        
        if response.status_code != 200:
            detail_text = response.text[:200] if response.text else ""
            mapped_status = response.status_code if response.status_code in (401, 403, 429) else 500
            raise HTTPException(
                status_code=mapped_status,
                detail=f"Failed to fetch Gemini models ({response.status_code}): {detail_text}"
            )
        
        models_data = response.json()
        
        # Extract model list from Gemini API response format.
        models = []
        for model in models_data.get("models", []):
            name = model.get("name", "")
            if not name.startswith("models/"):
                continue
            generation_methods = model.get("supportedGenerationMethods", [])
            if "generateContent" not in generation_methods:
                continue
            model_id = name.split("/", 1)[1]
            models.append(
                {
                    "id": model_id,
                    "name": model.get("displayName", model_id),
                }
            )
        
        # Sort models by name for better UX
        models.sort(key=lambda x: x["name"])
        
        return {
            "status": "success",
            "models": models,
            "default": os.getenv("GEMINI_DEFAULT_MODEL", "gemini-2.5-flash")
        }
        
    except HTTPException:
        raise
    except requests.RequestException as e:
        print(f"Error fetching models: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to connect to model service: {e}")
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")


@app.post("/analysis/data-quality-check")
@app.post("/api/analysis/data-quality-check")
async def check_data_quality(request: AnalysisRequest):
    """
    Endpoint to check data quality for a specific ticker and expiration
    without running the full analysis. Used for early guardrails.
    """
    try:
        from src.services.analysis_service import check_data_quality_only
        
        # We need to parse the date string from the request
        from datetime import datetime
        try:
            exp_date = datetime.strptime(request.expiration_date, '%Y%m%d').date()
        except ValueError:
            try:
                exp_date = datetime.strptime(request.expiration_date, '%Y-%m-%d').date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYYMMDD or YYYY-MM-DD")

        quality_assessment = await check_data_quality_only(
            ticker=request.ticker,
            expiration_date=exp_date
        )
        
        return {"quality_assessment": quality_assessment}
        
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"Error checking data quality: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

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

        quality_assessment = await analysis_service.check_data_quality_only(
            ticker=request.ticker.upper(),
            expiration_date=expiration_date
        )

        quality_level = quality_assessment.get("overall_level", "failed")
        combined_score = quality_assessment.get("combined_score", quality_assessment.get("quality_score", 0.0))
        pass_threshold = quality_assessment.get("thresholds_used", {}).get("pass_threshold", 0.6)
        quality_failed = (
            combined_score < pass_threshold or
            quality_level in ["acceptable", "poor", "failed"]
        )

        if quality_failed and not request.caution_mode:
            blocked_result = {
                "status": "analysis_blocked",
                "analysis_blocked": True,
                "message": (
                    f"Analysis blocked for {request.ticker.upper()} {request.expiration_date}. "
                    f"Data quality did not pass (level={quality_level}, score={combined_score:.2f}, "
                    f"threshold={pass_threshold:.2f})."
                ),
                "quality_assessment": quality_assessment,
                "allow_override": True
            }
            return [blocked_result]

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
            if "Could not fetch valid current price" in error_message:
                print(f"INFO: Price fetch failed for {request.ticker}, attempting broker fallback.")
                fetcher = PriceDataFetcher()
                new_price = await fetcher.get_current_price_from_broker_async(request.ticker.upper())
                if new_price:
                    print(f"INFO: Retrying analysis for {request.ticker} with broker price: {new_price}")
                    analysis_result = await run_full_analysis(
                        ticker=request.ticker.upper(),
                        expiration_date=expiration_date,
                        r_current=request.risk_free_rate,
                        methodology=request.analysis_method,
                        gpt_model=request.gpt_model,
                        override_price=new_price
                    )

            if analysis_result.get("status") != "success":
                error_message = analysis_result.get("message", "Analysis failed for the selected date.")
                raise HTTPException(status_code=400, detail=error_message)

        # The frontend expects an array of results, so we wrap the single result in a list.
        # We also calculate and add the DTE (days to expiration) for display purposes.
        analysis_result['expiration_date'] = request.expiration_date
        analysis_result['dte'] = (expiration_date - date.today()).days
        analysis_result['quality_assessment'] = quality_assessment
        analysis_result['caution_mode_active'] = bool(request.caution_mode and quality_failed)

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
            await loop.run_in_executor(
                None,
                lambda: save_verdict_document(analysis_result, None)
            )
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


async def _run_analysis_in_executor(request: AnalysisRequest):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: asyncio.run(analyze_stock(request)))


@app.post("/analysis/stock/async")
@app.post("/api/analysis/stock/async")
async def analyze_stock_async(request: AnalysisRequest):
    task_id = task_manager.submit("Analysis", lambda: _run_analysis_in_executor(request))
    return {"task_id": task_id, "status_url": f"/api/tasks/{task_id}"}


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


# [NEW] Intelligent Fallback Configuration Endpoints
@app.get("/api/config/fallback")
@app.get("/config/fallback")
async def get_fallback_configuration():
    """Get current intelligent fallback configuration."""
    try:
        config = get_fallback_config()

        # Create a serializable version of the configuration
        config_dict = {
            "expiration_strategy": {
                "target_dte_preferences": config.expiration_strategy.target_dte_preferences,
                "search_window_days": config.expiration_strategy.search_window_days,
                "max_search_attempts": config.expiration_strategy.max_search_attempts,
                "search_direction": config.expiration_strategy.search_direction,
                "min_dte": config.expiration_strategy.min_dte,
                "max_dte": config.expiration_strategy.max_dte,
                "min_quality_threshold": config.expiration_strategy.min_quality_threshold,
                "acceptable_quality_threshold": config.expiration_strategy.acceptable_quality_threshold
            },
            "data_source_strategy": {
                "source_priority": [source.value for source in config.data_source_strategy.source_priority],
                "max_retries_per_source": config.data_source_strategy.max_retries_per_source,
                "inter_source_delay": config.data_source_strategy.inter_source_delay
            },
            "quality_config": {
                "trigger_thresholds": {
                    trigger.value: threshold
                    for trigger, threshold in config.quality_config.trigger_thresholds.items()
                },
                "min_valid_strikes": config.quality_config.min_valid_strikes,
                "max_spread_percentage": config.quality_config.max_spread_percentage,
                "min_open_interest": config.quality_config.min_open_interest,
                "max_data_age_minutes": config.quality_config.max_data_age_minutes
            },
            "global_config": {
                "enable_fallback": config.enable_fallback,
                "max_total_attempts": config.max_total_attempts,
                "fallback_timeout_seconds": config.fallback_timeout_seconds,
                "log_fallback_decisions": config.log_fallback_decisions,
                "log_level": config.log_level
            }
        }

        return {
            "status": "success",
            "config": config_dict
        }
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to get fallback configuration: {e}")


@app.put("/api/config/fallback")
@app.put("/config/fallback")
async def update_fallback_configuration(config_updates: dict):
    """
    Update intelligent fallback configuration settings.

    Example payload:
    {
        "enable_fallback": true,
        "expiration_strategy": {
            "target_dte_preferences": [7, 14, 30, 60],
            "search_window_days": 5
        },
        "quality_config": {
            "min_valid_strikes": 3,
            "max_spread_percentage": 0.3
        }
    }
    """
    try:
        global _global_fallback_config
        current_config = get_fallback_config()

        # Update global configuration settings
        if "enable_fallback" in config_updates:
            current_config.enable_fallback = config_updates["enable_fallback"]
        if "max_total_attempts" in config_updates:
            current_config.max_total_attempts = config_updates["max_total_attempts"]
        if "fallback_timeout_seconds" in config_updates:
            current_config.fallback_timeout_seconds = config_updates["fallback_timeout_seconds"]
        if "log_fallback_decisions" in config_updates:
            current_config.log_fallback_decisions = config_updates["log_fallback_decisions"]

        # Update expiration strategy settings
        if "expiration_strategy" in config_updates:
            exp_updates = config_updates["expiration_strategy"]
            if "target_dte_preferences" in exp_updates:
                current_config.expiration_strategy.target_dte_preferences = exp_updates["target_dte_preferences"]
            if "search_window_days" in exp_updates:
                current_config.expiration_strategy.search_window_days = exp_updates["search_window_days"]
            if "max_search_attempts" in exp_updates:
                current_config.expiration_strategy.max_search_attempts = exp_updates["max_search_attempts"]
            if "search_direction" in exp_updates:
                current_config.expiration_strategy.search_direction = exp_updates["search_direction"]
            if "min_dte" in exp_updates:
                current_config.expiration_strategy.min_dte = exp_updates["min_dte"]
            if "max_dte" in exp_updates:
                current_config.expiration_strategy.max_dte = exp_updates["max_dte"]
            if "min_quality_threshold" in exp_updates:
                current_config.expiration_strategy.min_quality_threshold = exp_updates["min_quality_threshold"]
            if "acceptable_quality_threshold" in exp_updates:
                current_config.expiration_strategy.acceptable_quality_threshold = exp_updates["acceptable_quality_threshold"]

        # Update quality configuration settings
        if "quality_config" in config_updates:
            quality_updates = config_updates["quality_config"]
            if "min_valid_strikes" in quality_updates:
                current_config.quality_config.min_valid_strikes = quality_updates["min_valid_strikes"]
            if "max_spread_percentage" in quality_updates:
                current_config.quality_config.max_spread_percentage = quality_updates["max_spread_percentage"]
            if "min_open_interest" in quality_updates:
                current_config.quality_config.min_open_interest = quality_updates["min_open_interest"]
            if "max_data_age_minutes" in quality_updates:
                current_config.quality_config.max_data_age_minutes = quality_updates["max_data_age_minutes"]

        return {
            "status": "success",
            "message": "Fallback configuration updated successfully",
            "updated_settings": config_updates
        }

    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to update fallback configuration: {e}")


@app.get("/api/config/fallback/recommendations/{ticker}")
@app.get("/config/fallback/recommendations/{ticker}")
async def get_recommended_expiration_dates_endpoint(ticker: str):
    """Get recommended expiration dates for a ticker based on liquidity patterns."""
    try:
        fetcher = PriceDataFetcher()
        recommended_dates = fetcher.get_recommended_expiration_dates(ticker.upper())

        return {
            "status": "success",
            "ticker": ticker.upper(),
            "recommended_expiration_dates": recommended_dates,
            "note": "These dates are selected for higher liquidity and better data quality"
        }

    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to get recommendations: {e}")


@app.get("/api/config/fallback/stats")
@app.get("/config/fallback/stats")
async def get_fallback_execution_stats():
    """Get statistics about fallback execution performance."""
    try:
        # Initialize a manager to get stats (this could be enhanced to track global stats)
        config = get_fallback_config()
        manager = DataQualityFallbackManager(config)

        stats = manager.get_execution_stats()

        return {
            "status": "success",
            "execution_stats": stats,
            "note": "Statistics are reset when the service restarts"
        }

    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to get fallback stats: {e}")


@app.post("/api/config/fallback/reset")
@app.post("/config/fallback/reset")
async def reset_fallback_configuration():
    """Reset fallback configuration to default settings."""
    try:
        global _global_fallback_config
        _global_fallback_config = create_default_fallback_config()

        return {
            "status": "success",
            "message": "Fallback configuration reset to default settings"
        }

    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to reset fallback configuration: {e}")
