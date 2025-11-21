import React, { useState, useEffect, useCallback } from 'react';
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
  Tooltip
} from '@mui/material';
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
  History as HistoryIcon
} from '@mui/icons-material';

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
  if (!plotData || !plotData.data) {
    return <Typography color="text.secondary">Chart data is not available.</Typography>;
  }

  const { index: dates, columns, data } = plotData;
  const findCol = (name) => columns.indexOf(name);

  const traces = [];

  // Candlestick base
  traces.push({
    x: dates,
    close: data.map(row => row[findCol('Close')]),
    high: data.map(row => row[findCol('High')]),
    low: data.map(row => row[findCol('Low')]),
    open: data.map(row => row[findCol('Open')]),
    type: 'candlestick',
    name: ticker,
  });

  // Overlay SMA50 and SMA200 if available
  const sma10Idx = findCol('SMA10');
  if (sma10Idx !== -1) {
    traces.push({
      x: dates,
      y: data.map(row => row[sma10Idx]),
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
      y: data.map(row => row[sma20Idx]),
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
      y: data.map(row => row[sma50Idx]),
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
      y: data.map(row => row[sma100Idx]),
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
      y: data.map(row => row[sma200Idx]),
      type: 'scatter',
      mode: 'lines',
      name: 'SMA 200',
      line: { color: '#d62728', width: 1.5 },
    });
  }

  // Add Volume trace
  const volumeIdx = findCol('Volume');
  const closeIdx = findCol('Close');
  if (volumeIdx !== -1 && closeIdx !== -1) {
    traces.push({
      x: dates,
      y: data.map(row => row[volumeIdx]),
      type: 'bar',
      name: 'Volume',
      yaxis: 'y2',
      marker: {
        color: data.map((d, i) => {
          if (i > 0) {
            return data[i][closeIdx] >= data[i - 1][closeIdx] ? 'rgba(44, 160, 44, 0.7)' : 'rgba(214, 39, 40, 0.7)';
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

    return (
      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
              {Object.keys(futures[Object.keys(futures)[0]]).map(header => <TableCell key={header} sx={{ fontWeight: 'bold' }}>{header}</TableCell>)}
            </TableRow>
          </TableHead>
          <TableBody>
            {Object.entries(futures).map(([ticker, data]) => (
              <TableRow key={ticker}>
                {Object.entries(data).map(([key, value]) => (
                  <TableCell key={key} sx={{ color: key === 'Change' && (value.startsWith('+') ? 'success.main' : 'error.main') }}>
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

const StrategyOrder = ({ strategy, strategies = [], ticker, expirationDate, gptVerdict }) => {
    const [isOrdering, setIsOrdering] = useState({});
    const [orderStatus, setOrderStatus] = useState({});    
    const [showGptInsights, setShowGptInsights] = useState(false);

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
                            name: strategy.name,
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
        return null;
    }

    const renderStrategyCard = (strategy, index) => {
        if (!strategy || !strategy.name || strategy.name === 'None' || !strategy.legs || strategy.legs.length === 0) {
            return null;
        }

        const confidence = strategy.confidence || 'Medium';
        const confidenceColor = {
            'High': 'success',
            'Medium': 'warning',
            'Low': 'error'
        }[confidence] || 'default';

        return (
            <Card key={index} variant="outlined" sx={{ mb: 2 }}>
                <CardContent>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                        <Typography variant="h6">{strategy.name}</Typography>
                        <Chip label={`${confidence} Confidence`} color={confidenceColor} size="small" variant="outlined" />
                    </Box>
                    
                    <Typography variant="subtitle2" gutterBottom>Strategy Legs:</Typography>
                    <List dense disablePadding sx={{ mb: 2, bgcolor: '#f5f5f5', borderRadius: 1 }}>
                        {strategy.legs.map((leg, i) => (
                            <ListItem key={i}>
                                <ListItemText 
                                    primary={
                                        <Typography variant="body2">
                                            <strong>{leg.action}</strong> {leg.strike ? `$${leg.strike.toFixed(2)}` : ''} {leg.right}
                                        </Typography>
                                    } 
                                />
                            </ListItem>
                        ))}
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
                        {isOrdering[index] ? 'Placing Order...' : `Execute ${strategy.name}`}
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
            
            {/* GPT Insights Section */}
            {gptVerdict && (
                <Paper variant="outlined" sx={{ mb: 3, p: 2, bgcolor: '#f8f9fa' }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <SmartToyIcon color="primary" />
                            <Typography variant="h6">AI Trading Insights</Typography>
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
                            {gptVerdict.execution_recommendations?.primary_strategy && (
                                <Paper elevation={0} sx={{ p: 2, mb: 2, bgcolor: '#f0f7ff', borderLeft: '4px solid #1976d2' }}>
                                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                                        <CheckCircleIcon color="primary" sx={{ mr: 1 }} />
                                        <Typography variant="subtitle1" color="primary.main" fontWeight="bold">Recommended Strategy</Typography>
                                    </Box>
                                    <Typography variant="body2" paragraph>
                                        {gptVerdict.execution_recommendations.primary_strategy.description || 'No specific strategy description available.'}
                                    </Typography>
                                    <Stack direction="row" spacing={2}>
                                        <Typography variant="caption">
                                            <strong>Confidence:</strong> {gptVerdict.execution_recommendations.primary_strategy.confidence}
                                        </Typography>
                                        {gptVerdict.execution_recommendations.primary_strategy.time_horizon && (
                                            <Typography variant="caption">
                                                <strong>Timeframe:</strong> {gptVerdict.execution_recommendations.primary_strategy.time_horizon}
                                            </Typography>
                                        )}
                                    </Stack>
                                </Paper>
                            )}
                            
                            {gptVerdict.execution_recommendations?.position_sizing && (
                                <Paper variant="outlined" sx={{ p: 2, mb: 2, bgcolor: '#f8f9ff' }}>
                                    <Typography variant="subtitle2" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                        <TrendingUpIcon fontSize="small" /> Position Sizing
                                    </Typography>
                                    <Grid container spacing={2}>
                                        <Grid item xs={6}>
                                            <Typography variant="caption" color="text.secondary">Suggested Allocation</Typography>
                                            <Typography variant="body2" fontWeight="medium">
                                                {gptVerdict.execution_recommendations.position_sizing.suggested_allocation}
                                            </Typography>
                                        </Grid>
                                        <Grid item xs={6}>
                                            <Typography variant="caption" color="text.secondary">Risk Level</Typography>
                                            <Chip 
                                                label={gptVerdict.execution_recommendations.position_sizing.risk_level} 
                                                size="small" 
                                                color={gptVerdict.execution_recommendations.position_sizing.risk_level === 'Conservative' ? 'success' : 'warning'}
                                                variant="outlined"
                                            />
                                        </Grid>
                                        {gptVerdict.execution_recommendations.position_sizing.justification && (
                                            <Grid item xs={12}>
                                                <Typography variant="caption" color="text.secondary">Rationale</Typography>
                                                <Typography variant="body2" fontStyle="italic">
                                                    "{gptVerdict.execution_recommendations.position_sizing.justification}"
                                                </Typography>
                                            </Grid>
                                        )}
                                    </Grid>
                                </Paper>
                            )}
                            
                            <Grid container spacing={2} sx={{ mb: 2 }}>
                                {gptVerdict.execution_recommendations?.entry_conditions?.length > 0 && (
                                    <Grid item xs={12} md={6}>
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
                                    </Grid>
                                )}
                                
                                {gptVerdict.execution_recommendations?.exit_conditions?.length > 0 && (
                                    <Grid item xs={12} md={6}>
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
                                    </Grid>
                                )}
                            </Grid>
                            
                            {gptVerdict.actionable_ideas?.length > 0 && (
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
            )}
            
            {/* Strategy Cards */}
            <Box sx={{ mt: 2 }}>
                {allStrategies.map((strat, idx) => renderStrategyCard(strat, idx))}
            </Box>
        </AnalysisCard>
    );
};

const GptVerdictCard = ({ verdict }) => {
  if (!verdict) return null;

  return (
    <AnalysisCard title="GPT-Powered Verdict & Rationale">
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

      {verdict.search_performed && verdict.sources && verdict.sources.length > 0 && (
        <Box sx={{ mt: 3 }}>
          <Typography variant="subtitle2" gutterBottom>Sources Consulted</Typography>
          <List dense disablePadding>
            {verdict.sources.map((source, i) => (
              <ListItem key={i} disablePadding>
                <ListItemText 
                  primary={
                    <a href={source} target="_blank" rel="noopener noreferrer" style={{ color: '#1976d2', textDecoration: 'none' }}>
                      {source}
                    </a>
                  } 
                  primaryTypographyProps={{ variant: 'caption' }}
                />
              </ListItem>
            ))}
          </List>
        </Box>
      )}
    </AnalysisCard>
  );
};

const AnalysisDetails = ({ data }) => {
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

const ResultsDisplay = ({ analysisResult }) => {
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
          <AnalysisDetails data={result} />
        </Box>
      ))}
    </Box>
  );
};

const SavedVerdictsControls = ({ ticker, currentResult }) => {
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
                        ? (((item.analysis_method || '').includes('web') ? 'GPT Web Verdict' : 'GPT Verdict'))
                        : 'Model Verdict');
                      const isSelected = selectedId === item.id;
                      return (
                        <TableRow
                          key={item.id}
                          onClick={() => handleSelect(item.id)}
                          sx={{ cursor: 'pointer', bgcolor: isSelected ? 'action.selected' : 'inherit', '&:hover': { bgcolor: 'action.hover' } }}
                        >
                          <TableCell>{ts}</TableCell>
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
                      <TableCell colSpan={7} align="center">No saved verdicts yet.</TableCell>
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
  );
};

const MethodologyExplanation = ({ methodology }) => {
  if (methodology === 'gpt-5-web-verdict') {
    return (
      <AnalysisCard title="About: GPT-5 Web Verdict Analysis">
        <Typography paragraph>
          The <strong>GPT-5 Web Verdict</strong> methodology enhances the standard GPT Verdict by empowering the AI model with real-time web search capabilities.
        </Typography>
        <Typography paragraph>
          In addition to synthesizing the quantitative data provided by our internal analysis, the model will actively search for the latest news, analyst ratings, and market chatter related to the stock. This allows it to incorporate breaking developments and qualitative insights that are not captured in the raw market data, providing the most up-to-date and contextually-aware verdict possible.
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

const AnalysisPage = () => {
  const [ticker, setTicker] = useStickyState('SPY', 'ticker');
  const [analysisMethod, setAnalysisMethod] = useStickyState('holistic-market-edge', 'analysisMethod');
  const [riskFreeRate, setRiskFreeRate] = useStickyState(0.045, 'riskFreeRate');
  const [expirations, setExpirations] = useState([]);
  const [selectedExpiration, setSelectedExpiration] = useState('');
  const [fetchingExpirations, setFetchingExpirations] = useState(false);
  const [analysisResult, setAnalysisResult] = useStickyState(null, 'analysisResult');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  
  // GPT Model selection state
  const [availableModels, setAvailableModels] = useState([]);
  const [selectedModel, setSelectedModel] = useStickyState('gpt-5', 'selectedGptModel');
  const [fetchingModels, setFetchingModels] = useState(false);
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
    return Number.isFinite(numeric) ? numeric.toFixed(3) : '';
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
          setSelectedModel(response.data.default || 'gpt-5');
        }
      }
    } catch (error) {
      console.error('Failed to fetch GPT models:', error);
      console.error('Error details:', error.response?.data || error.message);
      // Fallback to default models if API fails
      setAvailableModels([
        { id: 'gpt-5', name: 'GPT-5 (Fallback)' },
        { id: 'gpt-4o', name: 'GPT-4o (Fallback)' },
        { id: 'claude-3.5-sonnet', name: 'Claude 3.5 Sonnet (Fallback)' }
      ]);
    } finally {
      setFetchingModels(false);
    }
  };

  // Load GPT models when analysis method is GPT-based
  useEffect(() => {
    if (analysisMethod.includes('gpt') && availableModels.length === 0) {
      fetchGptModels();
    }
  }, [analysisMethod]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory, historyReloadVersion]);

  const executeAnalysis = async ({ ticker: targetTicker, expiration: targetExpiration, riskFreeRate: targetRate, analysisMethod: targetMethod, gptModel: targetModel }) => {
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

    setTicker(normalizedTicker);
    setSelectedExpiration(normalizedExpiration);

    setLoading(true);
    setError('');
    setAnalysisResult(null);

    try {
      const response = await axios.post('/api/analysis/stock', {
        ticker: normalizedTicker,
        expiration_date: normalizedExpiration,
        risk_free_rate: targetRate,
        analysis_method: targetMethod,
        gpt_model: targetModel,
      });

      const result = response.data;
      const normalizedResult = (result && typeof result === 'object' && !Array.isArray(result)) ? [result] : result;
      setAnalysisResult(normalizedResult);

      setHistoryPage(1);
      setHistoryReloadVersion((prev) => prev + 1);
    } catch (err) {
      setError(err.response?.data?.detail || 'An unexpected error occurred.');
    } finally {
      setLoading(false);
    }
  };

  const handleFetchExpirations = async () => {
    if (!ticker) {
      setError('Please enter a ticker symbol first.');
      return;
    }
    setFetchingExpirations(true);
    setExpirations([]);
    setSelectedExpiration('');
    setAnalysisResult(null);
    setError('');
    try {
      // This endpoint needs to be created in the backend.
      const response = await axios.get(`/api/analysis/expirations/${ticker}`);
      if (response.data && response.data.length > 0) {
        setExpirations(response.data);
        setSelectedExpiration(response.data[0]); // Default to the first expiration
      } else {
        setError('No option expirations found for this ticker.');
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to fetch expirations.');
    } finally {
      setFetchingExpirations(false);
    }
  };

  const handleAnalyze = async (e) => {
    e.preventDefault();
    await executeAnalysis({
      ticker,
      expiration: selectedExpiration,
      riskFreeRate,
      analysisMethod,
      gptModel: selectedModel,
    });
  };

  const handleHistoryAnalyze = async (entry) => {
    if (!entry) return;

    const payload = entry.request_payload || {};
    const rawTicker = payload.ticker || entry.ticker || '';
    const rawExpiration = payload.expiration_date || entry.expiration_date_raw || entry.expiration_date || '';
    const nextMethod = payload.analysis_method || entry.analysis_method || analysisMethod;
    const nextRateCandidate = payload.risk_free_rate ?? entry.risk_free_rate ?? riskFreeRate;
    const nextRate = Number(nextRateCandidate);
    const needsGptModel = (nextMethod || '').includes('gpt');
    const nextModel = needsGptModel
      ? (payload.gpt_model || entry.gpt_model || selectedModel)
      : selectedModel;

    const normalizedTicker = rawTicker.trim().toUpperCase();

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
      setSelectedModel(nextModel);
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
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                label="Ticker"
                value={ticker}
                onChange={(e) => setTicker(e.target.value)}
                required
                fullWidth
                size="small"
              />
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
                  <MenuItem value="gpt-5-web-verdict">GPT-5 Web Verdict</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            
            {/* Show GPT model selector only for GPT-based methodologies */}
            {analysisMethod.includes('gpt') && (
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
                      ) : (
                        availableModels.map(model => (
                          <MenuItem key={model.id} value={model.id}>
                            {model.name}
                          </MenuItem>
                        ))
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

            {expirations.length > 0 && (
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
                inputProps={{ step: "0.001" }}
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
                disabled={loading || !selectedExpiration}
                fullWidth
                startIcon={loading ? <CircularProgress size={20} color="inherit" /> : <SmartToyIcon />}
              >
                2. Run Analysis
              </Button>
            </Grid>
          </Grid>
        </Box>

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {loading && <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}><CircularProgress /></Box>}
        {analysisResult && <ResultsDisplay analysisResult={analysisResult} />}
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
                      secondaryAction={
                        <Box>
                          <Button size="small" onClick={() => handleHistoryAnalyze(entry)} sx={{ mr: 1 }}>
                            Analyze Again
                          </Button>
                          <IconButton edge="end" size="small" onClick={() => handleRemoveHistoryItem(entry.id)}>
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
      />
    </Box>
  );
}

export default AnalysisPage;
