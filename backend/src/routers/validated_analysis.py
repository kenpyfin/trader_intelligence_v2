"""
Enhanced Analysis Router with Integrated Validation

This router provides endpoints for running validated options analysis with
comprehensive data quality checks, cross-source validation, and strategy-specific
validation gates.

Author: Quantitative Analysis & Financial Modeling Specialist
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import JSONResponse

# Import models
from ..models.validated_analysis_models import (
    ValidatedAnalysisRequest,
    ValidatedAnalysisResponse,
    StrategyValidationRequest,
    DataQualityCheckRequest,
    DataQualityReport,
    ValidationFailureResponse,
    ValidationMode,
    TradingStrategyName
)

# Import services
from ..services.validated_analysis_service import ValidatedAnalysisService
from ..services import analysis_history_service

# Import validation components
from ..analytics.strategy_validation_gates import default_strategy_gates
from ..analytics.validation_integration import validate_options_for_analysis

router = APIRouter(prefix="/validated", tags=["Validated Analysis"])
logger = logging.getLogger(__name__)


@router.post("/analyze", response_model=ValidatedAnalysisResponse)
async def run_validated_analysis(request: ValidatedAnalysisRequest):
    """
    Run comprehensive options analysis with integrated data validation.

    This endpoint performs full options analysis with:
    - Pre-analysis data quality validation
    - Cross-source validation between Finviz and calculated data
    - Strategy-specific validation gates (if strategies specified)
    - Quality-threshold-based filtering

    Returns comprehensive analysis results with validation insights.
    """
    start_time = datetime.now()

    try:
        # Convert string date to date object
        expiration_date = datetime.strptime(request.expiration_date, '%Y%m%d').date()

        logger.info(
            f"Starting validated analysis for {request.ticker} "
            f"(expiration: {request.expiration_date}, mode: {request.validation_mode})"
        )

        # Initialize validated analysis service
        service = ValidatedAnalysisService()

        # Configure validation settings
        service.default_validation_mode = request.validation_mode
        service.default_min_quality_threshold = request.min_quality_threshold
        service.enable_cross_source_validation = request.enable_cross_source_validation

        # Run validated analysis
        analysis_result = await service.run_validated_analysis(
            ticker=request.ticker,
            expiration_date=expiration_date,
            r_current=request.risk_free_rate,
            methodology=request.analysis_method,
            gpt_model=request.gpt_model,
            override_price=request.override_price,
            validation_mode=request.validation_mode.value,
            min_quality_threshold=request.min_quality_threshold,
            target_strategies=[s.value for s in request.target_strategies] if request.target_strategies else None
        )

        # Handle validation failures
        if analysis_result.get('status') in ['rejected', 'error']:
            return _handle_analysis_failure(analysis_result, request)

        # Calculate processing time
        processing_time = (datetime.now() - start_time).total_seconds()
        analysis_result['processing_time_seconds'] = processing_time

        # Log successful completion
        quality_score = analysis_result.get('quality_metrics', {}).get('overall_score', 0.0)
        logger.info(
            f"Validated analysis completed for {request.ticker} "
            f"(quality: {quality_score:.1%}, time: {processing_time:.1f}s)"
        )

        # Persist analysis record in background
        await _persist_analysis_record(request, analysis_result)

        # Convert to response model
        response = ValidatedAnalysisResponse(
            status=analysis_result.get('status', 'success'),
            validation_status=analysis_result.get('validation_status', 'completed'),
            analysis_results=analysis_result.get('analysis_results', {}),
            validation_report=analysis_result.get('validation_report', {}),
            quality_metrics=analysis_result.get('quality_metrics', {}),
            strategy_validation=analysis_result.get('strategy_validation'),
            filtered_strategies=analysis_result.get('filtered_strategies'),
            cross_source_validation=analysis_result.get('cross_source_validation'),
            validation_enhanced_recommendations=analysis_result.get('validation_enhanced_recommendations', []),
            validation_summary=analysis_result.get('validation_summary', {}),
            processing_time_seconds=processing_time,
            data_sources_used=['finviz', 'calculated']  # Could be made dynamic
        )

        return response

    except ValueError as e:
        logger.error(f"Invalid request parameters: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid parameters: {e}")

    except asyncio.TimeoutError:
        logger.error(f"Analysis timeout for {request.ticker}")
        raise HTTPException(
            status_code=504,
            detail="Analysis timed out - try with simpler validation mode or different expiration date"
        )

    except Exception as e:
        logger.error(f"Validated analysis failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}"
        )


@router.post("/validate-strategies")
async def validate_strategies(request: StrategyValidationRequest):
    """
    Validate options data against specific trading strategies.

    This endpoint checks whether the available options data meets the minimum
    quality requirements for the specified trading strategies.
    """
    try:
        # Convert string date to date object
        expiration_date = datetime.strptime(request.expiration_date, '%Y%m%d').date()

        logger.info(f"Validating strategies for {request.ticker}: {request.strategies}")

        # First get the options data (lightweight analysis)
        from ..services.analysis_service import run_full_analysis

        analysis_result = await run_full_analysis(
            ticker=request.ticker,
            expiration_date=expiration_date,
            r_current=request.risk_free_rate,
            methodology='basic',  # Use basic methodology for faster processing
            override_price=request.override_price
        )

        if analysis_result.get('status') == 'error':
            raise HTTPException(
                status_code=400,
                detail=f"Could not fetch options data: {analysis_result.get('message')}"
            )

        # Extract options data
        options_data = analysis_result.get('options_positioning', {}).get('greeks_by_strike', {})
        spot_price = analysis_result.get('market_context', {}).get('current_price')

        if not options_data:
            raise HTTPException(
                status_code=400,
                detail="No options data available for strategy validation"
            )

        # Validate each strategy
        validation_results = {}
        for strategy in request.strategies:
            try:
                result = default_strategy_gates.validate_strategy(
                    strategy=strategy,
                    options_data=options_data,
                    ticker=request.ticker,
                    expiration_date=request.expiration_date,
                    spot_price=spot_price
                )

                validation_results[strategy.value] = {
                    'gate_decision': result.gate_decision,
                    'decision_confidence': result.decision_confidence,
                    'quality_score_vs_threshold': result.quality_score_vs_threshold,
                    'recommended_position_size_factor': result.recommended_position_size_factor,
                    'risk_warnings': result.risk_warnings,
                    'approval_conditions': result.approval_conditions,
                    'improvement_recommendations': result.improvement_recommendations
                }

            except Exception as e:
                logger.warning(f"Strategy validation failed for {strategy}: {e}")
                validation_results[strategy.value] = {
                    'gate_decision': 'ERROR',
                    'error': str(e)
                }

        # Summarize results
        approved = [s for s, r in validation_results.items() if r.get('gate_decision') == 'APPROVE']
        conditional = [s for s, r in validation_results.items() if r.get('gate_decision') == 'APPROVE_WITH_CAUTION']
        rejected = [s for s, r in validation_results.items() if r.get('gate_decision') in ['REJECT', 'ERROR']]

        return {
            'ticker': request.ticker,
            'expiration_date': request.expiration_date,
            'validation_timestamp': datetime.now().isoformat(),
            'strategies_tested': [s.value for s in request.strategies],
            'validation_results': validation_results,
            'summary': {
                'approved_strategies': approved,
                'conditional_strategies': conditional,
                'rejected_strategies': rejected,
                'total_usable': len(approved) + len(conditional)
            },
            'recommendation': (
                f"Proceed with {len(approved)} approved and {len(conditional)} conditional strategies"
                if approved or conditional else
                "No strategies meet validation requirements - consider alternative approaches"
            )
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
    except Exception as e:
        logger.error(f"Strategy validation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check-data-quality", response_model=DataQualityReport)
async def check_data_quality(request: DataQualityCheckRequest):
    """
    Perform standalone data quality assessment without full analysis.

    This endpoint provides a fast way to assess options data quality before
    committing to a full analysis.
    """
    try:
        logger.info(f"Checking data quality for {request.ticker}")

        # Get basic options data
        from ..my_libs_py3.my_data import PriceDataFetcher

        price_fetcher = PriceDataFetcher()

        # Fetch option chain data
        option_chain_df = price_fetcher.get_option_data_finviz(
            request.ticker, 'o', request.expiration_date
        )

        if option_chain_df is None or option_chain_df.empty:
            raise HTTPException(
                status_code=404,
                detail=f"No options data available for {request.ticker} on {request.expiration_date}"
            )

        # Convert to greeks_by_strike format for validation
        # This is a simplified conversion - full analysis would have more complete data
        options_data = {}
        for _, row in option_chain_df.iterrows():
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

        # Run comprehensive validation
        validation_results = validate_options_for_analysis(
            options_data=options_data,
            ticker=request.ticker,
            expiration_date=request.expiration_date
        )

        # Extract quality metrics
        core_validation = validation_results.get('validation_summary', {}).get('core_validation', {})
        quality_metrics = validation_results.get('data_quality_metrics', {})

        # Build response
        report = DataQualityReport(
            ticker=request.ticker,
            expiration_date=request.expiration_date,
            assessment_timestamp=datetime.now().isoformat(),
            overall_quality_score=quality_metrics.get('consolidated_quality_score', 0.0),
            category_scores=core_validation.get('category_scores', {}),
            quality_level=_determine_quality_level(quality_metrics.get('consolidated_quality_score', 0.0)),
            strikes_analysis=validation_results.get('strike_analysis', {}),
            issues_summary={
                'critical_issues': core_validation.get('critical_issues', 0),
                'high_priority_issues': core_validation.get('high_priority_issues', 0)
            },
            recommendations=validation_results.get('consolidated_recommendations', {}).get('improvement_recommendations', [])
        )

        return report

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid parameters: {e}")
    except Exception as e:
        logger.error(f"Data quality check failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategy-requirements/{strategy}")
async def get_strategy_requirements(strategy: TradingStrategyName):
    """
    Get the validation requirements for a specific trading strategy.

    Returns the minimum data quality thresholds, required Greeks,
    and other validation criteria for the specified strategy.
    """
    try:
        requirements = default_strategy_gates.get_strategy_requirements(strategy)

        if 'error' in requirements:
            raise HTTPException(status_code=404, detail=requirements['error'])

        return {
            'strategy': strategy.value,
            'requirements': requirements,
            'description': f"Validation requirements for {strategy.value.replace('_', ' ').title()} strategy",
            'last_updated': datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to get strategy requirements: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/compare-strategy-requirements")
async def compare_strategy_requirements(
    strategies: List[TradingStrategyName] = Query(..., description="Strategies to compare")
):
    """
    Compare validation requirements across multiple trading strategies.

    Useful for understanding which strategies are most/least strict in their
    data quality requirements.
    """
    try:
        if len(strategies) < 2:
            raise HTTPException(
                status_code=400,
                detail="At least 2 strategies required for comparison"
            )

        comparison = default_strategy_gates.compare_strategies(strategies)
        comparison['comparison_timestamp'] = datetime.now().isoformat()
        comparison['strategies_requested'] = [s.value for s in strategies]

        return comparison

    except Exception as e:
        logger.error(f"Strategy comparison failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/validation-health")
async def validation_health_check():
    """
    Health check endpoint for the validation system.

    Returns status of validation components and system configuration.
    """
    try:
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'components': {
                'core_validation_engine': 'operational',
                'strategy_gates': 'operational',
                'cross_source_validation': 'operational',
                'validation_orchestrator': 'operational'
            },
            'configuration': {
                'default_validation_mode': 'standard',
                'default_quality_threshold': 0.5,
                'cross_source_validation_enabled': True,
                'supported_strategies': len(list(TradingStrategyName)),
                'supported_validation_modes': len(list(ValidationMode))
            },
            'version': '1.0.0'
        }

        return health_status

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
        )


# Helper functions
def _handle_analysis_failure(analysis_result: dict, request: ValidatedAnalysisRequest) -> JSONResponse:
    """Handle analysis failures with appropriate HTTP responses."""
    status_code = 400

    if analysis_result.get('error_type') == 'validation_gate_failure':
        status_code = 422  # Unprocessable Entity
    elif analysis_result.get('error_type') in ['service_failure', 'analysis_failure']:
        status_code = 500

    return JSONResponse(
        status_code=status_code,
        content={
            'status': 'failed',
            'error_type': analysis_result.get('error_type', 'unknown'),
            'message': analysis_result.get('message', 'Analysis failed'),
            'validation_report': analysis_result.get('validation_report'),
            'recommendations': analysis_result.get('recommendations', []),
            'quality_metrics': analysis_result.get('quality_metrics'),
            'retry_suggestions': [
                'Try a different expiration date',
                'Use permissive validation mode',
                'Check data source availability'
            ]
        }
    )


async def _persist_analysis_record(request: ValidatedAnalysisRequest, result: dict):
    """Persist analysis record in background."""
    try:
        payload = {
            'ticker': request.ticker,
            'expiration_date': request.expiration_date,
            'risk_free_rate': request.risk_free_rate,
            'analysis_method': request.analysis_method,
            'gpt_model': request.gpt_model,
            'override_price': request.override_price,
            'validation_mode': request.validation_mode.value,
            'min_quality_threshold': request.min_quality_threshold,
            'validation_enabled': True
        }

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: analysis_history_service.save_analysis_record(payload, result)
        )

    except Exception as e:
        logger.warning(f"Failed to persist analysis record: {e}")


def _determine_quality_level(score: float) -> str:
    """Determine quality level from score."""
    if score >= 0.85:
        return "excellent"
    elif score >= 0.7:
        return "good"
    elif score >= 0.5:
        return "acceptable"
    elif score >= 0.3:
        return "poor"
    else:
        return "failed"