import asyncio
from datetime import datetime
import numpy as np
from typing import List, Optional
import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from src.models.analysis_models import (
    AnalysisRequest,
    RiskFreeRateRequest,
    AnalysisResponse,
    DataQualityCheckResponse,
    ValidationFailureResponse,
    GeneralErrorResponse,
    NoDataResponse,
    QualityCheckErrorResponse,
    ValidationMetadata,
    QualityWarnings,
    ValidationStatus,
    ValidationMode
)
from src.services import analysis_service, analysis_history_service

# Import validation components
from src.services.validated_analysis_service import ValidatedAnalysisService
from src.analytics.validation_integration import validate_options_for_analysis
from src.analytics.quality_config import QualityAssessment

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/stock")
async def analyze_stock(
    request: AnalysisRequest,
    enable_validation: bool = Query(True, description="Enable data quality validation"),
    validation_mode: str = Query("standard", description="Validation mode: strict, standard, or permissive"),
    min_quality_threshold: float = Query(0.5, description="Minimum quality threshold (0.0-1.0)")
):
    """
    Runs a full, multi-faceted analysis on a stock option chain with integrated validation.

    The endpoint now includes:
    - Data quality validation before analysis
    - Appropriate error responses for insufficient data quality
    - Validation status in successful responses
    - Clear feedback about data quality issues
    """
    start_time = datetime.now()

    try:
        # Convert string date from request to date object for the service
        expiration_date = datetime.strptime(request.expiration_date, '%Y%m%d').date()

        logger.info(
            f"Analysis request: ticker={request.ticker}, "
            f"expiration={request.expiration_date}, method={request.analysis_method}, "
            f"validation={enable_validation}, mode={validation_mode}"
        )

        # Determine validation approach
        if enable_validation:
            # Use validated analysis service
            validated_service = ValidatedAnalysisService()
            validated_service.default_validation_mode = validation_mode
            validated_service.default_min_quality_threshold = min_quality_threshold

            analysis_result = await validated_service.run_validated_analysis(
                ticker=request.ticker,
                expiration_date=expiration_date,
                r_current=request.risk_free_rate,
                methodology=request.analysis_method,
                gpt_model=request.gpt_model,
                override_price=request.override_price,
                validation_mode=validation_mode,
                min_quality_threshold=min_quality_threshold
            )

            # Handle validation failures
            if analysis_result.get('status') in ['rejected', 'error']:
                return _handle_validation_failure(analysis_result, request)

            # Extract core analysis for backward compatibility
            core_analysis = analysis_result.get('analysis_results', {})

            # Add validation metadata to response
            response = {
                **core_analysis,
                'ticker': request.ticker,  # Explicitly include ticker from request
                'validation_metadata': {
                    'validation_enabled': True,
                    'validation_mode': validation_mode,
                    'validation_status': analysis_result.get('validation_status', 'completed'),
                    'quality_metrics': analysis_result.get('quality_metrics', {}),
                    'data_quality_insights': analysis_result.get('data_quality_insights', {}),
                    'validation_recommendations': analysis_result.get('validation_enhanced_recommendations', [])
                },
                'processing_time_seconds': (datetime.now() - start_time).total_seconds()
            }

            # Add quality warnings if applicable
            quality_score = analysis_result.get('quality_metrics', {}).get('overall_score', 1.0)
            if quality_score < 0.7:
                response['quality_warnings'] = _generate_quality_warnings(quality_score, analysis_result)

        else:
            # Use original analysis service without validation
            logger.warning(f"Running analysis without validation for {request.ticker}")

            analysis_result = await analysis_service.run_full_analysis(
                ticker=request.ticker,
                expiration_date=expiration_date,
                risk_free_rate=request.risk_free_rate,
                methodology=request.analysis_method,
                gpt_model=request.gpt_model,
                override_price=request.override_price
            )

            response = {
                **analysis_result,
                'ticker': request.ticker,  # Explicitly include ticker from request
                'validation_metadata': {
                    'validation_enabled': False,
                    'validation_status': 'disabled',
                    'note': 'Analysis performed without data quality validation'
                }
            }

        # Persist analysis record
        await _persist_analysis_record(request, response, enable_validation, validation_mode)

        logger.info(f"Analysis completed for {request.ticker} in {(datetime.now() - start_time).total_seconds():.1f}s")

        return response

    except ValueError as e:
        logger.error(f"Invalid request parameters: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid date format for expiration_date. Expected YYYYMMDD. Error: {e}")

    except Exception as e:
        logger.error(f"Analysis failed for {request.ticker}: {e}", exc_info=True)
        # Return structured error response with validation context
        return JSONResponse(
            status_code=500,
            content={
                'status': 'error',
                'error_type': 'analysis_failure',
                'message': str(e),
                'ticker': request.ticker,
                'expiration_date': request.expiration_date,
                'validation_enabled': enable_validation,
                'recommendations': [
                    'Check ticker symbol and expiration date',
                    'Try a different expiration date',
                    'Use permissive validation mode if validation is enabled',
                    'Contact support if the issue persists'
                ],
                'retry_suggestions': {
                    'different_expiration': f'Try other expiration dates for {request.ticker}',
                    'disable_validation': 'Set enable_validation=false to bypass validation',
                    'permissive_mode': 'Set validation_mode=permissive for more lenient validation'
                }
            }
        )


# Helper functions for validation integration
def _handle_validation_failure(analysis_result: dict, request: AnalysisRequest) -> JSONResponse:
    """Handle validation failures with appropriate HTTP responses and clear feedback."""
    error_type = analysis_result.get('error_type', 'validation_failure')
    quality_metrics = analysis_result.get('quality_metrics', {})

    # Determine appropriate HTTP status code
    if error_type == 'validation_gate_failure':
        status_code = 422  # Unprocessable Entity - data quality too low
    elif error_type == 'data_fetch_failure':
        status_code = 404  # Not Found - no data available
    elif error_type in ['service_failure', 'analysis_failure']:
        status_code = 500  # Internal Server Error
    else:
        status_code = 400  # Bad Request - general validation failure

    # Create detailed error response
    error_response = {
        'status': 'validation_failed',
        'error_type': error_type,
        'message': analysis_result.get('message', 'Data quality validation failed'),
        'ticker': request.ticker,
        'expiration_date': request.expiration_date,
        'quality_assessment': {
            'overall_score': quality_metrics.get('overall_score', 0.0),
            'threshold_used': quality_metrics.get('threshold_used', 0.5),
            'validation_mode': quality_metrics.get('validation_mode', 'unknown'),
            'asset_type': quality_metrics.get('asset_type', 'unknown')
        },
        'data_quality_issues': _extract_quality_issues(analysis_result),
        'improvement_recommendations': analysis_result.get('recommendations', []),
        'alternative_approaches': [
            {
                'approach': 'Try different expiration date',
                'reason': 'Other dates may have better data quality',
                'example': f'Use a date closer to earnings or with higher volume'
            },
            {
                'approach': 'Use permissive validation mode',
                'reason': 'Lower quality thresholds for analysis',
                'example': 'Set validation_mode=permissive in request'
            },
            {
                'approach': 'Disable validation temporarily',
                'reason': 'Proceed with analysis despite quality concerns',
                'example': 'Set enable_validation=false (use with caution)'
            }
        ],
        'retry_instructions': {
            'same_request_different_date': f'Change expiration_date to try different option chains',
            'lower_quality_threshold': f'Set min_quality_threshold to a lower value (current: {quality_metrics.get("threshold_used", 0.5)})',
            'permissive_mode': 'Set validation_mode=permissive for more lenient validation',
            'disable_validation': 'Set enable_validation=false to bypass all validation'
        }
    }

    # Add specific guidance based on error type
    if error_type == 'validation_gate_failure':
        error_response['specific_guidance'] = {
            'issue': 'Options data quality is below minimum threshold for reliable analysis',
            'impact': 'Analysis results would be unreliable and potentially misleading',
            'recommendation': 'Improve data quality or use alternative approaches listed above'
        }
    elif error_type == 'data_fetch_failure':
        error_response['specific_guidance'] = {
            'issue': 'Unable to fetch sufficient options data for analysis',
            'impact': 'Cannot perform analysis without basic options chain data',
            'recommendation': 'Check ticker symbol, verify options are available, try different expiration dates'
        }

    return JSONResponse(status_code=status_code, content=error_response)


def _generate_quality_warnings(quality_score: float, analysis_result: dict) -> dict:
    """Generate quality warnings for responses with moderate data quality."""
    warnings = {
        'overall_quality_score': quality_score,
        'quality_level': _get_quality_level_description(quality_score),
        'warnings': [],
        'recommended_actions': []
    }

    # Generate specific warnings based on quality score
    if quality_score < 0.5:
        warnings['warnings'].append('Low data quality detected - results may be unreliable')
        warnings['recommended_actions'].extend([
            'Use smaller position sizes',
            'Increase monitoring frequency',
            'Cross-validate with other data sources'
        ])
    elif quality_score < 0.7:
        warnings['warnings'].append('Moderate data quality - some limitations in analysis reliability')
        warnings['recommended_actions'].extend([
            'Monitor data quality closely',
            'Consider position size adjustments'
        ])

    # Add specific quality insights if available
    quality_insights = analysis_result.get('data_quality_insights', {})
    if quality_insights:
        weaknesses = quality_insights.get('key_weaknesses', [])
        if weaknesses:
            warnings['data_quality_concerns'] = weaknesses[:3]  # Top 3 concerns

        strengths = quality_insights.get('key_strengths', [])
        if strengths:
            warnings['data_quality_strengths'] = strengths[:3]  # Top 3 strengths

    return warnings


def _extract_quality_issues(analysis_result: dict) -> dict:
    """Extract and summarize data quality issues from analysis results."""
    issues_summary = {
        'critical_issues_count': 0,
        'high_priority_issues_count': 0,
        'main_concerns': [],
        'affected_categories': []
    }

    # Extract from validation report if available
    validation_report = analysis_result.get('validation_report', {})
    if validation_report:
        core_validation = validation_report.get('validation_summary', {}).get('core_validation', {})

        issues_summary['critical_issues_count'] = core_validation.get('critical_issues', 0)
        issues_summary['high_priority_issues_count'] = core_validation.get('high_priority_issues', 0)

        # Extract category performance
        category_scores = core_validation.get('category_scores', {})
        for category, score in category_scores.items():
            if score < 0.5:
                issues_summary['affected_categories'].append({
                    'category': category.replace('_', ' ').title(),
                    'score': score,
                    'severity': 'high' if score < 0.3 else 'medium'
                })

        # Add main concerns based on recommendation
        recommendation = core_validation.get('recommendation', '')
        if 'REVIEW REQUIRED' in recommendation or 'CAUTION' in recommendation:
            issues_summary['main_concerns'].append('Overall data quality below recommended thresholds')

    return issues_summary


def _get_quality_level_description(score: float) -> str:
    """Get human-readable quality level description."""
    if score >= 0.85:
        return 'Excellent - High confidence in analysis results'
    elif score >= 0.7:
        return 'Good - Analysis results should be reliable'
    elif score >= 0.5:
        return 'Fair - Use results with caution and monitoring'
    elif score >= 0.3:
        return 'Poor - Results may be unreliable, consider alternatives'
    else:
        return 'Very Poor - Analysis not recommended with current data'


async def _persist_analysis_record(request: AnalysisRequest,
                                 response: dict,
                                 enable_validation: bool,
                                 validation_mode: str):
    """Persist analysis record with validation metadata."""
    try:
        # Enhanced payload with validation metadata
        payload_to_persist = {
            'ticker': request.ticker,
            'expiration_date': request.expiration_date,
            'risk_free_rate': request.risk_free_rate,
            'analysis_method': request.analysis_method,
            'gpt_model': request.gpt_model,
            'override_price': request.override_price,
            # Validation metadata
            'validation_enabled': enable_validation,
            'validation_mode': validation_mode,
            'validation_status': response.get('validation_metadata', {}).get('validation_status', 'unknown'),
            'quality_score': response.get('validation_metadata', {}).get('quality_metrics', {}).get('overall_score')
        }

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: analysis_history_service.save_analysis_record(payload_to_persist, response)
        )

    except Exception as history_err:
        logger.warning(f"Failed to persist analysis history: {history_err}")


@router.get("/history")
async def get_analysis_history_all(ticker: str = "", page: int = 1, page_size: int = 20):
    """Fetch paginated analysis history, optionally filtered by ticker."""
    loop = asyncio.get_running_loop()
    try:
        history = await loop.run_in_executor(
            None,
            lambda: analysis_history_service.list_history(ticker, page=page, page_size=page_size)
        )
        return history
    except Exception as e:
        import traceback
        print(f"Error while fetching analysis history: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Failed to fetch analysis history")


@router.get("/history/{ticker}")
async def get_analysis_history(ticker: str, page: int = 1, page_size: int = 20):
    """Fetch paginated analysis history for the specified ticker."""
    return await get_analysis_history_all(ticker=ticker, page=page, page_size=page_size)


@router.delete("/history/id/{entry_id}")
async def delete_analysis_history_entry(entry_id: str):
    """Remove a single analysis history entry."""
    loop = asyncio.get_running_loop()
    try:
        deleted = await loop.run_in_executor(
            None,
            lambda: analysis_history_service.delete_history_entry(entry_id)
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="History entry not found")
        return {'status': 'success'}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Error deleting analysis history entry {entry_id}: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Failed to delete history entry")


@router.delete("/history/{ticker}")
async def clear_analysis_history(ticker: str):
    """Remove all history entries for a ticker."""
    loop = asyncio.get_running_loop()
    try:
        deleted_count = await loop.run_in_executor(
            None,
            lambda: analysis_history_service.clear_history_for_ticker(ticker)
        )
        return {'status': 'success', 'deleted': deleted_count}
    except Exception as e:
        import traceback
        print(f"Error clearing analysis history for {ticker}: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Failed to clear history")


@router.post("/calculate-risk-free-rate")
async def calculate_market_rate(request: RiskFreeRateRequest):
    """
    Calculates a market-implied risk-free rate from liquid ETF option chains.
    """
    try:
        # Convert string date from request to date object for the service
        expiration_date = datetime.strptime(request.expiration_date, '%Y%m%d').date()
        
        market_rate, logs = await analysis_service.calculate_market_implied_risk_free_rate(
            expiration_date=expiration_date,
            tickers=request.tickers
        )
        
        return {"risk_free_rate": market_rate, "logs": logs}
    except ValueError as e:
        # Handle date parsing errors
        raise HTTPException(status_code=400, detail=f"Invalid date format for expiration_date. Expected YYYYMMDD. Error: {e}")
    except Exception as e:
        import traceback
        print(f"Error in calculate_market_rate endpoint: {e}")
        print(traceback.format_exc())
        # Generic error handler for other issues
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/check-data-quality/{ticker}")
async def check_data_quality(
    ticker: str,
    expiration_date: str,
    detailed: bool = Query(True, description="Include detailed quality breakdown")
):
    """
    Quick data quality check for options data without running full analysis.

    This endpoint provides a fast way to assess data quality before committing
    to a full analysis, helping frontend clients make informed decisions.
    """
    try:
        logger.info(f"Data quality check for {ticker} expiration {expiration_date}")

        # Basic parameter validation
        try:
            exp_date = datetime.strptime(expiration_date, '%Y%m%d').date()
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid expiration_date format. Expected YYYYMMDD."
            )

        # Get basic options data for quality assessment
        from src.my_libs_py3.my_data import PriceDataFetcher
        price_fetcher = PriceDataFetcher()

        # Fetch option chain
        option_chain_df = price_fetcher.get_option_data_finviz(ticker, 'o', expiration_date)

        if option_chain_df is None or option_chain_df.empty:
            return JSONResponse(
                status_code=404,
                content={
                    'status': 'no_data',
                    'ticker': ticker,
                    'expiration_date': expiration_date,
                    'message': f'No options data available for {ticker} on {expiration_date}',
                    'suggestions': [
                        'Verify the ticker symbol is correct',
                        'Check if options are available for this stock',
                        'Try a different expiration date',
                        'Ensure the expiration date is in the future'
                    ]
                }
            )

        # Convert to standardized format for validation
        options_data = _convert_dataframe_to_greeks_format(option_chain_df)

        # Run validation check
        validation_results = validate_options_for_analysis(
            options_data=options_data,
            ticker=ticker,
            expiration_date=expiration_date
        )

        # Extract quality metrics
        quality_metrics = validation_results.get('data_quality_metrics', {})
        core_validation = validation_results.get('validation_summary', {}).get('core_validation', {})

        # Build response
        quality_check_result = {
            'status': 'completed',
            'ticker': ticker,
            'expiration_date': expiration_date,
            'assessment_timestamp': datetime.now().isoformat(),
            'overall_quality_score': quality_metrics.get('consolidated_quality_score', 0.0),
            'quality_level': _get_quality_level_description(quality_metrics.get('consolidated_quality_score', 0.0)),
            'analysis_recommendation': _get_analysis_recommendation(quality_metrics.get('consolidated_quality_score', 0.0)),
            'data_availability': {
                'total_option_contracts': len(option_chain_df),
                'strikes_available': len(options_data),
                'calls_and_puts_available': sum(1 for strike_data in options_data.values()
                                              if 'call' in strike_data and 'put' in strike_data)
            }
        }

        # Add detailed breakdown if requested
        if detailed:
            quality_check_result['detailed_assessment'] = {
                'category_scores': core_validation.get('category_scores', {}),
                'strikes_by_quality': core_validation.get('strikes_by_quality', {}),
                'critical_issues': core_validation.get('critical_issues', 0),
                'high_priority_issues': core_validation.get('high_priority_issues', 0),
                'data_completeness': {
                    'pricing_data_complete': _assess_pricing_completeness(options_data),
                    'greeks_data_complete': _assess_greeks_completeness(options_data),
                    'liquidity_data_complete': _assess_liquidity_completeness(options_data)
                }
            }

            # Add recommendations based on quality
            quality_check_result['recommendations'] = _generate_data_quality_recommendations(
                quality_metrics.get('consolidated_quality_score', 0.0),
                validation_results
            )

        return quality_check_result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Data quality check failed for {ticker}: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                'status': 'error',
                'ticker': ticker,
                'expiration_date': expiration_date,
                'message': f'Data quality check failed: {str(e)}',
                'error_type': 'quality_check_failure'
            }
        )


def _convert_dataframe_to_greeks_format(df) -> dict:
    """Convert options dataframe to greeks_by_strike format for validation."""
    options_data = {}

    for _, row in df.iterrows():
        strike = str(row.get('Strike', ''))
        option_type = 'call' if row.get('Type', '').lower() == 'call' else 'put'

        if strike not in options_data:
            options_data[strike] = {}

        options_data[strike][option_type] = {
            'bid': row.get('Bid'),
            'ask': row.get('Ask'),
            'last': row.get('Last'),
            'volume': row.get('Volume'),
            'open_interest': row.get('Open Int'),
            'delta': row.get('Delta'),
            'gamma': row.get('Gamma'),
            'theta': row.get('Theta'),
            'vega': row.get('Vega'),
            'rho': row.get('Rho')
        }

    return options_data


def _assess_pricing_completeness(options_data: dict) -> dict:
    """Assess completeness of pricing data."""
    total_options = 0
    complete_pricing = 0

    for strike_data in options_data.values():
        for option_type in ['call', 'put']:
            if option_type in strike_data:
                total_options += 1
                option_data = strike_data[option_type]
                if (option_data.get('bid') is not None and
                    option_data.get('ask') is not None):
                    complete_pricing += 1

    return {
        'completeness_ratio': complete_pricing / max(total_options, 1),
        'complete_count': complete_pricing,
        'total_count': total_options
    }


def _assess_greeks_completeness(options_data: dict) -> dict:
    """Assess completeness of Greeks data."""
    total_options = 0
    complete_greeks = 0
    required_greeks = ['delta', 'gamma', 'theta', 'vega', 'rho']

    for strike_data in options_data.values():
        for option_type in ['call', 'put']:
            if option_type in strike_data:
                total_options += 1
                option_data = strike_data[option_type]
                if all(option_data.get(greek) is not None for greek in required_greeks):
                    complete_greeks += 1

    return {
        'completeness_ratio': complete_greeks / max(total_options, 1),
        'complete_count': complete_greeks,
        'total_count': total_options,
        'required_greeks': required_greeks
    }


def _assess_liquidity_completeness(options_data: dict) -> dict:
    """Assess completeness of liquidity data."""
    total_options = 0
    complete_liquidity = 0

    for strike_data in options_data.values():
        for option_type in ['call', 'put']:
            if option_type in strike_data:
                total_options += 1
                option_data = strike_data[option_type]
                if (option_data.get('volume') is not None and
                    option_data.get('open_interest') is not None):
                    complete_liquidity += 1

    return {
        'completeness_ratio': complete_liquidity / max(total_options, 1),
        'complete_count': complete_liquidity,
        'total_count': total_options
    }


def _get_analysis_recommendation(quality_score: float) -> dict:
    """Get analysis recommendation based on quality score."""
    if quality_score >= 0.8:
        return {
            'recommendation': 'PROCEED',
            'confidence': 'HIGH',
            'message': 'Data quality is excellent - analysis should be highly reliable'
        }
    elif quality_score >= 0.65:
        return {
            'recommendation': 'PROCEED',
            'confidence': 'MEDIUM',
            'message': 'Data quality is good - analysis should be reliable with standard monitoring'
        }
    elif quality_score >= 0.45:
        return {
            'recommendation': 'PROCEED_WITH_CAUTION',
            'confidence': 'LOW',
            'message': 'Data quality is acceptable - use enhanced monitoring and consider position size adjustments'
        }
    else:
        return {
            'recommendation': 'REVIEW_REQUIRED',
            'confidence': 'VERY_LOW',
            'message': 'Data quality is poor - consider alternative approaches or improve data quality'
        }


def _generate_data_quality_recommendations(quality_score: float, validation_results: dict) -> list:
    """Generate specific recommendations based on data quality assessment."""
    recommendations = []

    if quality_score >= 0.8:
        recommendations.append('Data quality is excellent - proceed with full analysis')
    elif quality_score >= 0.6:
        recommendations.extend([
            'Data quality is good - proceed with standard analysis',
            'Monitor key metrics during analysis'
        ])
    elif quality_score >= 0.4:
        recommendations.extend([
            'Data quality is moderate - use enhanced validation mode',
            'Consider reducing position sizes',
            'Increase monitoring frequency'
        ])
    else:
        recommendations.extend([
            'Data quality is poor - consider alternative approaches',
            'Try different expiration dates',
            'Look for more liquid options',
            'Use manual data review before proceeding'
        ])

    # Add specific recommendations based on validation results
    consolidated_recs = validation_results.get('consolidated_recommendations', {})
    if consolidated_recs.get('alternative_sources_recommended'):
        recommendations.append('Consider using alternative data sources')

    if consolidated_recs.get('data_repair_recommended'):
        recommendations.append('Data repair mechanisms may improve quality')

    return recommendations[:5]  # Limit to top 5 recommendations


@router.get("/debug-option-chain")
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


@router.get("/debug-spy-quality")
async def debug_spy_quality_analysis(expiration_date: str = None):
    """
    TEMPORARY DEBUG ENDPOINT: Detailed quality analysis breakdown for SPY options data.
    Specifically designed to debug why SPY is getting a 0.33 quality score.
    Expiration date should be in YYYYMMDD format. If not provided, uses next available expiration.
    """
    try:
        from datetime import datetime, date, timedelta
        import json
        from src.analytics.analysis import run_analysis
        from src.analytics.methodologies.gpt_verdict import generate_gpt_verdict

        ticker = "SPY"

        # Use provided expiration or find next available one
        if expiration_date:
            exp_date = datetime.strptime(expiration_date, '%Y%m%d').date()
        else:
            # Use next Friday as default
            today = date.today()
            days_ahead = 4 - today.weekday()  # Friday is 4
            if days_ahead <= 0:  # Target day already happened this week
                days_ahead += 7
            exp_date = today + timedelta(days_ahead)

        print(f"\n=== SPY QUALITY DEBUG SESSION ===")
        print(f"Ticker: {ticker}")
        print(f"Expiration: {exp_date}")
        print(f"Debugging quality score calculation...")
        print("=" * 50)

        # Run the full analysis with enhanced logging
        analysis_result = run_analysis(
            ticker=ticker,
            expiration_date=exp_date,
            r_current=0.05,
            analysis_method='holistic-market-edge'
        )

        # Extract quality score information
        quality_info = {
            "ticker": ticker,
            "expiration_date": exp_date.strftime('%Y%m%d'),
            "analysis_timestamp": datetime.now().isoformat(),
            "debug_purpose": "Investigate SPY 0.33 quality score issue"
        }

        # Check if GPT verdict was generated (contains quality validation)
        if 'gpt_verdict' in analysis_result:
            verdict = analysis_result['gpt_verdict']

            # Extract quality metrics from verdict if available
            if isinstance(verdict, dict):
                quality_info.update({
                    "gpt_verdict_present": True,
                    "verdict_keys": list(verdict.keys()) if verdict else [],
                })

                # Look for quality-related information
                for key, value in verdict.items():
                    if 'quality' in key.lower() or 'validation' in key.lower():
                        quality_info[f"verdict_{key}"] = value
        else:
            quality_info["gpt_verdict_present"] = False
            quality_info["note"] = "No GPT verdict generated - likely failed quality checks"

        # Check for options positioning data
        if 'options_positioning' in analysis_result:
            positioning = analysis_result['options_positioning']
            quality_info["options_positioning_present"] = True
            quality_info["positioning_keys"] = list(positioning.keys()) if isinstance(positioning, dict) else "not_dict"

            # Look for greeks and validation data
            if isinstance(positioning, dict):
                if 'greeks_by_strike' in positioning:
                    greeks_data = positioning['greeks_by_strike']
                    quality_info["greeks_strikes_count"] = len(greeks_data) if isinstance(greeks_data, dict) else "not_dict"
                    if isinstance(greeks_data, dict) and len(greeks_data) > 0:
                        sample_strike = list(greeks_data.keys())[0]
                        quality_info["sample_strike_key"] = sample_strike
                        quality_info["sample_strike_data"] = greeks_data[sample_strike]

                if 'valid_strikes' in positioning:
                    valid_strikes = positioning['valid_strikes']
                    quality_info["valid_strikes_count"] = len(valid_strikes) if isinstance(valid_strikes, list) else "not_list"
                    quality_info["valid_strikes_sample"] = valid_strikes[:5] if isinstance(valid_strikes, list) and valid_strikes else []
        else:
            quality_info["options_positioning_present"] = False

        # Include full analysis result for debugging (truncated for response size)
        result_keys = list(analysis_result.keys()) if isinstance(analysis_result, dict) else "not_dict"
        quality_info["analysis_result_keys"] = result_keys

        print(f"\n=== DEBUG SUMMARY ===")
        print(f"Quality analysis completed for {ticker}")
        print(f"Check console logs above for detailed quality factor breakdowns")
        print("=" * 50)

        return {
            "message": "SPY quality debug analysis completed - check server logs for detailed breakdown",
            "quality_debug_info": quality_info,
            "instructions": "Look for QUALITY_DEBUG, STRIKE_DEBUG, FIELD_DEBUG, and LEGACY_QUALITY_DEBUG logs in server console",
            "note": "This is a temporary debug endpoint - remove after investigation"
        }

    except Exception as e:
        import traceback
        error_details = {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "traceback": traceback.format_exc()
        }
        print(f"Error in debug_spy_quality_analysis: {e}")
        print(traceback.format_exc())
        return {
            "error": "Debug analysis failed",
            "details": error_details,
            "note": "Check server logs for full error details"
        }
