import React, { useState, useEffect, useCallback, useRef, Component } from 'react';
import axios from 'axios';
import Plot from 'react-plotly.js';
import {
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Chip,
  CircularProgress,
  Collapse,
  Divider,
  FormControl,
  Grid,
  IconButton,
  InputLabel,
  List,
  ListItem,
  ListItemText,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
  Alert,
  AlertTitle,
  Tooltip,
  Link
} from '@mui/material';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  Refresh as RefreshIcon,
  Delete as DeleteIcon,
  SmartToy as SmartToyIcon,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  Warning as WarningIcon,
  Lightbulb as LightbulbIcon,
  Shield as ShieldIcon,
  CheckCircle as CheckCircleIcon,
  Search as SearchIcon,
  History as HistoryIcon,
  Error as ErrorIcon,
  HourglassEmpty as HourglassEmptyIcon,
  Info as InfoIcon,
  Build as BuildIcon,
  Skeleton as SkeletonIcon,
  OpenInNew as OpenInNewIcon
} from '@mui/icons-material';

// Import enhanced quality components
import DataQualityCard from '../components/DataQualityCard';
import {
  CautionBanner,
  CautionChip,
  StrategyCardWithCaution,
  ConfidenceIndicator,
  QualityScoreBadge
} from '../components/CautionModeIndicator';

import { useTaskPolling } from '../hooks/useTaskPolling';

// Missing Data Detection Utilities
const MissingDataStates = {
  LOADING: 'LOADING',
  GPT_RESPONSE_MISSING: 'GPT_RESPONSE_MISSING',
  TRADER_AGENT_FAILED: 'TRADER_AGENT_FAILED',
  SYSTEM_ERROR: 'SYSTEM_ERROR',
  DATA_QUALITY_ERROR: 'DATA_QUALITY_ERROR',
  DATA_QUALITY_CAUTION: 'DATA_QUALITY_CAUTION',  // NEW: Caution mode state
  PROCESSING: 'PROCESSING',
  PARTIAL_SUCCESS: 'PARTIAL_SUCCESS',
  COMPLETE: 'COMPLETE',
  COMPLETE_WITH_CAUTION: 'COMPLETE_WITH_CAUTION'  // NEW: Complete but with warnings
};

const ANALYSIS_PROGRESS_STAGES = [
  { id: 'queued', label: 'Task queued', threshold: 0 },
  { id: 'data_collection', label: 'Collecting market and options data', threshold: 15 },
  { id: 'guardrail_pause', label: 'Running quality and fallback checks', threshold: 40 },
  { id: 'full_analysis', label: 'Computing models and signals', threshold: 65 },
  { id: 'finalizing', label: 'Finalizing verdict and response', threshold: 90 },
];

const resolveAnalysisStage = (progressValue) => {
  const progress = Number.isFinite(progressValue) ? progressValue : 0;
  let currentStage = ANALYSIS_PROGRESS_STAGES[0].id;
  ANALYSIS_PROGRESS_STAGES.forEach((stage) => {
    if (progress >= stage.threshold) {
      currentStage = stage.id;
    }
  });
  return currentStage;
};

const extractQualityAssessmentFromResult = (payload) => {
  if (!payload) return null;
  const firstItem = Array.isArray(payload) ? payload[0] : payload;
  if (!firstItem || typeof firstItem !== 'object') return null;

  return (
    firstItem.error_details?.quality_assessment
    || firstItem.quality_assessment
    || null
  );
};

const MALFORMED_AI_JSON_NOTE = 'AI response could not be parsed as JSON';

const isMalformedAiJsonResponse = (payload) => {
  if (!payload) return false;
  const firstItem = Array.isArray(payload) ? payload[0] : payload;
  if (!firstItem || typeof firstItem !== 'object') return false;

  const summaryHtml = typeof firstItem.summary_html === 'string' ? firstItem.summary_html : '';
  const finalConclusionHtml = typeof firstItem.final_conclusion_html === 'string' ? firstItem.final_conclusion_html : '';

  return summaryHtml.includes(MALFORMED_AI_JSON_NOTE) || finalConclusionHtml.includes(MALFORMED_AI_JSON_NOTE);
};

const detectStrategyState = (strategy, gptVerdict, analysisResult, setCautionModeActive, executeAnalysis, ticker, selectedExpiration, riskFreeRate, analysisMethod, selectedModel) => {
  if (!strategy) {
    return { state: MissingDataStates.LOADING, message: 'Strategy data loading...' };
  }

  // Extract quality assessment data from analysis result
  const qualityAssessment = analysisResult?.error_details?.quality_assessment || null;
  const cautionModeActive = analysisResult?.caution_mode_active || false;

  // Check for known error types from backend fallbacks
  const errorTypes = {
    'GPT Response Missing': MissingDataStates.GPT_RESPONSE_MISSING,
    'Trader Agent Failed': MissingDataStates.TRADER_AGENT_FAILED,
    'System Error': MissingDataStates.SYSTEM_ERROR,
    'Data Quality Error': MissingDataStates.DATA_QUALITY_ERROR
  };

  if (errorTypes[strategy.type]) {
    // Enhanced: Check if caution mode is possible for data quality errors
    if (strategy.type === 'Data Quality Error' && qualityAssessment?.can_proceed_with_caution) {
      return {
        state: MissingDataStates.DATA_QUALITY_CAUTION,
        message: strategy.description || 'No additional details available',
        originalError: strategy.type,
        qualityAssessment: qualityAssessment,
        allowCaution: true
      };
    } else {
      return {
        state: errorTypes[strategy.type],
        message: strategy.description || 'No additional details available',
        originalError: strategy.type,
        qualityAssessment: qualityAssessment
      };
    }
  }

  // Check if we're running in caution mode (analysis succeeded but with warnings)
  if (cautionModeActive && strategy.legs && strategy.legs.length > 0) {
    return {
      state: MissingDataStates.COMPLETE_WITH_CAUTION,
      message: 'Strategy complete but running with data quality warnings',
      qualityScore: qualityAssessment?.combined_score || 0,
      qualityLevel: qualityAssessment?.overall_quality_level || 'unknown'
    };
  }

  // Check for placeholder/generic values
  if (strategy.confidence === 'Low' && strategy.time_horizon === 'Unknown') {
    return {
      state: MissingDataStates.PARTIAL_SUCCESS,
      message: 'Trading strategy incomplete - some analysis data available'
    };
  }

  // Check if strategy has valid legs for execution
  if (!strategy.legs || strategy.legs.length === 0) {
    return {
      state: MissingDataStates.PARTIAL_SUCCESS,
      message: 'Strategy concept available but not executable'
    };
  }

  return { state: MissingDataStates.COMPLETE, message: 'Strategy complete' };
};

const detectGptVerdictState = (gptVerdict) => {
  if (!gptVerdict) {
    return { state: MissingDataStates.LOADING, message: 'Analysis processing...' };
  }

  // Check if we have analyst data but no execution recommendations
  const hasAnalystData = gptVerdict.rationale || gptVerdict.summary_html || gptVerdict.final_bias;
  const hasExecutionRecs = gptVerdict.execution_recommendations?.primary_strategy?.type !== 'GPT Response Missing';

  if (hasAnalystData && !hasExecutionRecs) {
    return {
      state: MissingDataStates.PARTIAL_SUCCESS,
      message: 'Market analysis complete, trading strategies processing...',
      availableData: {
        rationale: !!gptVerdict.rationale,
        summary: !!gptVerdict.summary_html,
        bias: !!gptVerdict.final_bias,
        keyPoints: !!(gptVerdict.key_reasoning_points?.length),
        riskFactors: !!(gptVerdict.risk_factors?.length)
      }
    };
  }

  if (hasAnalystData && hasExecutionRecs) {
    return { state: MissingDataStates.COMPLETE, message: 'Analysis complete' };
  }

  return {
    state: MissingDataStates.PROCESSING,
    message: 'Analyzing market data and generating insights...'
  };
};

const isPlaceholderValue = (value, field) => {
  const placeholderValues = {
    allocation: ['Conservative allocation', 'No GPT guidance provided'],
    justification: ['No GPT guidance provided'],
    guidance: ['Use standard risk management', 'Use standard profit targets']
  };

  return placeholderValues[field]?.includes(value) || false;
};

// Skeleton Loader Components
const StrategySkeleton = () => (
  <Card variant="outlined" sx={{ mb: 2 }}>
    <CardContent>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Box sx={{ width: '60%', height: 24, bgcolor: 'grey.300', borderRadius: 1, animation: 'pulse 1.5s ease-in-out infinite' }} />
        <Box sx={{ width: 100, height: 24, bgcolor: 'grey.300', borderRadius: 12 }} />
      </Box>

      <Typography variant="subtitle2" gutterBottom>Strategy Legs:</Typography>
      <Paper sx={{ p: 1, mb: 2, bgcolor: '#f5f5f5' }}>
        {[1, 2].map((i) => (
          <Box key={i} sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
            <Box sx={{ width: '80%', height: 16, bgcolor: 'grey.300', borderRadius: 1 }} />
          </Box>
        ))}
      </Paper>

      <Box sx={{ width: '100%', height: 36, bgcolor: 'grey.300', borderRadius: 1 }} />
    </CardContent>
  </Card>
);

const GptInsightsSkeleton = () => (
  <Paper variant="outlined" sx={{ mb: 3, p: 2, bgcolor: '#f8f9fa' }}>
    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <HourglassEmptyIcon color="primary" sx={{ animation: 'pulse 1.5s ease-in-out infinite' }} />
        <Typography variant="h6">AI Trading Insights Processing...</Typography>
      </Box>
    </Box>

    <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
      <Typography variant="subtitle2" sx={{ mr: 1 }}>Market Bias:</Typography>
      <Box sx={{ width: 80, height: 24, bgcolor: 'grey.300', borderRadius: 12 }} />
    </Box>

    <Box sx={{ mt: 2 }}>
      <Paper elevation={0} sx={{ p: 2, mb: 2, bgcolor: '#f0f7ff', borderLeft: '4px solid #1976d2' }}>
        <Box sx={{ width: '40%', height: 20, bgcolor: 'grey.300', borderRadius: 1, mb: 1 }} />
        <Box sx={{ width: '100%', height: 16, bgcolor: 'grey.300', borderRadius: 1, mb: 1 }} />
        <Box sx={{ width: '80%', height: 16, bgcolor: 'grey.300', borderRadius: 1 }} />
      </Paper>

      <Paper variant="outlined" sx={{ p: 2, mb: 2, bgcolor: '#f8f9ff' }}>
        <Box sx={{ width: '30%', height: 16, bgcolor: 'grey.300', borderRadius: 1, mb: 1 }} />
        <Grid container spacing={2}>
          <Grid item xs={6}>
            <Box sx={{ width: '100%', height: 14, bgcolor: 'grey.300', borderRadius: 1, mb: 1 }} />
            <Box sx={{ width: '80%', height: 16, bgcolor: 'grey.300', borderRadius: 1 }} />
          </Grid>
          <Grid item xs={6}>
            <Box sx={{ width: '100%', height: 14, bgcolor: 'grey.300', borderRadius: 1, mb: 1 }} />
            <Box sx={{ width: 60, height: 24, bgcolor: 'grey.300', borderRadius: 12 }} />
          </Grid>
        </Grid>
      </Paper>
    </Box>
  </Paper>
);

// A custom hook to keep state in localStorage
function useStickyState(defaultValue, key) {
  const [value, setValue] = useState(() => {
    const stickyValue = window.localStorage.getItem(key);
    if (stickyValue !== null) {
      try {
        return JSON.parse(stickyValue);
      } catch (error) {
        console.error(`Error reading localStorage key “${key}”:`, error);
        return defaultValue;
      }
    }
    return defaultValue;
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch (error) {
      console.error(`Error setting localStorage key “${key}”:`, error);
    }
  }, [key, value]);

  return [value, setValue];
}

const RISK_FREE_DECIMAL_PLACES = 4;

/** Rounds to 4 decimal places so the rate field does not show float noise from API/storage. */
function normalizeRiskFreeRate(value, fallback = 0.045) {
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n)) return fallback;
  const f = 10 ** RISK_FREE_DECIMAL_PLACES;
  return Math.round(n * f) / f;
}

// --- Helper Components for Display ---

const AnalysisCard = ({ title, children, action }) => (
  <Card sx={{ mb: 3, boxShadow: 3 }}>
    <CardHeader 
      title={title} 
      action={action}
      titleTypographyProps={{ variant: 'h6', fontWeight: 'bold' }}
      sx={{ borderBottom: '1px solid #eee', pb: 1 }}
    />
    <CardContent>
      {children}
    </CardContent>
  </Card>
);

const CandlestickChart = ({ plotData, ticker }) => {
  if (!plotData || !plotData.data || !plotData.columns || !plotData.index) {
    return <Typography color="text.secondary">Chart data is not available.</Typography>;
  }

  const { index: dates, columns, data } = plotData;

  // Ensure data and columns are arrays
  if (!Array.isArray(data) || !Array.isArray(columns) || !Array.isArray(dates)) {
    return <Typography color="text.secondary">Invalid chart data format.</Typography>;
  }

  const findCol = (name) => columns.indexOf(name);

  const traces = [];

  // Candlestick base - check for required columns
  const closeIdx = findCol('Close');
  const highIdx = findCol('High');
  const lowIdx = findCol('Low');
  const openIdx = findCol('Open');

  if (closeIdx === -1 || highIdx === -1 || lowIdx === -1 || openIdx === -1) {
    return <Typography color="text.secondary">Required OHLC columns not found in chart data.</Typography>;
  }

  traces.push({
    x: dates,
    close: data.map(row => Array.isArray(row) && row.length > closeIdx ? row[closeIdx] : undefined),
    high: data.map(row => Array.isArray(row) && row.length > highIdx ? row[highIdx] : undefined),
    low: data.map(row => Array.isArray(row) && row.length > lowIdx ? row[lowIdx] : undefined),
    open: data.map(row => Array.isArray(row) && row.length > openIdx ? row[openIdx] : undefined),
    type: 'candlestick',
    name: ticker,
  });

  // Overlay SMA50 and SMA200 if available
  const sma10Idx = findCol('SMA10');
  if (sma10Idx !== -1) {
    traces.push({
      x: dates,
      y: data.map(row => Array.isArray(row) && row.length > sma10Idx ? row[sma10Idx] : undefined),
      type: 'scatter',
      mode: 'lines',
      name: 'SMA 10',
      line: { color: '#8c564b', width: 1.2 },
    });
  }

  const sma20Idx = findCol('SMA20');
  if (sma20Idx !== -1) {
    traces.push({
      x: dates,
      y: data.map(row => Array.isArray(row) && row.length > sma20Idx ? row[sma20Idx] : undefined),
      type: 'scatter',
      mode: 'lines',
      name: 'SMA 20',
      line: { color: '#2ca02c', width: 1.2 },
    });
  }

  const sma50Idx = findCol('SMA50');
  if (sma50Idx !== -1) {
    traces.push({
      x: dates,
      y: data.map(row => Array.isArray(row) && row.length > sma50Idx ? row[sma50Idx] : undefined),
      type: 'scatter',
      mode: 'lines',
      name: 'SMA 50',
      line: { color: '#1f77b4', width: 1.5 },
    });
  }

  const sma100Idx = findCol('SMA100');
  if (sma100Idx !== -1) {
    traces.push({
      x: dates,
      y: data.map(row => Array.isArray(row) && row.length > sma100Idx ? row[sma100Idx] : undefined),
      type: 'scatter',
      mode: 'lines',
      name: 'SMA 100',
      line: { color: '#9467bd', width: 1.3 },
    });
  }

  const sma200Idx = findCol('SMA200');
  if (sma200Idx !== -1) {
    traces.push({
      x: dates,
      y: data.map(row => Array.isArray(row) && row.length > sma200Idx ? row[sma200Idx] : undefined),
      type: 'scatter',
      mode: 'lines',
      name: 'SMA 200',
      line: { color: '#d62728', width: 1.5 },
    });
  }

  // Add Volume trace
  const volumeIdx = findCol('Volume');
  if (volumeIdx !== -1 && closeIdx !== -1) {
    traces.push({
      x: dates,
      y: data.map(row => Array.isArray(row) && row.length > volumeIdx ? row[volumeIdx] : undefined),
      type: 'bar',
      name: 'Volume',
      yaxis: 'y2',
      marker: {
        color: data.map((row, i) => {
          if (i > 0 && Array.isArray(row) && Array.isArray(data[i - 1]) &&
              row.length > closeIdx && data[i - 1].length > closeIdx) {
            return row[closeIdx] >= data[i - 1][closeIdx] ? 'rgba(44, 160, 44, 0.7)' : 'rgba(214, 39, 40, 0.7)';
          }
          return 'rgba(156, 156, 156, 0.7)';
        }),
      },
    });
  }

  const layout = {
    title: `${ticker} Price Chart`,
    xaxis: {
      type: 'date',
      title: 'Date',
      tickformat: '%Y-%m-%d',
      rangeslider: { visible: false },
    },
    yaxis: { title: 'Price', domain: [0.3, 1] },
    yaxis2: { title: 'Volume', domain: [0, 0.25], showticklabels: true },
    margin: { t: 40, b: 40, l: 50, r: 50 },
    height: 420,
    legend: { orientation: 'h' },
    showlegend: false,
  };

  return <Plot data={traces} layout={layout} style={{ width: '100%' }} />;
};

const MacroInsights = ({ onRateCalculated }) => {
  const [futures, setFutures] = useState(null);
  const [loading, setLoading] = useState(true);
  
  const [rfTickers, setRfTickers] = useStickyState('SPY, QQQ, IWM', 'rfTickers');
  const [calculating, setCalculating] = useState(false);
  const [calcResult, setCalcResult] = useState(null);
  const [calcLogs, setCalcLogs] = useState([]);

  useEffect(() => {
    const fetchMacroData = async () => {
      try {
        const response = await axios.get('/api/macro-data');
        setFutures(response.data);
      } catch (error) {
        console.error("Failed to fetch macro data:", error);
      } finally {
        setLoading(false);
      }
    };
    fetchMacroData();
  }, []);

  const handleCalculateRate = async (e) => {
    e.preventDefault();
    setCalculating(true);
    setCalcResult(null);
    setCalcLogs([]);
    try {
      const response = await axios.post('/api/calculate-risk-free-rate', {
        tickers: rfTickers.split(',').map(t => t.trim().toUpperCase()),
      });
      setCalcResult(response.data.risk_free_rate);
      setCalcLogs(response.data.logs);
      if (response.data.risk_free_rate) {
        onRateCalculated(response.data.risk_free_rate);
      }
    } catch (error) {
      console.error("Failed to calculate risk-free rate:", error);
      setCalcLogs(['Calculation failed. See browser console for details.']);
    } finally {
      setCalculating(false);
    }
  };

  const renderFuturesTable = () => {
    if (loading) return <CircularProgress size={24} />;
    if (!futures || futures.error || Object.keys(futures).length === 0) return <Typography color="error">Could not load futures data.</Typography>;

    // Additional safety checks for table structure
    const firstKey = Object.keys(futures)[0];
    if (!firstKey || !futures[firstKey] || typeof futures[firstKey] !== 'object') {
      return <Typography color="error">Invalid futures data structure.</Typography>;
    }

    return (
      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
              {Object.keys(futures[firstKey]).map(header => <TableCell key={header} sx={{ fontWeight: 'bold' }}>{header}</TableCell>)}
            </TableRow>
          </TableHead>
          <TableBody>
            {Object.entries(futures).map(([ticker, data]) => (
              <TableRow key={ticker}>
                {Object.entries(data || {}).map(([key, value]) => (
                  <TableCell key={key} sx={{ color: key === 'Change' && (typeof value === 'string' && value.startsWith('+') ? 'success.main' : 'error.main') }}>
                    {value}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    );
  };

  return (
    <AnalysisCard title="Macro Economy Insights">
      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <Typography variant="subtitle1" gutterBottom>Market Futures (Finviz)</Typography>
          {renderFuturesTable()}
        </Grid>
        <Grid item xs={12} md={6}>
          <Typography variant="subtitle1" gutterBottom>Implied Risk-Free Rate Calculator</Typography>
          <Box component="form" onSubmit={handleCalculateRate} sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <TextField
              label="Tickers (comma-separated)"
              value={rfTickers}
              onChange={e => setRfTickers(e.target.value)}
              fullWidth
              size="small"
            />
            <Button 
              type="submit" 
              variant="contained" 
              disabled={calculating}
              startIcon={calculating ? <CircularProgress size={20} /> : <SmartToyIcon />}
            >
              {calculating ? 'Calculating...' : 'Calculate Implied Rate'}
            </Button>
          </Box>
          {calcResult !== null && (
            <Alert severity="success" sx={{ mt: 2 }}>
              Calculated Rate: <strong>{(calcResult * 100).toFixed(3)}%</strong>
            </Alert>
          )}
          {calcLogs.length > 0 && (
            <Paper variant="outlined" sx={{ mt: 2, p: 1, maxHeight: 150, overflowY: 'auto', bgcolor: '#f9f9f9' }}>
              <Typography variant="caption" fontWeight="bold">Calculation Log:</Typography>
              {calcLogs.map((log, i) => <Typography key={i} variant="caption" display="block" sx={{ fontFamily: 'monospace' }}>{log}</Typography>)}
            </Paper>
          )}
        </Grid>
      </Grid>
    </AnalysisCard>
  );
};

const StrategyOrder = ({ strategy, strategies = [], ticker, expirationDate, gptVerdict, analysisResult, setCautionModeActive, executeAnalysis, selectedExpiration, riskFreeRate, analysisMethod, selectedModel }) => {
    const [isOrdering, setIsOrdering] = useState({});
    const [orderStatus, setOrderStatus] = useState({});    
    const [showGptInsights, setShowGptInsights] = useState(false);
    const [showEntryTimingDetails, setShowEntryTimingDetails] = useState({});

    // Consolidate strategies for execution from either GPT verdict or standard analysis
    let allStrategies = [];
    if (gptVerdict?.execution_recommendations) {
        const { primary_strategy, alternative_strategies } = gptVerdict.execution_recommendations;
        if (primary_strategy) {
            allStrategies.push({ ...primary_strategy, is_primary: true });
        }
        if (alternative_strategies) {
            allStrategies.push(...alternative_strategies);
        }
    } else {
        // Fallback to non-GPT strategies if no executable GPT strategies are found
        allStrategies = strategies && strategies.length > 0 ? strategies : (strategy ? [strategy] : []);
    }

    const handleExecute = async (strategy, index) => {
        setIsOrdering(prev => ({ ...prev, [index]: true }));
        setOrderStatus(prev => ({ ...prev, [index]: null }));
        
        try {
            const payload = {
                ticker: ticker,
                expiration_date: expirationDate, // "YYYY-MM-DD"
                legs: strategy.legs,
                is_credit_spread: strategy.is_credit_spread,
                size: 1, // Default to 1 for now
                // Include GPT verdict insights for enhanced order context
                gpt_insights: gptVerdict ? {
                    final_bias: gptVerdict.final_bias,
                    actionable_ideas: gptVerdict.actionable_ideas || [],
                    risk_factors: gptVerdict.risk_factors || [],
                    rationale: gptVerdict.rationale || '',
                    sources: gptVerdict.sources || [],
                    execution_recommendations: {
                        ...(gptVerdict.execution_recommendations || {}),
                        selected_strategy: {
                            name: strategy.name || strategy.type,
                            confidence: strategy.confidence || 'Medium'
                        }
                    }
                } : null
            };
            
            const response = await axios.post('/api/orders/strategy', payload);
            setOrderStatus(prev => ({ ...prev, [index]: response.data }));
        } catch (err) {
            setOrderStatus(prev => ({ ...prev, [index]: { 
                status: 'error', 
                message: err.response?.data?.detail || 'Order failed.' 
            }}));
        } finally {
            setIsOrdering(prev => ({ ...prev, [index]: false }));
        }
    };

    if (allStrategies.length === 0) {
        // Show helpful message when no strategies are available
        const verdictState = detectGptVerdictState(gptVerdict);

        if (verdictState.state === MissingDataStates.LOADING || verdictState.state === MissingDataStates.PROCESSING) {
            return (
                <AnalysisCard title="Strategy Recommendations">
                    <GptInsightsSkeleton />
                    <StrategySkeleton />
                </AnalysisCard>
            );
        }

        return (
            <AnalysisCard title="Strategy Recommendations">
                <Alert severity="info" sx={{ mb: 2 }}>
                    <AlertTitle>No Executable Strategies Available</AlertTitle>
                    {gptVerdict ?
                        'The market analysis is available above, but no executable trading strategies were generated. This may be due to limited options data or market conditions.' :
                        'No strategies are currently available. Try running an analysis first.'
                    }
                </Alert>

                {gptVerdict && (
                    <Paper variant="outlined" sx={{ p: 2, bgcolor: '#f0f9ff' }}>
                        <Typography variant="subtitle2" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <InfoIcon fontSize="small" color="info" />
                            Available Market Insights
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                            Review the market analysis above for trading insights and consider manual strategy implementation based on the market bias and risk factors provided.
                        </Typography>
                    </Paper>
                )}
            </AnalysisCard>
        );
    }

    const renderStrategyCard = (strategy, index) => {
        const strategyState = detectStrategyState(strategy, gptVerdict, analysisResult, setCautionModeActive, executeAnalysis, ticker, selectedExpiration, riskFreeRate, analysisMethod, selectedModel);

        // Handle loading/missing strategy states
        if (strategyState.state === MissingDataStates.LOADING) {
            return <StrategySkeleton key={index} />;
        }

        // Handle error states with informative cards
        if ([MissingDataStates.GPT_RESPONSE_MISSING, MissingDataStates.TRADER_AGENT_FAILED,
             MissingDataStates.SYSTEM_ERROR, MissingDataStates.DATA_QUALITY_ERROR,
             MissingDataStates.DATA_QUALITY_CAUTION].includes(strategyState.state)) {

            const errorConfig = {
                [MissingDataStates.GPT_RESPONSE_MISSING]: {
                    icon: <InfoIcon color="info" />,
                    title: 'Trading Strategy Processing',
                    bgColor: '#e3f2fd',
                    borderColor: '#2196f3',
                    severity: 'info',
                    actions: ['View market analysis while strategies are generated', 'Check back in a few moments']
                },
                [MissingDataStates.TRADER_AGENT_FAILED]: {
                    icon: <ErrorIcon color="error" />,
                    title: 'Strategy Generation Failed',
                    bgColor: '#ffebee',
                    borderColor: '#f44336',
                    severity: 'error',
                    actions: ['Try refreshing the analysis', 'Consider manual strategy selection based on market bias']
                },
                [MissingDataStates.SYSTEM_ERROR]: {
                    icon: <BuildIcon color="warning" />,
                    title: 'System Processing Error',
                    bgColor: '#fff3e0',
                    borderColor: '#ff9800',
                    severity: 'warning',
                    actions: ['Retry the analysis', 'Contact support if the issue persists']
                },
                [MissingDataStates.DATA_QUALITY_ERROR]: {
                    icon: <WarningIcon color="warning" />,
                    title: 'Insufficient Data Quality',
                    bgColor: '#fff8e1',
                    borderColor: '#ffc107',
                    severity: 'warning',
                    actions: ['Try a different expiration date', 'Ensure the ticker has active options trading']
                },
                [MissingDataStates.DATA_QUALITY_CAUTION]: {
                    icon: <ShieldIcon color="warning" />,
                    title: 'Data Quality Assessment',
                    bgColor: '#fff8e1',
                    borderColor: '#ffc107',
                    severity: 'warning',
                    actions: ['Review quality details below', 'Consider proceeding with caution'],
                    useEnhancedDisplay: true  // Flag to use DataQualityCard
                }
            };

            const config = errorConfig[strategyState.state];

            // Use enhanced DataQualityCard for DATA_QUALITY_CAUTION states
            if (strategyState.state === MissingDataStates.DATA_QUALITY_CAUTION && strategyState.qualityAssessment) {
                const handleProceedWithCaution = () => {
                    // Set caution mode and re-run analysis
                    setCautionModeActive(true);
                    executeAnalysis({
                        ticker: ticker,
                        expiration: expirationDate,
                        riskFreeRate: riskFreeRate,
                        analysisMethod: analysisMethod,
                        gptModel: selectedModel,
                        cautionMode: true
                    });
                };

                return (
                    <DataQualityCard
                        key={index}
                        qualityData={strategyState.qualityAssessment}
                        onProceedWithCaution={handleProceedWithCaution}
                        allowCaution={strategyState.allowCaution}
                        showRetryOptions={true}
                    />
                );
            }

            // Standard error card for other states
            return (
                <Card key={index} variant="outlined" sx={{ mb: 2, bgcolor: config.bgColor, borderColor: config.borderColor }}>
                    <CardContent>
                        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                            {config.icon}
                            <Typography variant="h6" sx={{ ml: 1, fontWeight: 'medium' }}>
                                {config.title}
                            </Typography>
                        </Box>

                        <Typography variant="body2" color="text.secondary" paragraph>
                            {strategyState.message}
                        </Typography>

                        <Alert severity={config.severity} sx={{ mt: 2 }}>
                            <AlertTitle>What you can do:</AlertTitle>
                            <Box component="ul" sx={{ mt: 1, pl: 2, mb: 0 }}>
                                {config.actions.map((action, i) => (
                                    <li key={i}>
                                        <Typography variant="body2">{action}</Typography>
                                    </li>
                                ))}
                            </Box>
                        </Alert>

                        {/* Show available data if in PARTIAL_SUCCESS state */}
                        {strategyState.state === MissingDataStates.PARTIAL_SUCCESS && gptVerdict && (
                            <Paper variant="outlined" sx={{ mt: 2, p: 2, bgcolor: 'rgba(33, 150, 243, 0.08)' }}>
                                <Typography variant="subtitle2" sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                                    <InfoIcon fontSize="small" color="info" />
                                    Available Market Analysis
                                </Typography>

                                {gptVerdict.final_bias && (
                                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                                        <Typography variant="body2" sx={{ mr: 1 }}>Market Bias:</Typography>
                                        <Chip
                                            label={gptVerdict.final_bias}
                                            color={gptVerdict.final_bias?.includes('Bull') ? 'success' : gptVerdict.final_bias?.includes('Bear') ? 'error' : 'default'}
                                            size="small"
                                        />
                                    </Box>
                                )}

                                {gptVerdict.rationale && (
                                    <Typography variant="body2" color="text.secondary" sx={{
                                        maxHeight: 60,
                                        overflow: 'hidden',
                                        textOverflow: 'ellipsis',
                                        display: '-webkit-box',
                                        WebkitLineClamp: 3,
                                        WebkitBoxOrient: 'vertical'
                                    }}>
                                        {gptVerdict.rationale.substring(0, 200)}...
                                    </Typography>
                                )}
                            </Paper>
                        )}
                    </CardContent>
                </Card>
            );
        }

        // Handle partial success - strategy concept but not executable
        if (strategyState.state === MissingDataStates.PARTIAL_SUCCESS && (!strategy.legs || strategy.legs.length === 0)) {
            return (
                <Card key={index} variant="outlined" sx={{ mb: 2, bgcolor: '#fff3e0', borderColor: '#ff9800' }}>
                    <CardContent>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                            <Typography variant="h6">{strategy.name || strategy.type || 'Trading Strategy'}</Typography>
                            <Chip label="Concept Only" color="warning" size="small" variant="outlined" />
                        </Box>

                        {strategy.description && (
                            <Typography variant="body2" color="text.secondary" paragraph>
                                {strategy.description}
                            </Typography>
                        )}

                        <Alert severity="info" sx={{ mt: 2 }}>
                            <AlertTitle>Strategy Not Executable</AlertTitle>
                            This alternative strategy is for context only; the AI did not provide execution legs (strikes, actions) for one-click execution.
                            Use the primary strategy above to execute, or implement this idea manually from the description.
                        </Alert>
                    </CardContent>
                </Card>
            );
        }

        // Render normal strategy (COMPLETE state)
        const confidence = strategy.confidence || 'Medium';
        const confidenceColor = {
            'High': 'success',
            'Medium': 'warning',
            'Low': 'error'
        }[confidence] || 'default';

        const entryTiming = gptVerdict?.execution_recommendations?.entry_timing;
        const entrySeverity = entryTiming?.status === 'enter_now' ? 'success' : entryTiming?.status === 'wait' ? 'warning' : 'info';
        const entryLabel =
          entryTiming?.status === 'enter_now'
            ? 'Good time to enter'
            : entryTiming?.status === 'wait'
              ? 'Wait — entry conditions not met'
              : 'Review entry conditions manually';

        return (
            <Card key={index} variant="outlined" sx={{ mb: 2 }}>
                <CardContent>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                        <Typography variant="h6">{strategy.name || strategy.type}</Typography>
                        <Chip label={`${confidence} Confidence`} color={confidenceColor} size="small" variant="outlined" />
                    </Box>

                    {entryTiming && (
                        <Box sx={{ mb: 2 }}>
                            <Alert severity={entrySeverity} sx={{ mb: 1 }}>
                                <AlertTitle>{entryTiming.status === 'enter_now' ? 'Timing: Enter Now' : entryTiming.status === 'wait' ? 'Timing: Wait' : 'Timing: Review'}</AlertTitle>
                                {entryLabel}
                            </Alert>
                            {(Array.isArray(entryTiming.conditions) && entryTiming.conditions.length > 0) && (
                                <>
                                    <Button
                                        size="small"
                                        variant="text"
                                        onClick={() =>
                                            setShowEntryTimingDetails((prev) => ({ ...prev, [index]: !prev[index] }))
                                        }
                                        sx={{ mb: 1 }}
                                    >
                                        {showEntryTimingDetails[index] ? 'Hide' : 'Show'} entry condition details
                                    </Button>
                                    <Collapse in={!!showEntryTimingDetails[index]}>
                                        <List dense disablePadding>
                                            {entryTiming.conditions.map((c, i) => (
                                                <ListItem key={i} disablePadding sx={{ mb: 0.5 }}>
                                                    <ListItemText
                                                        primaryTypographyProps={{ variant: 'caption', fontWeight: 600 }}
                                                        primary={`${c.status === 'met' ? '✓' : c.status === 'unmet' ? '!' : '?'} ${c.text}`}
                                                        secondary={c.reason}
                                                    />
                                                </ListItem>
                                            ))}
                                        </List>
                                    </Collapse>
                                </>
                            )}
                        </Box>
                    )}

                    <Typography variant="subtitle2" gutterBottom>Strategy Legs:</Typography>
                    <List dense disablePadding sx={{ mb: 2, bgcolor: '#f5f5f5', borderRadius: 1 }}>
                        {Array.isArray(strategy.legs) ? strategy.legs.map((leg, i) => (
                            <ListItem key={i}>
                                <ListItemText
                                    primary={
                                        <Typography variant="body2">
                                            <strong>{leg.action}</strong> {leg.strike ? `$${leg.strike.toFixed(2)}` : ''} {leg.right}
                                        </Typography>
                                    }
                                />
                            </ListItem>
                        )) : (
                            <ListItem>
                                <ListItemText
                                    primary={
                                        <Typography variant="body2" color="text.secondary">
                                            Strategy details not available
                                        </Typography>
                                    }
                                />
                            </ListItem>
                        )}
                    </List>

                    {(strategy.profit_target || strategy.stop_loss) && (
                        <Grid container spacing={2} sx={{ mb: 2 }}>
                            {typeof strategy.profit_target === 'number' && (
                                <Grid item xs={6}>
                                    <Paper variant="outlined" sx={{ p: 1, bgcolor: '#f0fdf4', borderColor: '#bbf7d0' }}>
                                        <Typography variant="caption" color="success.main" fontWeight="bold">Profit Target</Typography>
                                        <Typography variant="body1" fontWeight="bold">${strategy.profit_target.toFixed(2)}</Typography>
                                    </Paper>
                                </Grid>
                            )}
                            {typeof strategy.stop_loss === 'number' && (
                                <Grid item xs={6}>
                                    <Paper variant="outlined" sx={{ p: 1, bgcolor: '#fef2f2', borderColor: '#fecaca' }}>
                                        <Typography variant="caption" color="error.main" fontWeight="bold">Stop Loss</Typography>
                                        <Typography variant="body1" fontWeight="bold">${strategy.stop_loss.toFixed(2)}</Typography>
                                    </Paper>
                                </Grid>
                            )}
                        </Grid>
                    )}

                    <Button
                        variant="contained"
                        color="success"
                        fullWidth
                        onClick={() => handleExecute(strategy, index)}
                        disabled={isOrdering[index]}
                        startIcon={isOrdering[index] ? <CircularProgress size={20} color="inherit" /> : <CheckCircleIcon />}
                    >
                        {isOrdering[index] ? 'Placing Order...' : `Execute ${strategy.name || strategy.type}`}
                    </Button>

                    {orderStatus[index] && (
                        <Alert severity={orderStatus[index].status === 'error' ? 'error' : 'success'} sx={{ mt: 2 }}>
                            <AlertTitle>{orderStatus[index].status === 'error' ? 'Error' : 'Success'}</AlertTitle>
                            {orderStatus[index].message}
                            {orderStatus[index].status === 'success' && orderStatus[index].order_status && (
                                <Typography variant="caption" display="block" sx={{ mt: 1 }}>
                                    Order Status: {orderStatus[index].order_status}
                                </Typography>
                            )}
                        </Alert>
                    )}
                </CardContent>
            </Card>
        );
    };

    return (
        <AnalysisCard title={allStrategies.length > 1 ? "Recommended Strategies" : "Execute Strategy"}>
            
            {/* Enhanced GPT Insights Section with Better Missing Data Handling */}
            {(() => {
                const verdictState = detectGptVerdictState(gptVerdict);

                // Show loading skeleton while processing
                if (verdictState.state === MissingDataStates.LOADING || verdictState.state === MissingDataStates.PROCESSING) {
                    return <GptInsightsSkeleton />;
                }

                // Show partial data when analysis is available but execution recommendations are missing
                if (verdictState.state === MissingDataStates.PARTIAL_SUCCESS) {
                    return (
                        <Paper variant="outlined" sx={{ mb: 3, p: 2, bgcolor: '#f8f9fa' }}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                    <SmartToyIcon color="primary" />
                                    <Typography variant="h6">Market Analysis Available</Typography>
                                </Box>
                                <Button
                                    size="small"
                                    variant="outlined"
                                    onClick={() => setShowGptInsights(!showGptInsights)}
                                    endIcon={showGptInsights ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                                >
                                    {showGptInsights ? 'Hide Details' : 'Show Details'}
                                </Button>
                            </Box>

                            <Alert severity="info" sx={{ mb: 2 }}>
                                <AlertTitle>Trading Strategies Processing</AlertTitle>
                                {verdictState.message} The market analysis below is complete and available for review.
                            </Alert>

                            {gptVerdict.final_bias && (
                                <Box sx={{ display: 'flex', alignItems: 'center', mb: showGptInsights ? 2 : 0 }}>
                                    <Typography variant="subtitle2" sx={{ mr: 1 }}>Market Bias:</Typography>
                                    <Chip
                                        label={gptVerdict.final_bias}
                                        color={gptVerdict.final_bias?.includes('Bull') ? 'success' : gptVerdict.final_bias?.includes('Bear') ? 'error' : 'default'}
                                        size="small"
                                    />
                                </Box>
                            )}

                            <Collapse in={showGptInsights}>
                                <Box sx={{ mt: 2 }}>
                                    {/* Show placeholder for strategy recommendations */}
                                    <Paper elevation={0} sx={{ p: 2, mb: 2, bgcolor: '#fff3e0', borderLeft: '4px solid #ff9800' }}>
                                        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                                            <HourglassEmptyIcon color="warning" sx={{ mr: 1 }} />
                                            <Typography variant="subtitle1" color="warning.main" fontWeight="bold">Strategy Recommendations</Typography>
                                        </Box>
                                        <Typography variant="body2" color="text.secondary">
                                            Trading strategies are being generated based on the market analysis. This may take a few moments.
                                        </Typography>
                                    </Paper>

                                    {/* Show available analysis data */}
                                    {gptVerdict.key_reasoning_points?.length > 0 && (
                                        <Paper variant="outlined" sx={{ p: 2, mb: 2, bgcolor: '#f0f9ff' }}>
                                            <Typography variant="subtitle2" color="info.main" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                                <LightbulbIcon fontSize="small" /> Key Analysis Points
                                            </Typography>
                                            <List dense disablePadding>
                                                {gptVerdict.key_reasoning_points.slice(0, 3).map((point, i) => (
                                                    <ListItem key={i} disablePadding sx={{ mb: 0.5 }}>
                                                        <ListItemText primary={point} primaryTypographyProps={{ variant: 'body2' }} />
                                                    </ListItem>
                                                ))}
                                            </List>
                                        </Paper>
                                    )}

                                    {gptVerdict.risk_factors?.length > 0 && (
                                        <Paper variant="outlined" sx={{ p: 2, mb: 2, bgcolor: '#fef2f2', borderColor: '#fecaca' }}>
                                            <Typography variant="subtitle2" color="error.main" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                                <WarningIcon fontSize="small" /> Risk Factors
                                            </Typography>
                                            <List dense disablePadding>
                                                {gptVerdict.risk_factors.slice(0, 3).map((risk, i) => (
                                                    <ListItem key={i} disablePadding sx={{ mb: 0.5 }}>
                                                        <ListItemText primary={risk} primaryTypographyProps={{ variant: 'body2' }} />
                                                    </ListItem>
                                                ))}
                                            </List>
                                        </Paper>
                                    )}
                                </Box>
                            </Collapse>
                        </Paper>
                    );
                }

                // Show complete data when available
                if (verdictState.state === MissingDataStates.COMPLETE && gptVerdict) {
                    return (
                        <Paper variant="outlined" sx={{ mb: 3, p: 2, bgcolor: '#f8f9fa' }}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                    <SmartToyIcon color="primary" />
                                    <Typography variant="h6">AI Trading Insights</Typography>
                                    <Chip label="Complete" color="success" size="small" variant="outlined" />
                                </Box>
                                <Button
                                    size="small"
                                    variant="outlined"
                                    onClick={() => setShowGptInsights(!showGptInsights)}
                                    endIcon={showGptInsights ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                                >
                                    {showGptInsights ? 'Hide Details' : 'Show Details'}
                                </Button>
                            </Box>

                            <Box sx={{ display: 'flex', alignItems: 'center', mb: showGptInsights ? 2 : 0 }}>
                                <Typography variant="subtitle2" sx={{ mr: 1 }}>Market Bias:</Typography>
                                <Chip
                                    label={gptVerdict.final_bias || 'Neutral'}
                                    color={gptVerdict.final_bias?.includes('Bull') ? 'success' : gptVerdict.final_bias?.includes('Bear') ? 'error' : 'default'}
                                    size="small"
                                />
                            </Box>

                            <Collapse in={showGptInsights}>
                                <Box sx={{ mt: 2 }}>
                                    {/* Strategy Recommendations with placeholder detection */}
                                    {(() => {
                                        const strategy = gptVerdict.execution_recommendations?.primary_strategy;
                                        const isPlaceholder = strategy?.type === 'GPT Response Missing';

                                        if (strategy && !isPlaceholder) {
                                            return (
                                                <Paper elevation={0} sx={{ p: 2, mb: 2, bgcolor: '#f0f7ff', borderLeft: '4px solid #1976d2' }}>
                                                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                                                        <CheckCircleIcon color="primary" sx={{ mr: 1 }} />
                                                        <Typography variant="subtitle1" color="primary.main" fontWeight="bold">
                                                            Recommended Strategy: {strategy.type}
                                                        </Typography>
                                                    </Box>
                                                    <Typography variant="body2" paragraph>
                                                        {strategy.description || 'No specific strategy description available.'}
                                                    </Typography>
                                                    <Stack direction="row" spacing={2}>
                                                        <Typography variant="caption">
                                                            <strong>Confidence:</strong> {strategy.confidence}
                                                        </Typography>
                                                        {strategy.time_horizon && strategy.time_horizon !== 'Unknown' && (
                                                            <Typography variant="caption">
                                                                <strong>Timeframe:</strong> {strategy.time_horizon}
                                                            </Typography>
                                                        )}
                                                    </Stack>
                                                </Paper>
                                            );
                                        }
                                        return null;
                                    })()}

                                    {/* Position Sizing with placeholder detection */}
                                    {(() => {
                                        const positioning = gptVerdict.execution_recommendations?.position_sizing;
                                        if (!positioning) return null;

                                        const isPlaceholderAllocation = isPlaceholderValue(positioning.suggested_allocation, 'allocation');
                                        const isPlaceholderJustification = isPlaceholderValue(positioning.justification, 'justification');

                                        return (
                                            <Paper variant="outlined" sx={{
                                                p: 2,
                                                mb: 2,
                                                bgcolor: isPlaceholderAllocation ? '#fff8e1' : '#f8f9ff',
                                                ...(isPlaceholderAllocation && { borderColor: '#ffc107' })
                                            }}>
                                                <Typography variant="subtitle2" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                                    <TrendingUpIcon fontSize="small" /> Position Sizing
                                                    {isPlaceholderAllocation && <Chip label="Generic" color="warning" size="small" variant="outlined" />}
                                                </Typography>
                                                <Grid container spacing={2}>
                                                    <Grid item xs={6}>
                                                        <Typography variant="caption" color="text.secondary">Suggested Allocation</Typography>
                                                        <Typography variant="body2" fontWeight="medium" sx={{
                                                            fontStyle: isPlaceholderAllocation ? 'italic' : 'normal',
                                                            color: isPlaceholderAllocation ? 'text.secondary' : 'text.primary'
                                                        }}>
                                                            {positioning.suggested_allocation}
                                                        </Typography>
                                                    </Grid>
                                                    <Grid item xs={6}>
                                                        <Typography variant="caption" color="text.secondary">Risk Level</Typography>
                                                        <Chip
                                                            label={positioning.risk_level}
                                                            size="small"
                                                            color={positioning.risk_level === 'Conservative' ? 'success' : 'warning'}
                                                            variant={isPlaceholderAllocation ? 'outlined' : 'filled'}
                                                        />
                                                    </Grid>
                                                    {positioning.justification && (
                                                        <Grid item xs={12}>
                                                            <Typography variant="caption" color="text.secondary">Rationale</Typography>
                                                            <Typography variant="body2" fontStyle="italic" sx={{
                                                                color: isPlaceholderJustification ? 'text.secondary' : 'text.primary'
                                                            }}>
                                                                "{positioning.justification}"
                                                            </Typography>
                                                        </Grid>
                                                    )}
                                                </Grid>
                                            </Paper>
                                        );
                                    })()}

                                    {/* Entry/Exit Conditions - show placeholders when empty */}
                                    <Grid container spacing={2} sx={{ mb: 2 }}>
                                        <Grid item xs={12} md={6}>
                                            {gptVerdict.execution_recommendations?.entry_conditions?.length > 0 ? (
                                                <Paper variant="outlined" sx={{ p: 2, height: '100%', bgcolor: '#f0fdf4', borderColor: '#bbf7d0' }}>
                                                    <Typography variant="subtitle2" color="success.dark" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                                        <TrendingUpIcon fontSize="small" /> Entry Conditions
                                                    </Typography>
                                                    <List dense disablePadding>
                                                        {gptVerdict.execution_recommendations.entry_conditions.slice(0, 3).map((condition, i) => (
                                                            <ListItem key={i} disablePadding sx={{ mb: 0.5 }}>
                                                                <ListItemText primary={condition} primaryTypographyProps={{ variant: 'caption', lineHeight: 1.4 }} />
                                                            </ListItem>
                                                        ))}
                                                    </List>
                                                </Paper>
                                            ) : (
                                                <Paper variant="outlined" sx={{ p: 2, height: '100%', bgcolor: '#f5f5f5', borderColor: '#e0e0e0' }}>
                                                    <Typography variant="subtitle2" color="text.secondary" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                                        <InfoIcon fontSize="small" /> Entry Conditions
                                                    </Typography>
                                                    <Typography variant="body2" color="text.secondary" fontStyle="italic">
                                                        No specific entry conditions provided. Use standard technical analysis.
                                                    </Typography>
                                                </Paper>
                                            )}
                                        </Grid>

                                        <Grid item xs={12} md={6}>
                                            {gptVerdict.execution_recommendations?.exit_conditions?.length > 0 ? (
                                                <Paper variant="outlined" sx={{ p: 2, height: '100%', bgcolor: '#fff7ed', borderColor: '#ffedd5' }}>
                                                    <Typography variant="subtitle2" color="warning.dark" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                                        <TrendingDownIcon fontSize="small" /> Exit Conditions
                                                    </Typography>
                                                    <List dense disablePadding>
                                                        {gptVerdict.execution_recommendations.exit_conditions.slice(0, 3).map((condition, i) => (
                                                            <ListItem key={i} disablePadding sx={{ mb: 0.5 }}>
                                                                <ListItemText primary={condition} primaryTypographyProps={{ variant: 'caption', lineHeight: 1.4 }} />
                                                            </ListItem>
                                                        ))}
                                                    </List>
                                                </Paper>
                                            ) : (
                                                <Paper variant="outlined" sx={{ p: 2, height: '100%', bgcolor: '#f5f5f5', borderColor: '#e0e0e0' }}>
                                                    <Typography variant="subtitle2" color="text.secondary" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                                        <InfoIcon fontSize="small" /> Exit Conditions
                                                    </Typography>
                                                    <Typography variant="body2" color="text.secondary" fontStyle="italic">
                                                        No specific exit conditions provided. Use standard profit targets and stop losses.
                                                    </Typography>
                                                </Paper>
                                            )}
                                        </Grid>
                                    </Grid>

                                    {/* Trading Ideas - show placeholder when empty */}
                                    {gptVerdict.actionable_ideas?.length > 0 ? (
                                        <Paper variant="outlined" sx={{ p: 2, mb: 2, bgcolor: '#f0f9ff' }}>
                                            <Typography variant="subtitle2" color="info.main" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                                <LightbulbIcon fontSize="small" /> Key Trading Ideas
                                            </Typography>
                                            <List dense disablePadding>
                                                {gptVerdict.actionable_ideas.slice(0, 3).map((idea, i) => (
                                                    <ListItem key={i} disablePadding sx={{ mb: 0.5 }}>
                                                        <ListItemText primary={idea} primaryTypographyProps={{ variant: 'body2' }} />
                                                    </ListItem>
                                                ))}
                                            </List>
                                        </Paper>
                                    ) : (
                                        <Paper variant="outlined" sx={{ p: 2, mb: 2, bgcolor: '#f5f5f5', borderColor: '#e0e0e0' }}>
                                            <Typography variant="subtitle2" color="text.secondary" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                                <LightbulbIcon fontSize="small" /> Trading Ideas
                                            </Typography>
                                            <Typography variant="body2" color="text.secondary" fontStyle="italic">
                                                No specific trading ideas provided. Consider the market bias and risk factors when planning trades.
                                            </Typography>
                                        </Paper>
                                    )}

                                    {/* Risk Factors - show placeholder when empty */}
                                    {gptVerdict.risk_factors?.length > 0 ? (
                                        <Paper variant="outlined" sx={{ p: 2, mb: 2, bgcolor: '#fef2f2', borderColor: '#fecaca' }}>
                                            <Typography variant="subtitle2" color="error.main" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                                <WarningIcon fontSize="small" /> Risk Factors
                                            </Typography>
                                            <List dense disablePadding>
                                                {gptVerdict.risk_factors.slice(0, 3).map((risk, i) => (
                                                    <ListItem key={i} disablePadding sx={{ mb: 0.5 }}>
                                                        <ListItemText primary={risk} primaryTypographyProps={{ variant: 'body2' }} />
                                                    </ListItem>
                                                ))}
                                            </List>
                                        </Paper>
                                    ) : (
                                        <Paper variant="outlined" sx={{ p: 2, mb: 2, bgcolor: '#f5f5f5', borderColor: '#e0e0e0' }}>
                                            <Typography variant="subtitle2" color="text.secondary" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                                <WarningIcon fontSize="small" /> Risk Factors
                                            </Typography>
                                            <Typography variant="body2" color="text.secondary" fontStyle="italic">
                                                No specific risk factors identified. Apply general market risk management principles.
                                            </Typography>
                                        </Paper>
                                    )}
                                </Box>
                            </Collapse>
                        </Paper>
                    );
                }

                return null;
            })()}
            
            {/* Strategy Cards */}
            <Box sx={{ mt: 2 }}>
                {allStrategies.map((strat, idx) => renderStrategyCard(strat, idx))}
            </Box>
        </AnalysisCard>
    );
};

const webResearchMarkdownSx = {
  fontSize: '0.875rem',
  lineHeight: 1.65,
  color: 'text.primary',
  '& > *:first-of-type': { mt: 0 },
  '& > *:last-child': { mb: 0 },
  '& p': { my: 1 },
  '& h1, & h2, & h3, & h4': {
    mt: 2,
    mb: 0.75,
    fontWeight: 600,
    lineHeight: 1.3,
    color: 'primary.dark',
  },
  '& h1': { fontSize: '1.05rem' },
  '& h2': { fontSize: '1rem' },
  '& h3, & h4': { fontSize: '0.95rem' },
  '& ul, & ol': { pl: 2.25, my: 1 },
  '& ul': { listStyleType: 'disc' },
  '& ol': { listStyleType: 'decimal' },
  '& li': { mb: 0.65, pl: 0.25 },
  '& li::marker': { color: 'primary.main' },
  '& li > p': { my: 0.25 },
  '& strong': { fontWeight: 600, color: 'text.primary' },
  '& em': { color: 'text.secondary' },
  '& a': { color: 'primary.main', textDecoration: 'none', '&:hover': { textDecoration: 'underline' } },
  '& blockquote': {
    borderLeft: '3px solid',
    borderColor: 'primary.light',
    pl: 2,
    ml: 0,
    my: 1.5,
    color: 'text.secondary',
    fontStyle: 'italic',
    bgcolor: 'action.hover',
    borderRadius: '0 4px 4px 0',
    py: 0.5,
  },
  '& code': {
    fontFamily: 'monospace',
    fontSize: '0.8rem',
    bgcolor: 'action.hover',
    px: 0.5,
    py: 0.25,
    borderRadius: 0.5,
  },
  '& hr': { my: 2, borderColor: 'divider' },
  '& table': { borderCollapse: 'collapse', width: '100%', my: 1.5, fontSize: '0.8rem' },
  '& th, & td': { border: '1px solid', borderColor: 'divider', px: 1, py: 0.75, textAlign: 'left' },
  '& th': { bgcolor: 'action.hover', fontWeight: 600 },
};

const formatWebResearchFetchedAt = (iso) => {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
  } catch {
    return null;
  }
};

const sourceLinkLabel = (url) => {
  try {
    const host = new URL(url).hostname.replace(/^www\./, '');
    const path = new URL(url).pathname;
    if (path && path !== '/' && path.length < 48) {
      return `${host}${path}`;
    }
    return host;
  } catch {
    return url;
  }
};

/** Strip Perplexity inline citation markers like [1] or [1][2] for cleaner reading. */
const stripInlineCitations = (line) =>
  line.replace(/\s*\[(\d+)\](?:\[(\d+)\])*/g, '').trim();

/** Normalize plain-text Perplexity output into markdown-friendly content. */
const normalizeWebResearchSummary = (text) => {
  if (!text || typeof text !== 'string') return '';
  let trimmed = text.trim();
  if (!trimmed) return '';

  if (!/^#|\*\*|\[.*\]\(http|^[-*]\s/m.test(trimmed)) {
    const rawLines = trimmed.split('\n').map((line) => line.trim()).filter(Boolean);
    const bulletLike = rawLines.filter((line) => /^[-•*]\s/.test(line) || /^\d+\.\s/.test(line));
    if (bulletLike.length >= Math.max(2, rawLines.length * 0.5)) {
      trimmed = rawLines
        .map((line) => {
          const cleaned = stripInlineCitations(line);
          if (/^[-•*]\s/.test(cleaned)) return `- ${cleaned.replace(/^[-•*]\s+/, '')}`;
          if (/^\d+\.\s/.test(cleaned)) return cleaned;
          return cleaned;
        })
        .join('\n');
    } else {
      trimmed = rawLines
        .map((line) => stripInlineCitations(line))
        .map((line, i, arr) => {
          if (/^[A-Z][A-Za-z0-9\s/&-]{2,48}:$/.test(line)) {
            return `### ${line.slice(0, -1)}`;
          }
          if (/^[A-Z][A-Za-z0-9\s/&-]{2,48}:\s/.test(line) && line.length < 72) {
            const colon = line.indexOf(':');
            return `**${line.slice(0, colon + 1)}**${line.slice(colon + 1)}`;
          }
          if (arr.length > 1 && line.length < 200) return `- ${line}`;
          return line;
        })
        .join('\n\n');
    }
  }

  return trimmed
    .split('\n')
    .map((line) => stripInlineCitations(line))
    .join('\n');
};

const webResearchMarkdownComponents = {
  h3: ({ children }) => (
    <Typography
      component="h3"
      variant="subtitle2"
      fontWeight={700}
      sx={{
        mt: 2,
        mb: 0.75,
        pb: 0.5,
        color: 'primary.dark',
        borderBottom: 1,
        borderColor: 'divider',
      }}
    >
      {children}
    </Typography>
  ),
  li: ({ children }) => (
    <Box component="li" sx={{ mb: 0.75, '& p': { display: 'inline', margin: 0 } }}>
      <Typography component="span" variant="body2" sx={{ lineHeight: 1.65 }}>
        {children}
      </Typography>
    </Box>
  ),
  p: ({ children }) => (
    <Typography component="p" variant="body2" sx={{ lineHeight: 1.65, my: 1 }}>
      {children}
    </Typography>
  ),
};

const WebResearchSummaryBlock = ({ webResearch, sources }) => {
  const [expanded, setExpanded] = useState(true);
  const summary = normalizeWebResearchSummary(webResearch?.summary || '');
  const linkList = (sources && sources.length > 0 ? sources : webResearch?.sources) || [];
  const fetchedLabel = formatWebResearchFetchedAt(webResearch?.fetched_at);

  if (!summary && linkList.length === 0) return null;

  return (
    <Box sx={{ mb: 3 }}>
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        spacing={1}
        sx={{ mb: 1 }}
      >
        <Stack direction="row" alignItems="center" spacing={1}>
          <SearchIcon color="primary" fontSize="small" />
          <Typography variant="subtitle1" fontWeight="bold">
            Web Research Summary
          </Typography>
          {linkList.length > 0 && (
            <Chip size="small" label={`${linkList.length} sources`} variant="outlined" sx={{ height: 22 }} />
          )}
        </Stack>
        <IconButton
          size="small"
          aria-label={expanded ? 'Collapse web research' : 'Expand web research'}
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
        </IconButton>
      </Stack>

      <Collapse in={expanded}>
        <Paper
          variant="outlined"
          sx={{
            overflow: 'hidden',
            borderColor: 'primary.light',
            bgcolor: 'background.paper',
          }}
        >
          <Box
            sx={{
              px: 2,
              py: 1.25,
              bgcolor: (theme) => theme.palette.mode === 'dark' ? 'action.hover' : 'primary.50',
              borderBottom: 1,
              borderColor: 'divider',
            }}
          >
            <Stack direction="row" flexWrap="wrap" gap={1} alignItems="center">
              <Chip
                size="small"
                icon={<SearchIcon sx={{ fontSize: '14px !important' }} />}
                label={webResearch?.provider === 'perplexity' ? 'Perplexity Sonar' : (webResearch?.provider || 'Web search')}
                color="primary"
                variant="outlined"
              />
              {webResearch?.model && (
                <Chip size="small" label={webResearch.model} variant="outlined" />
              )}
              {fetchedLabel && (
                <Typography variant="caption" color="text.secondary" sx={{ ml: { xs: 0, sm: 'auto' } }}>
                  Retrieved {fetchedLabel}
                </Typography>
              )}
            </Stack>
          </Box>

          {summary && (
            <Box sx={{ px: 2, py: 2, bgcolor: '#f8fafc' }}>
              <Box sx={webResearchMarkdownSx}>
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={webResearchMarkdownComponents}
                >
                  {summary}
                </ReactMarkdown>
              </Box>
            </Box>
          )}

          {linkList.length > 0 && (
            <>
              {summary && <Divider />}
              <Box sx={{ px: 2, py: 1.5, bgcolor: 'background.default' }}>
                <Typography variant="caption" color="text.secondary" fontWeight={700} sx={{ display: 'block', mb: 1.25, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                  Sources · {linkList.length}
                </Typography>
                <Stack spacing={0.75}>
                  {linkList.map((source, i) => (
                    <Tooltip key={`${source}-${i}`} title={source} placement="top-start" enterDelay={400}>
                      <Link
                        href={source}
                        target="_blank"
                        rel="noopener noreferrer"
                        underline="hover"
                        variant="body2"
                        sx={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 0.75,
                          color: 'primary.main',
                          fontWeight: 500,
                          maxWidth: '100%',
                        }}
                      >
                        <OpenInNewIcon sx={{ fontSize: 15, flexShrink: 0 }} />
                        <Box component="span" sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {sourceLinkLabel(source)}
                        </Box>
                      </Link>
                    </Tooltip>
                  ))}
                </Stack>
              </Box>
            </>
          )}
        </Paper>
      </Collapse>
    </Box>
  );
};

const GptVerdictCard = ({ verdict }) => {
  if (!verdict) return null;

  return (
    <AnalysisCard title="GPT-Powered Verdict & Rationale">
      <WebResearchSummaryBlock
        webResearch={verdict.web_research}
        sources={verdict.sources}
      />

      {verdict.key_reasoning_points && verdict.key_reasoning_points.length > 0 && (
        <Box sx={{ mb: 3 }}>
          <Typography variant="subtitle1" gutterBottom fontWeight="bold">Key Analysis Points</Typography>
          <Paper variant="outlined" sx={{ p: 2, bgcolor: '#f8f9fa' }}>
            <List dense disablePadding>
              {verdict.key_reasoning_points.map((point, i) => (
                <ListItem key={i} disablePadding sx={{ mb: 1 }}>
                  <ListItemText primary={point} primaryTypographyProps={{ variant: 'body2', fontWeight: 'medium' }} />
                </ListItem>
              ))}
            </List>
          </Paper>
        </Box>
      )}
      
      {verdict.rationale && (
        <Box sx={{ mb: 3 }}>
          <Typography variant="subtitle1" gutterBottom fontWeight="bold">Detailed Reasoning</Typography>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="body2" sx={{ lineHeight: 1.6 }}>
              {verdict.rationale}
            </Typography>
          </Paper>
        </Box>
      )}
      
      <Grid container spacing={3}>
        {verdict.actionable_ideas && verdict.actionable_ideas.length > 0 && (
          <Grid item xs={12} md={6}>
            <Typography variant="subtitle1" gutterBottom fontWeight="bold">Actionable Ideas</Typography>
            <List dense>
              {verdict.actionable_ideas.map((idea, i) => (
                <ListItem key={i} disablePadding sx={{ mb: 0.5 }}>
                  <ListItemText primary={`• ${idea}`} />
                </ListItem>
              ))}
            </List>
          </Grid>
        )}

        {verdict.risk_factors && verdict.risk_factors.length > 0 && (
          <Grid item xs={12} md={6}>
            <Typography variant="subtitle1" gutterBottom fontWeight="bold">Risk Factors</Typography>
            <List dense>
              {verdict.risk_factors.map((risk, i) => (
                <ListItem key={i} disablePadding sx={{ mb: 0.5 }}>
                  <ListItemText primary={`• ${risk}`} />
                </ListItem>
              ))}
            </List>
          </Grid>
        )}
      </Grid>
    </AnalysisCard>
  );
};

const AnalysisDetails = ({
  data,
  analysisResult,
  setCautionModeActive,
  executeAnalysis,
  selectedExpiration,
  riskFreeRate,
  analysisMethod,
  selectedModel
}) => {
  const finalBias = data.final_bias || '';
  const biasColor = finalBias.includes('Bullish') ? 'success.main' : finalBias.includes('Bearish') ? 'error.main' : 'warning.main';

  const isGptResult = !!data.gpt_verdict;
  const conclusionTitle = isGptResult
    ? `AI-Powered Conclusion & Strategy (DTE: ${data.dte} days)`
    : `Holistic Conclusion & Strategy (DTE: ${data.dte} days)`;

  const renderUOA = (uoaList, type) => {
    if (!uoaList || uoaList.length === 0) return null;
    return (
      <Box sx={{ mt: 2 }}>
        <Typography variant="subtitle2" gutterBottom>Unusual {type} Activity:</Typography>
        <List dense disablePadding>
          {uoaList.map((item, i) => (
            <ListItem key={i} disablePadding>
              <ListItemText 
                primary={`${item.Type || type} @ $${item.Strike.toFixed(2)}`}
                secondary={`Vol: ${item.Volume}, OI: ${item['Open Int.']}`}
              />
            </ListItem>
          ))}
        </List>
      </Box>
    );
  };

  return (
    <Box>
      <AnalysisCard title={conclusionTitle}>
        <Typography variant="h5" sx={{ color: biasColor, mb: 2, fontWeight: 'bold' }}>
          Final Bias: {finalBias}
        </Typography>
        <Box dangerouslySetInnerHTML={{ __html: data.final_conclusion_html }} sx={{ '& ul': { pl: 2 }, '& li': { mb: 0.5 } }} />
      </AnalysisCard>

      {data.gpt_verdict && <GptVerdictCard verdict={data.gpt_verdict} />}

      <AnalysisCard title="Price Chart (Candlesticks + MAs)">
        {data.candlestick_analysis?.plot_data ? 
          <CandlestickChart plotData={data.candlestick_analysis.plot_data} ticker={data.ticker} /> :
          <Typography color="text.secondary">{data.candlestick_analysis?.error || "No chart data."}</Typography>
        }
        <Grid container spacing={2} sx={{ mt: 2 }}>
          <Grid item xs={6} md={3}>
            <Typography variant="caption" display="block" color="text.secondary">Primary Trend</Typography>
            <Typography variant="body2" fontWeight="bold">{data.candlestick_analysis?.context?.primary_trend}</Typography>
          </Grid>
          <Grid item xs={6} md={3}>
            <Typography variant="caption" display="block" color="text.secondary">Secondary Trend</Typography>
            <Typography variant="body2" fontWeight="bold">{data.candlestick_analysis?.context?.secondary_trend}</Typography>
          </Grid>
          {data.candlestick_analysis?.volume_analysis?.summary && (
            <Grid item xs={12} md={6}>
              <Typography variant="caption" display="block" color="text.secondary">Volume</Typography>
              <Typography variant="body2">{data.candlestick_analysis.volume_analysis.summary}</Typography>
            </Grid>
          )}
        </Grid>
      </AnalysisCard>
      
      <StrategyOrder
        strategies={data.recommended_strategies || [data.recommended_strategy].filter(Boolean)}
        ticker={data.ticker}
        expirationDate={data.expiration_date}
        gptVerdict={data.gpt_verdict}
        analysisResult={analysisResult}
        setCautionModeActive={setCautionModeActive}
        executeAnalysis={executeAnalysis}
        selectedExpiration={selectedExpiration}
        riskFreeRate={riskFreeRate}
        analysisMethod={analysisMethod}
        selectedModel={selectedModel}
      />
      
      { !isGptResult &&
        <>
          <AnalysisCard title="1. Candlestick Patterns (Context)">
            {data.candlestick_analysis?.patterns && data.candlestick_analysis.patterns.length > 0 ? (
              <Box sx={{ mt: 1 }}>
                <Typography variant="subtitle2" gutterBottom>Recent Patterns Identified:</Typography>
                <List dense>
                  {data.candlestick_analysis.patterns.map((p, i) => (
                    <ListItem key={i}>
                      <ListItemText 
                        primary={`${p.name} (Strength: ${p.strength})`}
                        secondary={p.interpretation}
                      />
                    </ListItem>
                  ))}
                </List>
              </Box>
            ) : (
              <Typography variant="body2" sx={{ mt: 1 }}>No significant candlestick patterns identified in the last few periods.</Typography>
            )}
          </AnalysisCard>

          <AnalysisCard title="2. Sentiment Analysis (Volume & OI)">
            <Grid container spacing={2}>
              <Grid item xs={12} md={4}>
                <Typography variant="subtitle2">Put/Call Ratio (Volume)</Typography>
                <Typography variant="body1">{data.volume_oi_analysis?.pc_ratio?.toFixed(2) || 'N/A'}</Typography>
              </Grid>
              {data.volume_oi_analysis?.oi_put_wall && (
                <Grid item xs={12} md={4}>
                  <Typography variant="subtitle2">Put Wall (Support)</Typography>
                  <Typography variant="body1">${data.volume_oi_analysis.oi_put_wall.Strike.toFixed(2)} (OI: {data.volume_oi_analysis.oi_put_wall['Open Int.']})</Typography>
                </Grid>
              )}
              {data.volume_oi_analysis?.oi_call_wall && (
                <Grid item xs={12} md={4}>
                  <Typography variant="subtitle2">Call Wall (Resistance)</Typography>
                  <Typography variant="body1">${data.volume_oi_analysis.oi_call_wall.Strike.toFixed(2)} (OI: {data.volume_oi_analysis.oi_call_wall['Open Int.']})</Typography>
                </Grid>
              )}
            </Grid>
            {renderUOA(data.volume_oi_analysis?.uoa_calls, 'Call')}
            {renderUOA(data.volume_oi_analysis?.uoa_puts, 'Put')}
          </AnalysisCard>

          <AnalysisCard title="3. Volatility & Movement Analysis">
            <Typography variant="body1" gutterBottom><strong>Market-Implied Move:</strong> {data.movement_analysis?.expected_move_pct?.toFixed(2) || 'N/A'}%</Typography>
            {data.movement_analysis?.vol_compression_text && <Typography variant="body2" paragraph><strong>Volatility Compression:</strong> {data.movement_analysis.vol_compression_text}</Typography>}
            {data.movement_analysis?.earnings_note && <Typography variant="body2" paragraph><strong>Catalyst Event:</strong> {data.movement_analysis.earnings_note}</Typography>}
          </AnalysisCard>
          
          <AnalysisCard title="4. Quantitative Valuation (Undervalued Options)">
            {data.results_df && data.results_df.length > 0 ? (
              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ bgcolor: '#f5f5f5' }}>
                      <TableCell>Strike</TableCell>
                      <TableCell>Type</TableCell>
                      <TableCell>Market Price</TableCell>
                      <TableCell>Model Price</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {data.results_df.map((opt, i) => (
                      <TableRow key={i}>
                        <TableCell>${opt.Strike.toFixed(2)}</TableCell>
                        <TableCell>{opt.Type}</TableCell>
                        <TableCell>${opt['Market Price'].toFixed(2)}</TableCell>
                        <TableCell>${opt['Model Price'].toFixed(2)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            ) : <Typography variant="body2">No significantly undervalued options were found.</Typography>}
          </AnalysisCard>
        </>
      }
    </Box>
  );
};

const ResultsDisplay = ({ analysisResult, setCautionModeActive, executeAnalysis, selectedExpiration, riskFreeRate, analysisMethod, selectedModel }) => {
  if (!analysisResult || !Array.isArray(analysisResult) || analysisResult.length === 0) {
    return <Typography color="text.secondary">No analysis results to display.</Typography>;
  }
  
  const commonData = analysisResult[0]; // Use first result for common data like ticker and price

  return (
    <Box sx={{ mt: 4 }}>
      <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 2, mb: 2 }}>
        <Typography variant="h4" component="h2">Analysis for {commonData.ticker?.toUpperCase()}</Typography>
        <Typography variant="h6" color="text.secondary">
          Current Price: <strong>{typeof commonData.S_current === 'number' ? `$${commonData.S_current.toFixed(2)}` : 'N/A'}</strong>
        </Typography>
      </Box>

      {analysisResult.map((result, index) => (
        <Box key={index} sx={{ mt: index > 0 ? 4 : 0, pt: index > 0 ? 4 : 0, borderTop: index > 0 ? '1px solid #e0e0e0' : 'none' }}>
          <AnalysisDetails
            data={result}
            analysisResult={analysisResult}
            setCautionModeActive={setCautionModeActive}
            executeAnalysis={executeAnalysis}
            selectedExpiration={selectedExpiration}
            riskFreeRate={riskFreeRate}
            analysisMethod={analysisMethod}
            selectedModel={selectedModel}
          />
        </Box>
      ))}
    </Box>
  );
};

const SavedVerdictsControls = ({ ticker, currentResult, scrollAnchorRef }) => {
  const [saving, setSaving] = useState(false);
  const [saveLabel, setSaveLabel] = useState('');
  const [saveMsg, setSaveMsg] = useState('');

  const [listLoading, setListLoading] = useState(false);
  const [savedList, setSavedList] = useState([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [selectedId, setSelectedId] = useState('');
  const [selectedDoc, setSelectedDoc] = useState(null);

  // Use the provided ticker; currentResult is optional (used for manual save and compare)

  const loadList = async () => {
    if (!ticker) return;
    setListLoading(true);
    try {
      const resp = await axios.get(`/api/analysis/verdicts/${encodeURIComponent(ticker)}`, {
        params: { page, page_size: pageSize }
      });
      setSavedList(resp.data?.items || []);
      setTotal(resp.data?.total || 0);
      setHasMore(!!resp.data?.has_more);
    } catch (e) {
      console.error('Failed to load saved verdicts', e);
    } finally {
      setListLoading(false);
    }
  };

  useEffect(() => {
    setSavedList([]);
    setSelectedDoc(null);
    setSelectedId('');
    setPage(1);
    if (ticker) loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker]);

  // Reload history when page or pageSize changes
  useEffect(() => {
    if (ticker) loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize]);

  // After a new analysis result arrives, refresh to include autosaved entry
  useEffect(() => {
    if (!ticker || !currentResult) return;
    setPage(1);
    loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentResult]);

  const handleSave = async () => {
    if (!currentResult) {
      setSaveMsg('No current verdict to save.');
      return;
    }
    setSaving(true);
    setSaveMsg('');
    try {
      const resp = await axios.post('/api/analysis/verdicts', {
        verdict: currentResult,
        label: saveLabel || undefined,
      });
      setSaveMsg(`Saved (id: ${resp.data?.id || 'unknown'})`);
      setSaveLabel('');
      await loadList();
    } catch (e) {
      setSaveMsg(`Save failed: ${e.response?.data?.detail || e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleSelect = async (id) => {
    setSelectedId(id);
    if (!id) {
      setSelectedDoc(null);
      return;
    }
    try {
      const resp = await axios.get(`/api/analysis/verdicts/id/${encodeURIComponent(id)}`);
      setSelectedDoc(resp.data?.item || null);
    } catch (e) {
      console.error('Failed to fetch saved verdict', e);
      setSelectedDoc(null);
    }
  };

  const currentBias = currentResult?.final_bias || '';
  const previousBias = selectedDoc?.final_bias || '';
  const biasChanged = previousBias && currentBias && previousBias !== currentBias;

  return (
    <Box ref={scrollAnchorRef}>
    <AnalysisCard title="Verdict History">
      <Grid container spacing={3}>
        <Grid item xs={12} md={4}>
          <Typography variant="subtitle1" gutterBottom>Add Current Verdict to History</Typography>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <TextField
              label="Label (optional)"
              placeholder="e.g., Before Earnings"
              value={saveLabel}
              onChange={e => setSaveLabel(e.target.value)}
              fullWidth
              size="small"
            />
            <Button 
              variant="contained" 
              onClick={handleSave} 
              disabled={saving || !ticker || !currentResult}
            >
              {saving ? 'Saving...' : 'Add to History'}
            </Button>
            {saveMsg && <Typography variant="caption" color={saveMsg.includes('failed') ? 'error' : 'success.main'}>{saveMsg}</Typography>}
          </Box>
        </Grid>

        <Grid item xs={12} md={8}>
          <Typography variant="subtitle1" gutterBottom>History</Typography>
          {listLoading ? (
            <CircularProgress size={24} />
          ) : (
            <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 320 }}>
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell>Saved At</TableCell>
                    <TableCell>Ticker</TableCell>
                    <TableCell>Label</TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell>Bias</TableCell>
                    <TableCell>Expiration</TableCell>
                    <TableCell align="right">DTE</TableCell>
                    <TableCell align="right">Price</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {savedList && savedList.length > 0 ? (
                    savedList.map(item => {
                      const ts = item.created_at?.slice(0, 19).replace('T',' ');
                      const ov = item.overview || {};
                      const typeText = ov.method_label || ((item.analysis_method || '').includes('gpt')
                        ? (((item.analysis_method || '').includes('web') ? 'Web Verdict' : 'GPT Verdict'))
                        : 'Model Verdict');
                      const isSelected = selectedId === item.id;
                      return (
                        <TableRow
                          key={item.id}
                          onClick={() => handleSelect(item.id)}
                          sx={{ cursor: 'pointer', bgcolor: isSelected ? 'action.selected' : 'inherit', '&:hover': { bgcolor: 'action.hover' } }}
                        >
                          <TableCell>{ts}</TableCell>
                          <TableCell>{item.ticker || ov.ticker || ''}</TableCell>
                          <TableCell>{item.label || ''}</TableCell>
                          <TableCell>{typeText}</TableCell>
                          <TableCell>{item.final_bias || ov.final_bias || ''}</TableCell>
                          <TableCell>{item.expiration_date || ov.expiration_date || ''}</TableCell>
                          <TableCell align="right">{ov.dte ?? ''}</TableCell>
                          <TableCell align="right">{typeof ov.S_current === 'number' ? `$${ov.S_current.toFixed(2)}` : ''}</TableCell>
                        </TableRow>
                      );
                    })
                  ) : (
                    <TableRow>
                      <TableCell colSpan={8} align="center">No saved verdicts yet.</TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          )}

          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 2 }}>
            <Box>
              <Button size="small" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1} sx={{ mr: 1 }}>Prev</Button>
              <Button size="small" onClick={() => setPage(p => (hasMore ? p + 1 : p))} disabled={!hasMore}>Next</Button>
            </Box>
            <Typography variant="caption" color="text.secondary">
              Page {page} of {Math.max(1, Math.ceil((total||0) / pageSize))} • {total} total
            </Typography>
            <FormControl size="small" sx={{ minWidth: 80 }}>
              <Select value={pageSize} onChange={e => setPageSize(parseInt(e.target.value) || 10)} variant="standard">
                {[10, 25, 50, 100].map(sz => <MenuItem key={sz} value={sz}>{sz}</MenuItem>)}
              </Select>
            </FormControl>
          </Box>

          {selectedDoc && (
            <Paper variant="outlined" sx={{ mt: 2, p: 2, bgcolor: '#f9f9f9' }}>
              <Typography variant="subtitle2">Saved Bias: {previousBias || 'N/A'}</Typography>
              {selectedDoc?.label && (
                <Typography variant="subtitle2" color="primary">Label: {selectedDoc.label}</Typography>
              )}
              {biasChanged && (
                <Typography variant="subtitle2" color="error">Changed vs Current: {currentBias || 'N/A'}</Typography>
              )}
              <Box sx={{ mt: 1 }}>
                <Typography variant="subtitle2" gutterBottom>Saved Summary</Typography>
                <Box dangerouslySetInnerHTML={{ __html: selectedDoc?.data?.final_conclusion_html || '<p>No saved summary.</p>' }} />
              </Box>
            </Paper>
          )}
        </Grid>
      </Grid>
    </AnalysisCard>
    </Box>
  );
};

const MethodologyExplanation = ({ methodology }) => {
  if (methodology === 'gpt-5-web-verdict') {
    return (
      <AnalysisCard title="About: Web Verdict Analysis">
        <Typography paragraph>
          The <strong>Web Verdict</strong> methodology runs entirely on <strong>Perplexity Sonar</strong>: live web research, then the same two-stage Analyst + Trader pipeline used by GPT Verdict.
        </Typography>
        <Typography paragraph>
          Perplexity gathers recent news, earnings catalysts, analyst actions, and sector headlines, then synthesizes them with our quantitative sub-analyses (technicals, volatility, options positioning). Only <strong>PERPLEXITY_API_KEY</strong> is required—no Gemini key for this mode. Source URLs are listed when available.
        </Typography>
      </AnalysisCard>
    );
  }

  if (methodology === 'gpt-verdict') {
    return (
      <AnalysisCard title="About: GPT Verdict Analysis">
        <Typography paragraph>
          The <strong>GPT Verdict</strong> methodology leverages a powerful Large Language Model (LLM) to synthesize the output of all standard sub-analyses.
        </Typography>
        <Typography paragraph>
          Instead of relying on a rules-based scoring system, this approach provides the AI with the complete, structured data from the Trend, Sentiment, Volatility, and Quantitative analyses. The model then acts as an expert analyst, weighing the evidence, identifying nuanced connections, and generating a final verdict that includes a detailed rationale, actionable ideas, and key risk factors. This provides a qualitative, expert-level second opinion on the quantitative data.
        </Typography>
      </AnalysisCard>
    );
  }
  
  if (methodology === 'holistic-market-edge') {
    return (
      <AnalysisCard title="About: Holistic Market Edge Analysis">
        <Typography paragraph>
          The <strong>Holistic Market Edge</strong> methodology is a multi-faceted approach to stock and option analysis, designed to synthesize a wide range of market data into a single, actionable conclusion. It avoids relying on a single indicator and instead builds a &quot;weight of the evidence&quot; verdict.
        </Typography>
        <Typography variant="subtitle2" gutterBottom>How the Final Verdict is Generated:</Typography>
        <Typography paragraph>
          The final bias (e.g., Bullish, Bearish, Neutral) is determined by a scoring system that aggregates sentiment from several core analytical components:
        </Typography>
        <List dense>
          <ListItem>
            <ListItemText primary="Price Trend & Candlesticks" secondary="Establishes the market's primary and secondary trends using moving averages and identifies recent, psychologically significant candlestick patterns for short-term sentiment." />
          </ListItem>
          <ListItem>
            <ListItemText primary="Sentiment Analysis" secondary="Gauges market sentiment by analyzing put/call ratios, unusual options activity (UOA), and significant open interest levels (support/resistance walls)." />
          </ListItem>
          <ListItem>
            <ListItemText primary="Volatility Analysis" secondary="Compares implied volatility (IV) to historical volatility (HV) to determine if options are 'cheap' or 'expensive.' It also checks for volatility compression, which often precedes large price moves." />
          </ListItem>
          <ListItem>
            <ListItemText primary="Catalyst Events" secondary="Checks for upcoming earnings reports before the option's expiration date, as these are significant drivers of volatility and price movement." />
          </ListItem>
          <ListItem>
            <ListItemText primary="Quantitative Valuation" secondary="Uses a binomial pricing model to calculate a theoretical option price, which is then compared to the market price to find potentially undervalued opportunities." />
          </ListItem>
        </List>
        <Typography paragraph>
          Each component contributes a bullish, bearish, or neutral signal to the final score. A strong bias is formed only when the evidence from multiple, diverse components points in the same direction. This comprehensive approach aims to provide a robust and well-rounded trading edge.
        </Typography>
      </AnalysisCard>
    );
  }
  
  return null;
};

// Error Boundary Component
class AnalysisErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('Analysis page error:', error, errorInfo);
    this.setState({ error: error });
  }

  render() {
    if (this.state.hasError) {
      return (
        <Box sx={{ p: 3 }}>
          <Alert severity="error">
            <AlertTitle>Application Error</AlertTitle>
            <Typography>
              An unexpected error occurred. Please refresh the page and try again.
            </Typography>
            {this.state.error && (
              <Box sx={{ mt: 2, p: 2, bgcolor: 'rgba(0,0,0,0.05)', borderRadius: 1 }}>
                <Typography variant="body2" color="error" sx={{ fontFamily: 'monospace' }}>
                  {this.state.error.toString()}
                </Typography>
              </Box>
            )}
            <Button
              onClick={() => window.location.reload()}
              sx={{ mt: 2 }}
              variant="outlined"
            >
              Refresh Page
            </Button>
          </Alert>
        </Box>
      );
    }

    return this.props.children;
  }
}

const StockRankingsDisplay = ({ ticker, analysisResult }) => {
  const [rankings, setRankings] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!ticker || !analysisResult) {
      setRankings([]);
      return;
    }
    const fetchRankings = async () => {
      setLoading(true);
      try {
        const response = await axios.get(`/api/stock-selection/rankings/${encodeURIComponent(ticker)}`);
        if (response.data?.status === 'success') {
          setRankings(response.data.rankings || []);
        }
      } catch (err) {
        console.error('Failed to fetch stock rankings:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchRankings();
  }, [ticker, analysisResult]);

  if (!analysisResult) return null;
  if (loading) return <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', mb: 2 }}><CircularProgress size={16} /><Typography variant="caption">Checking selection rankings...</Typography></Box>;
  if (rankings.length === 0) return null;

  return (
    <Box sx={{ mb: 3 }}>
      <Typography variant="subtitle2" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <CheckCircleIcon fontSize="small" color="success" />
        Top Ranked Stock Selection
      </Typography>
      <Grid container spacing={2}>
        {rankings.map((r, i) => (
          <Grid item xs={12} sm={6} md={4} key={i}>
            <Paper variant="outlined" sx={{ p: 1.5, bgcolor: '#f0fdf4', borderColor: '#4caf50' }}>
              <Typography variant="caption" color="text.secondary" display="block">
                Strategy: <strong>{r.strategy_label}</strong> ({r.mode.replace('_', ' ')})
              </Typography>
              <Typography variant="body2" sx={{ mt: 0.5 }}>
                Global Rank: <strong>{r.global_rank}</strong>
              </Typography>
              <Typography variant="body2">
                Cluster Rank: <strong>{r.cluster_rank}</strong>
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                Score: {Number(r.selection_score).toFixed(3)} | {r.group_label || r.regime_bucket}
              </Typography>
            </Paper>
          </Grid>
        ))}
      </Grid>
    </Box>
  );
};

const AnalysisPage = () => {
  const [ticker, setTicker] = useStickyState('SPY', 'ticker');
  const [analysisMethod, setAnalysisMethod] = useStickyState('holistic-market-edge', 'analysisMethod');
  const [riskFreeRate, setRiskFreeRateStored] = useStickyState(0.045, 'riskFreeRate');

  useEffect(() => {
    setRiskFreeRateStored((prev) => normalizeRiskFreeRate(prev));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setRiskFreeRate = useCallback((next) => {
    setRiskFreeRateStored((prev) => {
      const candidate = typeof next === 'number' ? next : parseFloat(String(next), 10);
      if (!Number.isFinite(candidate)) return prev;
      return normalizeRiskFreeRate(candidate);
    });
  }, [setRiskFreeRateStored]);
  const [expirations, setExpirations] = useState([]);
  const [selectedExpiration, setSelectedExpiration] = useState('');
  const [fetchingExpirations, setFetchingExpirations] = useState(false);
  const [analysisResult, setAnalysisResult] = useStickyState(null, 'analysisResult');
  const [analysisStage, setAnalysisStage] = useState('idle'); // 'idle', 'data_collection', 'guardrail_pause', 'full_analysis'
  const [error, setError] = useState('');
  const [showMalformedJsonReturn, setShowMalformedJsonReturn] = useState(false);

  // NEW: Caution mode state management
  const [cautionModeActive, setCautionModeActive] = useState(false);
  const [qualityAssessment, setQualityAssessment] = useState(null);
  
  // GPT / Perplexity model selection state
  const [availableModels, setAvailableModels] = useState([]);
  const [selectedModel, setSelectedModel] = useStickyState('gemini-2.5-flash', 'selectedGptModel');
  const [fetchingModels, setFetchingModels] = useState(false);
  const [perplexityModels, setPerplexityModels] = useState([]);
  const [selectedPerplexityModel, setSelectedPerplexityModel] = useStickyState('sonar', 'selectedPerplexityModel');
  const [fetchingPerplexityModels, setFetchingPerplexityModels] = useState(false);
  const isWebVerdictMethod = analysisMethod === 'gpt-5-web-verdict';
  const verdictModel = isWebVerdictMethod ? selectedPerplexityModel : selectedModel;
  const HISTORY_PAGE_SIZE = 5;
  const HISTORY_SCOPE_ALL = 'all';
  const HISTORY_SCOPE_CURRENT = 'current';
  const [historyItems, setHistoryItems] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState('');
  const [historyScope, setHistoryScope] = useStickyState(HISTORY_SCOPE_ALL, 'analysisHistoryScope');
  const [historyPage, setHistoryPage] = useState(1);
  const [historyHasMore, setHistoryHasMore] = useState(false);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyReloadVersion, setHistoryReloadVersion] = useState(0);
  const verdictHistorySectionRef = useRef(null);

  const { startTask: runAnalysisTask, loading: asyncLoading, taskStatus, error: asyncError, result: asyncResult } = useTaskPolling();

  const normalizedTickerForHistory = (ticker || '').trim().toUpperCase();
  const hasHistoryTicker = normalizedTickerForHistory.length > 0;

  useEffect(() => {
    if (historyPage !== 1) {
      setHistoryPage(1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [normalizedTickerForHistory, historyScope]);

  const formatTimestamp = (isoString) => {
    if (!isoString) return '';
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleString();
  };

  const formatRiskFreeRate = (value) => {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? normalizeRiskFreeRate(numeric).toFixed(RISK_FREE_DECIMAL_PLACES) : '';
  };

  const formatExpiration = (value) => {
    if (!value) return '';
    if (/^\d{8}$/.test(value)) {
      const year = value.slice(0, 4);
      const month = value.slice(4, 6);
      const day = value.slice(6, 8);
      const date = new Date(`${year}-${month}-${day}T00:00:00Z`);
      if (!Number.isNaN(date.getTime())) {
        return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
      }
    }
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime())
      ? value
      : parsed.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  };

  const totalHistoryPages = historyTotal > 0
    ? Math.max(1, Math.ceil(historyTotal / HISTORY_PAGE_SIZE))
    : (historyItems.length > 0 ? historyPage : 1);
  const historyRangeStart = historyItems.length === 0 ? 0 : (historyPage - 1) * HISTORY_PAGE_SIZE + 1;
  const historyRangeEnd = historyItems.length === 0 ? 0 : historyRangeStart + historyItems.length - 1;

  const fetchHistory = useCallback(
    async (targetTicker, scopeOverride) => {
      const scope = scopeOverride || historyScope;
      const normalizedTicker = (targetTicker || ticker || '').trim().toUpperCase();

      if (scope === HISTORY_SCOPE_CURRENT && !normalizedTicker) {
        setHistoryItems([]);
        setHistoryHasMore(false);
        setHistoryTotal(0);
        setHistoryError('');
        setHistoryLoading(false);
        return;
      }

      setHistoryLoading(true);
      setHistoryError('');
      try {
        const params = { page: historyPage, page_size: HISTORY_PAGE_SIZE };
        if (scope === HISTORY_SCOPE_CURRENT) {
          params.ticker = normalizedTicker;
        }
        const response = await axios.get('/api/analysis/history', { params });
        const data = response.data || {};
        const items = Array.isArray(data.items) ? data.items : [];
        setHistoryItems(items);
        setHistoryHasMore(Boolean(data.has_more));
        const total = Number(data.total);
        setHistoryTotal(Number.isFinite(total) ? total : Math.max(0, (historyPage - 1) * HISTORY_PAGE_SIZE + items.length));
      } catch (err) {
        console.error('Failed to fetch analysis history:', err);
        setHistoryError('Unable to load analysis history.');
        setHistoryItems([]);
        setHistoryHasMore(false);
        setHistoryTotal(0);
      } finally {
        setHistoryLoading(false);
      }
    },
    [historyScope, ticker, historyPage]
  );

  const handleRemoveHistoryItem = async (entryId) => {
    if (!entryId) return;

    try {
      await axios.delete(`/api/analysis/history/id/${encodeURIComponent(entryId)}`);
      if (historyItems.length <= 1 && historyPage > 1) {
        setHistoryPage((prev) => Math.max(1, prev - 1));
      } else {
        setHistoryReloadVersion((prev) => prev + 1);
      }
    } catch (err) {
      console.error('Failed to delete history entry:', err);
    }
  };

  const handleClearHistory = async () => {
    if (historyScope !== HISTORY_SCOPE_CURRENT) {
      return;
    }
    const normalizedTicker = (ticker || '').trim().toUpperCase();
    if (!normalizedTicker) {
      setHistoryItems([]);
      return;
    }

    try {
      await axios.delete(`/api/analysis/history/${encodeURIComponent(normalizedTicker)}`);
      setHistoryPage(1);
      setHistoryReloadVersion((prev) => prev + 1);
    } catch (err) {
      console.error('Failed to clear history:', err);
    }
  };

  // Fetch available GPT models
  const fetchGptModels = async () => {
    setFetchingModels(true);
    try {
      const response = await axios.get('/api/gpt-models');
      if (response.data.status === 'success') {
        setAvailableModels(response.data.models);
        // Set default model if current selection is not available
        if (!response.data.models.some(model => model.id === selectedModel)) {
          setSelectedModel(response.data.default || 'gemini-2.5-flash');
        }
      }
    } catch (error) {
      console.error('Failed to fetch GPT models:', error);
      console.error('Error details:', error.response?.data || error.message);
      // Fallback to default models if API fails
      setAvailableModels([
        { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash (Fallback)' },
        { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro (Fallback)' }
      ]);
    } finally {
      setFetchingModels(false);
    }
  };

  const fetchPerplexityModels = async () => {
    setFetchingPerplexityModels(true);
    try {
      const response = await axios.get('/api/perplexity-models');
      if (response.data.status === 'success') {
        setPerplexityModels(response.data.models);
        if (!response.data.models.some((m) => m.id === selectedPerplexityModel)) {
          setSelectedPerplexityModel(response.data.default || 'sonar');
        }
      }
    } catch (error) {
      console.error('Failed to fetch Perplexity models:', error);
      setPerplexityModels([
        { id: 'sonar', name: 'Sonar (Fallback)' },
        { id: 'sonar-pro', name: 'Sonar Pro (Fallback)' },
      ]);
    } finally {
      setFetchingPerplexityModels(false);
    }
  };

  // Load models when analysis method is GPT-based
  useEffect(() => {
    if (analysisMethod === 'gpt-5-web-verdict' && perplexityModels.length === 0) {
      fetchPerplexityModels();
    } else if (
      analysisMethod.includes('gpt')
      && analysisMethod !== 'gpt-5-web-verdict'
      && availableModels.length === 0
    ) {
      fetchGptModels();
    }
  }, [analysisMethod]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory, historyReloadVersion]);

  const executeAnalysis = async ({ ticker: targetTicker, expiration: targetExpiration, riskFreeRate: targetRate, analysisMethod: targetMethod, gptModel: targetModel, cautionMode = false }) => {
    const normalizedTicker = (targetTicker || '').trim().toUpperCase();
    const normalizedExpiration = (targetExpiration || '').trim();

    if (!normalizedTicker) {
      setError('Please enter a ticker symbol.');
      return;
    }

    if (!normalizedExpiration) {
      setError('Please fetch and select an expiration date.');
      return;
    }

    if (typeof targetRate !== 'number' || isNaN(targetRate)) {
      setError('Invalid risk-free rate value.');
      return;
    }

    if (!targetMethod) {
      setError('Please select an analysis method.');
      return;
    }

    setTicker(normalizedTicker);
    setSelectedExpiration(normalizedExpiration);
    if (!cautionMode) {
      setQualityAssessment(null);
      setCautionModeActive(false);
    }
    setShowMalformedJsonReturn(false);
    setError('');

    const requestPayload = {
      ticker: normalizedTicker,
      expiration_date: normalizedExpiration,
      risk_free_rate: targetRate,
      analysis_method: targetMethod,
      gpt_model: targetModel,
      caution_mode: cautionMode,
    };

    // Run pre-check before async analysis when override is not enabled.
    if (!cautionMode) {
      try {
        const qualityCheckResponse = await axios.post('/api/analysis/data-quality-check', requestPayload);
        const nextAssessment = qualityCheckResponse.data?.quality_assessment;

        if (nextAssessment) {
          setQualityAssessment(nextAssessment);
          const qualityLevel = nextAssessment.overall_level || 'failed';
          const combinedScore = nextAssessment.combined_score || nextAssessment.quality_score || 0;
          const passThreshold = nextAssessment?.thresholds_used?.pass_threshold || 0.6;
          const qualityFailed = (
            combinedScore < passThreshold ||
            ['acceptable', 'poor', 'failed'].includes(qualityLevel)
          );

          if (qualityFailed) {
            setAnalysisStage('guardrail_pause');
            return;
          }
        }
      } catch (err) {
        console.warn('Data quality pre-check failed, blocking analysis by default:', err);
        setError('Data quality check failed. Please retry or use a different expiration date.');
        setAnalysisStage('guardrail_pause');
        return;
      }
    }

    setAnalysisStage('full_analysis');
    if (cautionMode) {
      setCautionModeActive(true);
    }

    // Call the async analysis hook
    runAnalysisTask('/api/analysis/stock/async', {
      ...requestPayload,
    }, 'Analysis');
  };

  useEffect(() => {
    if (asyncResult) {
      if (isMalformedAiJsonResponse(asyncResult)) {
        setAnalysisResult(null);
        setQualityAssessment(null);
        setAnalysisStage('idle');
        setShowMalformedJsonReturn(true);
        setError('Note: AI response could not be parsed as JSON.');
        return;
      }

      const firstItem = Array.isArray(asyncResult) ? asyncResult[0] : asyncResult;
      if (firstItem?.analysis_blocked) {
        setQualityAssessment(firstItem.quality_assessment || null);
        setAnalysisResult(null);
        setShowMalformedJsonReturn(false);
        setAnalysisStage('guardrail_pause');
        setError(firstItem.message || 'Analysis blocked due to data quality.');
        return;
      }

      setAnalysisResult(asyncResult);
      setShowMalformedJsonReturn(false);
      setQualityAssessment(extractQualityAssessmentFromResult(asyncResult));
      setHistoryReloadVersion(v => v + 1);
    }
  }, [asyncResult, setAnalysisResult]);

  useEffect(() => {
    if (asyncError) {
      setShowMalformedJsonReturn(false);
      setError(asyncError);
      setQualityAssessment(null);
    }
  }, [asyncError]);

  useEffect(() => {
    if (!asyncLoading) {
      setAnalysisStage((prev) => (prev === 'guardrail_pause' ? prev : 'idle'));
      return;
    }
    setAnalysisStage(resolveAnalysisStage(taskStatus?.progress));
  }, [asyncLoading, taskStatus]);

  const handleFetchExpirations = async () => {
    try {
      if (!ticker) {
        setError('Please enter a ticker symbol first.');
        return;
      }
      setFetchingExpirations(true);
      setExpirations([]);
      setSelectedExpiration('');
      setAnalysisResult(null);
      setError('');

      // This endpoint needs to be created in the backend.
      const response = await axios.get(`/api/analysis/expirations/${encodeURIComponent(ticker)}`);
      if (response.data && response.data.length > 0) {
        setExpirations(response.data);
        setSelectedExpiration(response.data[0]); // Default to the first expiration
      } else {
        setError('No option expirations found for this ticker.');
      }
    } catch (err) {
      console.error('Error in handleFetchExpirations:', err);
      setError(err.response?.data?.detail || 'Failed to fetch expirations.');
    } finally {
      setFetchingExpirations(false);
    }
  };

  const handleAnalyze = async (e) => {
    try {
      e.preventDefault();
      await executeAnalysis({
        ticker,
        expiration: selectedExpiration,
        riskFreeRate,
        analysisMethod,
        gptModel: verdictModel,
      });
    } catch (error) {
      console.error('Error in handleAnalyze:', error);
      setError('An error occurred during analysis. Please try again.');
    }
  };

  const normalizeHistoryEntryTicker = (entry) => {
    if (!entry) return '';
    const payload = entry.request_payload || {};
    return (payload.ticker || entry.ticker || '').trim().toUpperCase();
  };

  const handlePortTickerToVerdictHistory = (entry) => {
    const normalizedTicker = normalizeHistoryEntryTicker(entry);
    if (!normalizedTicker) return;
    setTicker(normalizedTicker);
    verdictHistorySectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const handleHistoryAnalyze = async (entry) => {
    if (!entry) return;

    const normalizedTicker = normalizeHistoryEntryTicker(entry);
    if (!normalizedTicker) return;

    const payload = entry.request_payload || {};
    const rawExpiration = payload.expiration_date || entry.expiration_date_raw || entry.expiration_date || '';
    const nextMethod = payload.analysis_method || entry.analysis_method || analysisMethod;
    const nextRateCandidate = payload.risk_free_rate ?? entry.risk_free_rate ?? riskFreeRate;
    const nextRate = Number(nextRateCandidate);
    const needsGptModel = (nextMethod || '').includes('gpt');
    const isWebHistory = nextMethod === 'gpt-5-web-verdict';
    const nextModel = needsGptModel
      ? (payload.gpt_model || entry.gpt_model || (isWebHistory ? selectedPerplexityModel : selectedModel))
      : selectedModel;

    let normalizedExpiration = rawExpiration.trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(normalizedExpiration)) {
      normalizedExpiration = normalizedExpiration.replace(/-/g, '');
    }

    setTicker(normalizedTicker);
    setAnalysisMethod(nextMethod);
    setRiskFreeRate(Number.isNaN(nextRate) ? riskFreeRate : nextRate);
    setSelectedExpiration(normalizedExpiration);
    setExpirations((prev) => {
      if (!normalizedExpiration) return prev;
      return prev.includes(normalizedExpiration) ? prev : [normalizedExpiration, ...prev];
    });

    if (needsGptModel && nextModel) {
      if (isWebHistory) {
        setSelectedPerplexityModel(nextModel);
      } else {
        setSelectedModel(nextModel);
      }
    }

    await executeAnalysis({
      ticker: normalizedTicker,
      expiration: normalizedExpiration,
      riskFreeRate: Number.isNaN(nextRate) ? riskFreeRate : nextRate,
      analysisMethod: nextMethod,
      gptModel: nextModel,
    });
  };

  return (
    <Box>
      <MacroInsights onRateCalculated={setRiskFreeRate} />
      
      <MethodologyExplanation methodology={analysisMethod} />

      <AnalysisCard title="Stock and Option Analysis">
        <Box component="form" onSubmit={handleAnalyze} sx={{ mb: 3 }}>
          <Grid container spacing={2} alignItems="flex-end">
            <Grid item xs={12} sm={6} md={3}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <TextField
                  label="Ticker"
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value)}
                  required
                  fullWidth
                  size="small"
                />
                {ticker && (
                  <Tooltip title={`View ${ticker} on Finviz`}>
                    <IconButton 
                      size="small" 
                      component="a" 
                      href={`https://finviz.com/quote.ashx?t=${ticker}`} 
                      target="_blank" 
                      rel="noopener noreferrer"
                      sx={{ flexShrink: 0 }}
                    >
                      <OpenInNewIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                )}
              </Box>
            </Grid>

            <Grid item xs={12} sm={6} md={3}>
              <FormControl fullWidth size="small">
                <InputLabel>Analysis Methodology</InputLabel>
                <Select
                  value={analysisMethod}
                  label="Analysis Methodology"
                  onChange={e => setAnalysisMethod(e.target.value)}
                >
                  <MenuItem value="holistic-market-edge">Holistic Market Edge</MenuItem>
                  <MenuItem value="gpt-verdict">GPT Verdict</MenuItem>
                  <MenuItem value="gpt-5-web-verdict">Web Verdict</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            
            {/* Perplexity model selector for Web Verdict */}
            {isWebVerdictMethod && (
              <Grid item xs={12} sm={6} md={3}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Perplexity Model</InputLabel>
                    <Select
                      value={selectedPerplexityModel}
                      label="Perplexity Model"
                      onChange={(e) => setSelectedPerplexityModel(e.target.value)}
                      disabled={fetchingPerplexityModels}
                    >
                      {fetchingPerplexityModels ? (
                        <MenuItem disabled>Loading models...</MenuItem>
                      ) : Array.isArray(perplexityModels) && perplexityModels.length > 0 ? (
                        perplexityModels.map((model) => (
                          <MenuItem key={model.id} value={model.id}>
                            {model.name}
                          </MenuItem>
                        ))
                      ) : (
                        <MenuItem disabled>No models available</MenuItem>
                      )}
                    </Select>
                  </FormControl>
                  <Tooltip title="Refresh models list">
                    <IconButton onClick={fetchPerplexityModels} disabled={fetchingPerplexityModels} size="small">
                      <RefreshIcon />
                    </IconButton>
                  </Tooltip>
                </Box>
                {perplexityModels.some((m) => m.name.includes('Fallback')) && (
                  <Typography variant="caption" color="warning.main">
                    ⚠️ Using fallback models
                  </Typography>
                )}
              </Grid>
            )}

            {/* Gemini model selector for GPT Verdict only */}
            {analysisMethod === 'gpt-verdict' && (
              <Grid item xs={12} sm={6} md={3}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <FormControl fullWidth size="small">
                    <InputLabel>GPT Model</InputLabel>
                    <Select
                      value={selectedModel}
                      label="GPT Model"
                      onChange={e => setSelectedModel(e.target.value)}
                      disabled={fetchingModels}
                    >
                      {fetchingModels ? (
                        <MenuItem disabled>Loading models...</MenuItem>
                      ) : Array.isArray(availableModels) && availableModels.length > 0 ? (
                        availableModels.map(model => (
                          <MenuItem key={model.id} value={model.id}>
                            {model.name}
                          </MenuItem>
                        ))
                      ) : (
                        <MenuItem disabled>No models available</MenuItem>
                      )}
                    </Select>
                  </FormControl>
                  <Tooltip title="Refresh models list">
                    <IconButton onClick={fetchGptModels} disabled={fetchingModels} size="small">
                      <RefreshIcon />
                    </IconButton>
                  </Tooltip>
                </Box>
                {availableModels.some(m => m.name.includes('Fallback')) && (
                  <Typography variant="caption" color="warning.main">
                    ⚠️ Using fallback models
                  </Typography>
                )}
              </Grid>
            )}

            <Grid item xs={12} sm={6} md={2}>
              <Button 
                variant="outlined" 
                onClick={handleFetchExpirations} 
                disabled={fetchingExpirations || !ticker.trim()}
                fullWidth
                startIcon={fetchingExpirations ? <CircularProgress size={20} /> : <SearchIcon />}
              >
                1. Fetch Expirations
              </Button>
            </Grid>

            {Array.isArray(expirations) && expirations.length > 0 && (
              <Grid item xs={12} sm={6} md={2}>
                <FormControl fullWidth size="small">
                  <InputLabel>Expiration Date</InputLabel>
                  <Select
                    value={selectedExpiration}
                    label="Expiration Date"
                    onChange={e => setSelectedExpiration(e.target.value)}
                  >
                    {expirations.map(exp => (
                      <MenuItem key={exp} value={exp}>
                        {new Date(exp.replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3')).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' })}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
            )}

            <Grid item xs={6} md={2}>
              <TextField
                label="Risk-Free Rate"
                type="number"
                inputProps={{ step: 0.0001 }}
                value={riskFreeRate}
                onChange={(e) => setRiskFreeRate(parseFloat(e.target.value))}
                required
                fullWidth
                size="small"
              />
            </Grid>

            <Grid item xs={6} md={2}>
              <Button 
                type="submit" 
                variant="contained" 
                disabled={asyncLoading || !selectedExpiration}
                fullWidth
                startIcon={asyncLoading ? <CircularProgress size={20} color="inherit" /> : <SmartToyIcon />}
              >
                2. Run Analysis
              </Button>
            </Grid>
          </Grid>
        </Box>

        {error && (
          <Alert
            severity="error"
            sx={{ mb: 2 }}
            action={showMalformedJsonReturn ? (
              <Button
                color="inherit"
                size="small"
                onClick={() => {
                  setError('');
                  setShowMalformedJsonReturn(false);
                  setAnalysisStage('idle');
                }}
              >
                Return
              </Button>
            ) : null}
          >
            {error}
          </Alert>
        )}
        
        {analysisStage === 'guardrail_pause' && qualityAssessment && (
          <Box sx={{ mb: 3 }}>
            <Alert severity="warning" sx={{ mb: 2 }}>
              <AlertTitle>Data Quality Gate</AlertTitle>
              Data quality did not pass for <strong>{ticker}</strong> on <strong>{selectedExpiration}</strong>. Analysis is currently stopped.
            </Alert>
            <DataQualityCard qualityData={qualityAssessment} showRetryOptions={!asyncLoading} />
            <Box sx={{ display: 'flex', gap: 2, mt: 2 }}>
              <Button
                variant="contained"
                color="warning"
                disabled={asyncLoading}
                onClick={() => executeAnalysis({
                  ticker,
                  expiration: selectedExpiration,
                  riskFreeRate,
                  analysisMethod,
                  gptModel: verdictModel,
                  cautionMode: true
                })}
              >
                Override and Continue
              </Button>
              <Button
                variant="outlined"
                disabled={asyncLoading}
                onClick={() => {
                  setAnalysisStage('idle');
                  setCautionModeActive(false);
                }}
              >
                Cancel
              </Button>
            </Box>
          </Box>
        )}

        {/* Show quality assessment as soon as it's available, even during loading */}
        {qualityAssessment && analysisStage !== 'guardrail_pause' && (
          <Box sx={{ mb: 3 }}>
            <DataQualityCard qualityData={qualityAssessment} showRetryOptions={!asyncLoading} />
          </Box>
        )}

        {asyncLoading && (
          <Paper variant="outlined" sx={{ p: 3, mb: 3, textAlign: 'center' }}>
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
              <CircularProgress size={40} />
              <Typography variant="h6" color="primary">
                {taskStatus?.name || 'Analysis in Progress'}
              </Typography>
              <Typography variant="body1">
                {taskStatus?.message || 'Analysis is running...'}
              </Typography>

            </Box>
          </Paper>
        )}
        {analysisResult && (
          <>
            <StockRankingsDisplay ticker={ticker} analysisResult={analysisResult} />
            <ResultsDisplay
              analysisResult={analysisResult}
              setCautionModeActive={setCautionModeActive}
              executeAnalysis={executeAnalysis}
              selectedExpiration={selectedExpiration}
              riskFreeRate={riskFreeRate}
              analysisMethod={analysisMethod}
              selectedModel={verdictModel}
            />
          </>
        )}
      </AnalysisCard>

      <AnalysisCard title="Recent Analyses">
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <FormControl size="small" sx={{ minWidth: 150 }}>
              <InputLabel>Show</InputLabel>
              <Select
                value={historyScope}
                label="Show"
                onChange={e => {
                  const nextScope = e.target.value;
                  setHistoryScope(nextScope);
                  setHistoryPage(1);
                }}
              >
                <MenuItem value={HISTORY_SCOPE_ALL}>All tickers</MenuItem>
                <MenuItem value={HISTORY_SCOPE_CURRENT}>
                  {hasHistoryTicker ? `Current ticker (${normalizedTickerForHistory})` : 'Current ticker'}
                </MenuItem>
              </Select>
            </FormControl>
            {historyScope === HISTORY_SCOPE_CURRENT && (
              <Typography variant="caption" color={hasHistoryTicker ? 'text.secondary' : 'error'}>
                {hasHistoryTicker ? `Filtering on ${normalizedTickerForHistory}` : 'Enter a ticker above to filter by symbol.'}
              </Typography>
            )}
          </Box>
          {historyItems.length > 0 && historyScope === HISTORY_SCOPE_CURRENT && hasHistoryTicker && (
            <Button size="small" color="error" startIcon={<DeleteIcon />} onClick={handleClearHistory}>
              Clear History
            </Button>
          )}
        </Box>

        {historyLoading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', p: 2 }}><CircularProgress size={24} /></Box>
        ) : (
          <>
            {historyError && <Alert severity="error" sx={{ mb: 2 }}>{historyError}</Alert>}
            
            {historyItems.length === 0 ? (
              <Typography color="text.secondary" align="center" sx={{ py: 2 }}>
                {historyScope === HISTORY_SCOPE_CURRENT
                  ? (hasHistoryTicker ? 'No history found for this ticker yet.' : 'Enter a ticker to view its recent analyses.')
                  : 'Run an analysis to build your personal history.'}
              </Typography>
            ) : (
              <List>
                {historyItems.map((entry) => (
                  <Paper key={entry.id} variant="outlined" sx={{ mb: 1 }}>
                    <ListItem
                      onClick={() => handlePortTickerToVerdictHistory(entry)}
                      sx={{
                        cursor: 'pointer',
                        '&:hover': { bgcolor: 'action.hover' },
                      }}
                      secondaryAction={
                        <Box>
                          <Button
                            size="small"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleHistoryAnalyze(entry);
                            }}
                            sx={{ mr: 1 }}
                          >
                            Analyze Again
                          </Button>
                          <IconButton
                            edge="end"
                            size="small"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleRemoveHistoryItem(entry.id);
                            }}
                          >
                            <DeleteIcon fontSize="small" />
                          </IconButton>
                        </Box>
                      }
                    >
                      <ListItemText
                        primary={
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <Typography variant="subtitle2">{entry.ticker}</Typography>
                            {(entry.expiration_date || entry.expiration_date_raw) && (
                              <Typography variant="caption" color="text.secondary">
                                · Exp {formatExpiration(entry.expiration_date_raw || entry.expiration_date)}
                              </Typography>
                            )}
                          </Box>
                        }
                        secondary={
                          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', mt: 0.5 }}>
                            <Typography variant="caption">{entry.analysis_method}</Typography>
                            {entry.gpt_model && <Typography variant="caption">Model: {entry.gpt_model}</Typography>}
                            {formatRiskFreeRate(entry.risk_free_rate) && (
                              <Typography variant="caption">RF: {formatRiskFreeRate(entry.risk_free_rate)}</Typography>
                            )}
                            {formatTimestamp(entry.created_at) && (
                              <Typography variant="caption">{formatTimestamp(entry.created_at)}</Typography>
                            )}
                            {entry.final_bias && (
                              <Chip label={entry.final_bias} size="small" sx={{ height: 20, fontSize: '0.7rem' }} />
                            )}
                          </Box>
                        }
                      />
                    </ListItem>
                  </Paper>
                ))}
              </List>
            )}
            
            {historyItems.length > 0 && (
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 2 }}>
                <Typography variant="caption" color="text.secondary">
                  Showing {historyRangeStart}–{historyRangeEnd} of {historyTotal || historyRangeEnd}
                </Typography>
                <Box>
                  <Button size="small" onClick={() => setHistoryPage((prev) => Math.max(1, prev - 1))} disabled={historyPage === 1 || historyLoading} sx={{ mr: 1 }}>
                    Previous
                  </Button>
                  <Typography variant="caption" sx={{ mx: 1 }}>
                    Page {historyPage} of {totalHistoryPages}
                  </Typography>
                  <Button size="small" onClick={() => setHistoryPage((prev) => prev + 1)} disabled={!historyHasMore || historyLoading}>
                    Next
                  </Button>
                </Box>
              </Box>
            )}
          </>
        )}
      </AnalysisCard>

      {/* Verdict History is accessible without running a new analysis */}
      <SavedVerdictsControls
        ticker={ticker}
        currentResult={analysisResult && Array.isArray(analysisResult) ? analysisResult[0] : null}
        scrollAnchorRef={verdictHistorySectionRef}
      />
    </Box>
  );
}

// Wrapped component with error boundary
const AnalysisPageWithErrorBoundary = () => (
  <AnalysisErrorBoundary>
    <AnalysisPage />
  </AnalysisErrorBoundary>
);

export default AnalysisPageWithErrorBoundary;
