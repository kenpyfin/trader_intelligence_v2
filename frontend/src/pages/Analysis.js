import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import Plot from 'react-plotly.js';

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

const AnalysisCard = ({ title, children }) => (
  <div style={{ border: '1px solid #ddd', borderRadius: '8px', padding: '16px', marginBottom: '16px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
    <h3 style={{ marginTop: 0, borderBottom: '2px solid #eee', paddingBottom: '8px' }}>{title}</h3>
    {children}
  </div>
);

const CandlestickChart = ({ plotData, ticker }) => {
  if (!plotData || !plotData.data) {
    return <p>Chart data is not available.</p>;
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

  const layout = {
    title: `${ticker} Price Chart`,
    xaxis: {
      type: 'date',
      title: 'Date',
      tickformat: '%Y-%m-%d',
      rangeslider: { visible: false },
    },
    yaxis: { title: 'Price' },
    margin: { t: 40, b: 40, l: 50, r: 20 },
    height: 420,
    legend: { orientation: 'h' },
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
    if (loading) return <p>Loading futures data...</p>;
    if (!futures || futures.error || Object.keys(futures).length === 0) return <p>Could not load futures data.</p>;

    return (
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9em' }}>
        <thead>
          <tr style={{ background: '#f4f4f4' }}>
            {Object.keys(futures[Object.keys(futures)[0]]).map(header => <th key={header} style={{ padding: '8px', border: '1px solid #ddd' }}>{header}</th>)}
          </tr>
        </thead>
        <tbody>
          {Object.entries(futures).map(([ticker, data]) => (
            <tr key={ticker}>
              {Object.entries(data).map(([key, value]) => (
                <td key={key} style={{ padding: '8px', border: '1px solid #ddd', color: key === 'Change' && (value.startsWith('+') ? 'green' : 'red') }}>
                  {value}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    );
  };

  return (
    <AnalysisCard title="Macro Economy Insights">
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
        <div>
          <h4>Market Futures (Finviz)</h4>
          {renderFuturesTable()}
        </div>
        <div>
          <h4>Implied Risk-Free Rate Calculator</h4>
          <form onSubmit={handleCalculateRate}>
            <div style={{ marginBottom: '10px' }}>
              <label>Tickers (comma-separated):</label><br/>
              <input type="text" value={rfTickers} onChange={e => setRfTickers(e.target.value)} style={{ width: '95%' }}/>
            </div>
            <button type="submit" disabled={calculating}>
              {calculating ? 'Calculating...' : 'Calculate Implied Rate'}
            </button>
          </form>
          {calcResult !== null && (
            <div style={{ marginTop: '10px', background: '#e8f5e9', padding: '10px', borderRadius: '5px' }}>
              <strong>Calculated Rate: <span style={{color: 'green'}}>{(calcResult * 100).toFixed(3)}%</span></strong>
            </div>
          )}
          {calcLogs.length > 0 && (
            <div style={{ marginTop: '10px', maxHeight: '150px', overflowY: 'auto', background: '#f4f4f4', padding: '5px', fontSize: '0.8em', border: '1px solid #ddd' }}>
              <strong>Calculation Log:</strong>
              {calcLogs.map((log, i) => <p key={i} style={{margin: '2px 0'}}>{log}</p>)}
            </div>
          )}
        </div>
      </div>
    </AnalysisCard>
  );
};

const StrategyOrder = ({ strategy, strategies = [], ticker, expirationDate, gptVerdict }) => {
    const [isOrdering, setIsOrdering] = useState({});
    const [orderStatus, setOrderStatus] = useState({});    
    const [showGptInsights, setShowGptInsights] = useState(false);

    // If single strategy is passed, convert it to array for consistent handling
    const allStrategies = strategies && strategies.length > 0 ? strategies : (strategy ? [strategy] : []);

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

        const legDescriptions = strategy.legs.map((leg, i) => (
            <li key={i}>
                <strong>{leg.action}</strong> {leg.strike.toFixed(2)} {leg.right}
            </li>
        ));

        const confidence = strategy.confidence || 'Medium';
        const confidenceColor = {
            'High': 'green',
            'Medium': 'orange',
            'Low': 'red'
        }[confidence] || 'gray';

        return (
            <div key={index} style={{
                marginBottom: '20px',
                padding: '15px',
                border: '1px solid #e0e0e0',
                borderRadius: '8px',
                backgroundColor: '#fff'
            }}>
                <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: '10px',
                    paddingBottom: '10px',
                    borderBottom: '1px solid #f0f0f0'
                }}>
                    <h4 style={{ margin: 0 }}>{strategy.name}</h4>
                    <span style={{
                        padding: '2px 8px',
                        borderRadius: '10px',
                        backgroundColor: `${confidenceColor}20`,
                        color: confidenceColor,
                        fontSize: '12px',
                        fontWeight: 'bold'
                    }}>
                        {confidence} Confidence
                    </span>
                </div>
                
                <div style={{ marginBottom: '15px' }}>
                    <strong>Strategy Legs:</strong>
                    <ul style={{ 
                        margin: '5px 0 0 0', 
                        paddingLeft: '20px',
                        fontSize: '14px'
                    }}>
                        {legDescriptions}
                    </ul>
                </div>
                
                <button 
                    onClick={() => handleExecute(strategy, index)}
                    disabled={isOrdering[index]}
                    style={{
                        padding: '8px 16px',
                        backgroundColor: isOrdering[index] ? '#cccccc' : '#4CAF50',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        fontSize: '14px',
                        width: '100%',
                        transition: 'background-color 0.3s',
                        ':hover': {
                            backgroundColor: isOrdering[index] ? '#cccccc' : '#45a049'
                        }
                    }}
                >
                    {isOrdering[index] ? 'Placing Order...' : `Execute ${strategy.name}`}
                </button>
                
                {orderStatus[index] && (
                    <div style={{
                        marginTop: '10px',
                        padding: '10px',
                        borderRadius: '5px',
                        background: orderStatus[index].status === 'error' ? '#ffebee' : '#e8f5e9',
                        borderLeft: `4px solid ${orderStatus[index].status === 'error' ? '#f44336' : '#4CAF50'}`
                    }}>
                        <p style={{ margin: '0', color: orderStatus[index].status === 'error' ? '#d32f2f' : '#2e7d32' }}>
                            <strong>{orderStatus[index].status === 'error' ? 'Error:' : 'Success:'}</strong> {orderStatus[index].message}
                        </p>
                        {orderStatus[index].status === 'success' && orderStatus[index].order_status && (
                            <p style={{ margin: '5px 0 0 0', fontSize: '13px' }}>
                                <strong>Order Status:</strong> {orderStatus[index].order_status}
                            </p>
                        )}
                    </div>
                )}
            </div>
        );
    };

    return (
        <AnalysisCard title={allStrategies.length > 1 ? "Recommended Strategies" : "Execute Strategy"}>
            
            {/* GPT Insights Section */}
            {gptVerdict && (
                <div style={{ 
                    marginBottom: '20px', 
                    padding: '15px', 
                    border: '1px solid #e0e0e0', 
                    borderRadius: '8px', 
                    backgroundColor: '#f8f9fa' 
                }}>
                    <div style={{ 
                        display: 'flex', 
                        justifyContent: 'space-between', 
                        alignItems: 'center', 
                        marginBottom: '10px' 
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                            <span style={{ fontSize: '18px' }}>🤖</span>
                            <h3 style={{ margin: 0 }}>AI Trading Insights</h3>
                        </div>
                        <button 
                            onClick={() => setShowGptInsights(!showGptInsights)}
                            style={{ 
                                padding: '4px 12px', 
                                fontSize: '13px', 
                                cursor: 'pointer',
                                backgroundColor: 'transparent',
                                border: '1px solid #d0d0d0',
                                borderRadius: '4px',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '5px'
                            }}
                        >
                            {showGptInsights ? (
                                <>
                                    <span>Hide Details</span>
                                    <span>▲</span>
                                </>
                            ) : (
                                <>
                                    <span>Show Details</span>
                                    <span>▼</span>
                                </>
                            )}
                        </button>
                    </div>
                    
                    <div style={{ 
                        display: 'flex', 
                        alignItems: 'center', 
                        marginBottom: showGptInsights ? '15px' : 0,
                        paddingBottom: showGptInsights ? '15px' : 0,
                        borderBottom: showGptInsights ? '1px solid #e8e8e8' : 'none'
                    }}>
                        <strong style={{ marginRight: '5px' }}>Market Bias:</strong>
                        <span style={{ 
                            padding: '2px 8px',
                            borderRadius: '10px',
                            backgroundColor: gptVerdict.final_bias?.includes('Bull') ? '#e8f5e9' : 
                                           gptVerdict.final_bias?.includes('Bear') ? '#ffebee' : '#e3f2fd',
                            color: gptVerdict.final_bias?.includes('Bull') ? '#2e7d32' : 
                                  gptVerdict.final_bias?.includes('Bear') ? '#c62828' : '#1565c0',
                            fontWeight: '500',
                            fontSize: '13px'
                        }}>
                            {gptVerdict.final_bias || 'Neutral'}
                        </span>
                    </div>
                    
                    {showGptInsights && (
                        <div style={{ marginTop: '15px' }}>
                            {gptVerdict.execution_recommendations?.primary_strategy && (
                                <div style={{ 
                                    backgroundColor: '#f0f7ff',
                                    padding: '12px',
                                    borderRadius: '6px',
                                    marginBottom: '15px',
                                    borderLeft: '4px solid #4a90e2'
                                }}>
                                    <div style={{ 
                                        display: 'flex', 
                                        alignItems: 'center', 
                                        marginBottom: '8px' 
                                    }}>
                                        <span style={{ 
                                            backgroundColor: '#4a90e2', 
                                            color: 'white', 
                                            borderRadius: '50%', 
                                            width: '24px', 
                                            height: '24px', 
                                            display: 'flex', 
                                            alignItems: 'center', 
                                            justifyContent: 'center',
                                            marginRight: '10px',
                                            fontSize: '14px',
                                            fontWeight: 'bold'
                                        }}>
                                            ✓
                                        </span>
                                        <h4 style={{ margin: 0, color: '#1a365d' }}>Recommended Strategy</h4>
                                    </div>
                                    <div style={{ paddingLeft: '34px' }}>
                                        <p style={{ 
                                            margin: '0 0 8px 0', 
                                            fontSize: '14px',
                                            lineHeight: '1.5',
                                            color: '#2d3748'
                                        }}>
                                            {gptVerdict.execution_recommendations.primary_strategy.description || 
                                             'No specific strategy description available.'}
                                        </p>
                                        <div style={{ 
                                            display: 'flex', 
                                            alignItems: 'center',
                                            fontSize: '13px',
                                            color: '#4a5568'
                                        }}>
                                            <span style={{ marginRight: '15px' }}>
                                                <strong>Confidence:</strong> 
                                                <span style={{
                                                    color: gptVerdict.execution_recommendations.primary_strategy.confidence === 'High' ? 'green' : 
                                                          gptVerdict.execution_recommendations.primary_strategy.confidence === 'Medium' ? 'orange' : 'red',
                                                    marginLeft: '5px'
                                                }}>
                                                    {gptVerdict.execution_recommendations.primary_strategy.confidence}
                                                </span>
                                            </span>
                                            {gptVerdict.execution_recommendations.primary_strategy.time_horizon && (
                                                <span>
                                                    <strong>Timeframe:</strong> {gptVerdict.execution_recommendations.primary_strategy.time_horizon}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            )}
                            
                            {gptVerdict.execution_recommendations?.position_sizing && (
                                <div style={{ 
                                    backgroundColor: '#f8f9ff',
                                    border: '1px solid #e0e0ff',
                                    borderRadius: '6px',
                                    padding: '12px',
                                    marginBottom: '15px'
                                }}>
                                    <h5 style={{ 
                                        margin: '0 0 10px 0', 
                                        color: '#4a4a8a',
                                        fontSize: '14px',
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: '8px'
                                    }}>
                                        <span>📊</span>
                                        Position Sizing
                                    </h5>
                                    <div style={{
                                        display: 'grid',
                                        gridTemplateColumns: '1fr 1fr',
                                        gap: '15px',
                                        fontSize: '13px'
                                    }}>
                                        <div>
                                            <div style={{ color: '#6b7280', marginBottom: '4px' }}>Suggested Allocation</div>
                                            <div style={{ fontWeight: '500' }}>
                                                {gptVerdict.execution_recommendations.position_sizing.suggested_allocation}
                                            </div>
                                        </div>
                                        <div>
                                            <div style={{ color: '#6b7280', marginBottom: '4px' }}>Risk Level</div>
                                            <div>
                                                <span style={{
                                                    padding: '2px 8px',
                                                    borderRadius: '10px',
                                                    backgroundColor: gptVerdict.execution_recommendations.position_sizing.risk_level === 'Conservative' ? '#e6f6e6' : 
                                                                  gptVerdict.execution_recommendations.position_sizing.risk_level === 'Moderate' ? '#fff3e0' : '#ffebee',
                                                    color: gptVerdict.execution_recommendations.position_sizing.risk_level === 'Conservative' ? '#2e7d32' : 
                                                          gptVerdict.execution_recommendations.position_sizing.risk_level === 'Moderate' ? '#e65100' : '#c62828',
                                                    fontSize: '12px',
                                                    fontWeight: '500'
                                                }}>
                                                    {gptVerdict.execution_recommendations.position_sizing.risk_level}
                                                </span>
                                            </div>
                                        </div>
                                        {gptVerdict.execution_recommendations.position_sizing.justification && (
                                            <div style={{ gridColumn: '1 / -1' }}>
                                                <div style={{ color: '#6b7280', marginBottom: '4px' }}>Rationale</div>
                                                <div style={{ fontStyle: 'italic', fontSize: '12px' }}>
                                                    "{gptVerdict.execution_recommendations.position_sizing.justification}"
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}
                            
                            <div style={{
                                display: 'grid',
                                gridTemplateColumns: '1fr 1fr',
                                gap: '15px',
                                marginBottom: '15px'
                            }}>
                                {gptVerdict.execution_recommendations?.entry_conditions?.length > 0 && (
                                    <div style={{
                                        backgroundColor: '#f0fdf4',
                                        border: '1px solid #dcfce7',
                                        borderRadius: '6px',
                                        padding: '12px'
                                    }}>
                                        <h5 style={{
                                            margin: '0 0 10px 0',
                                            color: '#166534',
                                            fontSize: '14px',
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: '8px'
                                        }}>
                                            <span>📈</span>
                                            Entry Conditions
                                        </h5>
                                        <ul style={{
                                            margin: '0',
                                            paddingLeft: '20px',
                                            fontSize: '13px',
                                            color: '#1f2937'
                                        }}>
                                            {gptVerdict.execution_recommendations.entry_conditions.slice(0, 3).map((condition, i) => (
                                                <li key={i} style={{ marginBottom: '6px', lineHeight: '1.4' }}>
                                                    {condition}
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                                
                                {gptVerdict.execution_recommendations?.exit_conditions?.length > 0 && (
                                    <div style={{
                                        backgroundColor: '#fff7ed',
                                        border: '1px solid #ffedd5',
                                        borderRadius: '6px',
                                        padding: '12px'
                                    }}>
                                        <h5 style={{
                                            margin: '0 0 10px 0',
                                            color: '#9a3412',
                                            fontSize: '14px',
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: '8px'
                                        }}>
                                            <span>📉</span>
                                            Exit Conditions
                                        </h5>
                                        <ul style={{
                                            margin: '0',
                                            paddingLeft: '20px',
                                            fontSize: '13px',
                                            color: '#1f2937'
                                        }}>
                                            {gptVerdict.execution_recommendations.exit_conditions.slice(0, 3).map((condition, i) => (
                                                <li key={i} style={{ marginBottom: '6px', lineHeight: '1.4' }}>
                                                    {condition}
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                                
                                {gptVerdict.execution_recommendations?.stop_loss_guidance && (
                                    <div style={{
                                        backgroundColor: '#fef2f2',
                                        border: '1px solid #fee2e2',
                                        borderRadius: '6px',
                                        padding: '12px'
                                    }}>
                                        <h5 style={{
                                            margin: '0 0 10px 0',
                                            color: '#b91c1c',
                                            fontSize: '14px',
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: '8px'
                                        }}>
                                            <span>🛡️</span>
                                            Stop Loss
                                        </h5>
                                        <p style={{
                                            margin: '0',
                                            fontSize: '13px',
                                            color: '#1f2937',
                                            lineHeight: '1.5'
                                        }}>
                                            {gptVerdict.execution_recommendations.stop_loss_guidance}
                                        </p>
                                    </div>
                                )}
                                
                                {gptVerdict.execution_recommendations?.profit_target_guidance && (
                                    <div style={{
                                        backgroundColor: '#f0fdf4',
                                        border: '1px solid #dcfce7',
                                        borderRadius: '6px',
                                        padding: '12px'
                                    }}>
                                        <h5 style={{
                                            margin: '0 0 10px 0',
                                            color: '#166534',
                                            fontSize: '14px',
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: '8px'
                                        }}>
                                            <span>🎯</span>
                                            Profit Target
                                        </h5>
                                        <p style={{
                                            margin: '0',
                                            fontSize: '13px',
                                            color: '#1f2937',
                                            lineHeight: '1.5'
                                        }}>
                                            {gptVerdict.execution_recommendations.profit_target_guidance}
                                        </p>
                                    </div>
                                )}
                            </div>
                            
                            {gptVerdict.actionable_ideas?.length > 0 && (
                                <div style={{
                                    backgroundColor: '#f0f9ff',
                                    border: '1px solid #e0f2fe',
                                    borderRadius: '6px',
                                    padding: '12px',
                                    marginBottom: '15px'
                                }}>
                                    <h5 style={{
                                        margin: '0 0 10px 0',
                                        color: '#075985',
                                        fontSize: '14px',
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: '8px'
                                    }}>
                                        <span>💡</span>
                                        Key Trading Ideas
                                    </h5>
                                    <ul style={{
                                        margin: '0',
                                        paddingLeft: '20px',
                                        fontSize: '13px',
                                        color: '#1f2937'
                                    }}>
                                        {gptVerdict.actionable_ideas.slice(0, 3).map((idea, i) => (
                                            <li key={i} style={{ marginBottom: '6px', lineHeight: '1.5' }}>
                                                {idea}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                            
                            {gptVerdict.risk_factors?.length > 0 && (
                                <div style={{
                                    backgroundColor: '#fef2f2',
                                    border: '1px solid #fee2e2',
                                    borderRadius: '6px',
                                    padding: '12px',
                                    marginBottom: '10px'
                                }}>
                                    <h5 style={{
                                        margin: '0 0 10px 0',
                                        color: '#b91c1c',
                                        fontSize: '14px',
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: '8px'
                                    }}>
                                        <span>⚠️</span>
                                        Risk Factors
                                    </h5>
                                    <ul style={{
                                        margin: '0',
                                        paddingLeft: '20px',
                                        fontSize: '13px',
                                        color: '#1f2937'
                                    }}>
                                        {gptVerdict.risk_factors.slice(0, 3).map((risk, i) => (
                                            <li key={i} style={{ marginBottom: '6px', lineHeight: '1.5' }}>
                                                {risk}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                            
                            {gptVerdict.execution_recommendations?.alternative_strategies?.length > 0 && (
                                <div style={{
                                    backgroundColor: '#f9fafb',
                                    border: '1px solid #e5e7eb',
                                    borderRadius: '6px',
                                    padding: '12px',
                                    marginTop: '15px'
                                }}>
                                    <h5 style={{
                                        margin: '0 0 10px 0',
                                        color: '#4b5563',
                                        fontSize: '14px',
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: '8px'
                                    }}>
                                        <span>🔄</span>
                                        Alternative Strategies
                                    </h5>
                                    <div style={{
                                        display: 'grid',
                                        gap: '10px'
                                    }}>
                                        {gptVerdict.execution_recommendations.alternative_strategies.slice(0, 2).map((alt, i) => (
                                            <div key={i} style={{
                                                backgroundColor: 'white',
                                                border: '1px solid #e5e7eb',
                                                borderRadius: '6px',
                                                padding: '10px',
                                                fontSize: '13px'
                                            }}>
                                                <div style={{
                                                    display: 'flex',
                                                    justifyContent: 'space-between',
                                                    alignItems: 'center',
                                                    marginBottom: '6px'
                                                }}>
                                                    <strong style={{
                                                        color: '#1f2937',
                                                        fontSize: '13px'
                                                    }}>
                                                        {alt.type}
                                                    </strong>
                                                    <span style={{
                                                        padding: '2px 8px',
                                                        borderRadius: '10px',
                                                        backgroundColor: alt.confidence === 'High' ? '#e6f6e6' : 
                                                                      alt.confidence === 'Medium' ? '#fff3e0' : '#ffebee',
                                                        color: alt.confidence === 'High' ? '#2e7d32' : 
                                                              alt.confidence === 'Medium' ? '#e65100' : '#c62828',
                                                        fontSize: '11px',
                                                        fontWeight: '500'
                                                    }}>
                                                        {alt.confidence} Confidence
                                                    </span>
                                                </div>
                                                <p style={{
                                                    margin: '0',
                                                    color: '#4b5563',
                                                    lineHeight: '1.5',
                                                    fontSize: '12px'
                                                }}>
                                                    {alt.description}
                                                </p>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}
            
            {/* Strategy Cards */}
            <div style={{
                display: 'grid',
                gap: '15px',
                marginTop: '20px'
            }}>
                {allStrategies.map((strat, idx) => renderStrategyCard(strat, idx))}
            </div>
        </AnalysisCard>
    );
};

const GptVerdictCard = ({ verdict }) => {
  if (!verdict) return null;

  return (
    <AnalysisCard title="GPT-Powered Verdict & Rationale">
      {verdict.key_reasoning_points && verdict.key_reasoning_points.length > 0 && (
        <>
          <h5>Key Analysis Points</h5>
          <ul style={{ backgroundColor: '#f8f9fa', padding: '10px', borderRadius: '4px', marginBottom: '15px' }}>
            {verdict.key_reasoning_points.map((point, i) => <li key={i} style={{ marginBottom: '5px' }}><strong>{point}</strong></li>)}
          </ul>
        </>
      )}
      
      {verdict.rationale && (
        <>
          <h5>Detailed Reasoning</h5>
          <p style={{ lineHeight: '1.6', backgroundColor: '#fff', padding: '12px', border: '1px solid #e9ecef', borderRadius: '4px' }}>
            {verdict.rationale}
          </p>
        </>
      )}
      
      {verdict.actionable_ideas && verdict.actionable_ideas.length > 0 && (
        <>
          <h5>Actionable Ideas</h5>
          <ul>
            {verdict.actionable_ideas.map((idea, i) => <li key={i}>{idea}</li>)}
          </ul>
        </>
      )}

      {verdict.risk_factors && verdict.risk_factors.length > 0 && (
        <>
          <h5>Risk Factors</h5>
          <ul>
            {verdict.risk_factors.map((risk, i) => <li key={i}>{risk}</li>)}
          </ul>
        </>
      )}

      {verdict.search_performed && verdict.sources && verdict.sources.length > 0 && (
        <>
          <h5>Sources Consulted</h5>
          <ul>
            {verdict.sources.map((source, i) => <li key={i}><a href={source} target="_blank" rel="noopener noreferrer">{source}</a></li>)}
          </ul>
        </>
      )}
    </AnalysisCard>
  );
};

const AnalysisDetails = ({ data }) => {
  const finalBias = data.final_bias || '';
  const biasColor = finalBias.includes('Bullish') ? 'green' : finalBias.includes('Bearish') ? 'red' : 'orange';

  const isGptResult = !!data.gpt_verdict;
  const conclusionTitle = isGptResult
    ? `AI-Powered Conclusion & Strategy (DTE: ${data.dte} days)`
    : `Holistic Conclusion & Strategy (DTE: ${data.dte} days)`;

  const renderUOA = (uoaList, type) => {
    if (!uoaList || uoaList.length === 0) return null;
    return (
      <div style={{marginTop: '10px'}}>
        <strong>Unusual {type} Activity:</strong>
        <ul style={{ margin: '5px 0', paddingLeft: '20px' }}>
          {uoaList.map((item, i) => (
            <li key={i}>
              {item.Type || type} @ ${item.Strike.toFixed(2)} (Vol: {item.Volume}, OI: {item['Open Int.']})
            </li>
          ))}
        </ul>
      </div>
    );
  };

  return (
    <div>
      <AnalysisCard title={conclusionTitle}>
        <h4 style={{ color: biasColor }}>Final Bias: {finalBias}</h4>
        <div dangerouslySetInnerHTML={{ __html: data.final_conclusion_html }} />
      </AnalysisCard>

      {data.gpt_verdict && <GptVerdictCard verdict={data.gpt_verdict} />}

      <AnalysisCard title="Price Chart (Candlesticks + MAs)">
        {data.candlestick_analysis?.plot_data ? 
          <CandlestickChart plotData={data.candlestick_analysis.plot_data} ticker={data.ticker} /> :
          <p>{data.candlestick_analysis?.error || "No chart data."}</p>
        }
        <p><strong>Primary Trend:</strong> {data.candlestick_analysis?.context?.primary_trend}</p>
        <p><strong>Secondary Trend:</strong> {data.candlestick_analysis?.context?.secondary_trend}</p>
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
              <div style={{marginTop: '5px'}}>
                <strong>Recent Patterns Identified:</strong>
                <ul style={{ margin: '5px 0', paddingLeft: '20px' }}>
                  {data.candlestick_analysis.patterns.map((p, i) => (
                    <li key={i}>
                      <strong>{p.name}</strong> (Strength: {p.strength}) - {p.interpretation}
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p style={{marginTop: '5px'}}><strong>Patterns:</strong> No significant candlestick patterns identified in the last few periods.</p>
            )}
          </AnalysisCard>

          <AnalysisCard title="2. Sentiment Analysis (Volume & OI)">
            <p><strong>Put/Call Ratio (Volume):</strong> {data.volume_oi_analysis?.pc_ratio?.toFixed(2) || 'N/A'}</p>
            {data.volume_oi_analysis?.oi_put_wall && <p><strong>Put Wall (Support):</strong> ${data.volume_oi_analysis.oi_put_wall.Strike.toFixed(2)} (OI: {data.volume_oi_analysis.oi_put_wall['Open Int.']})</p>}
            {data.volume_oi_analysis?.oi_call_wall && <p><strong>Call Wall (Resistance):</strong> ${data.volume_oi_analysis.oi_call_wall.Strike.toFixed(2)} (OI: {data.volume_oi_analysis.oi_call_wall['Open Int.']})</p>}
            {renderUOA(data.volume_oi_analysis?.uoa_calls, 'Call')}
            {renderUOA(data.volume_oi_analysis?.uoa_puts, 'Put')}
          </AnalysisCard>

          <AnalysisCard title="3. Volatility & Movement Analysis">
            <p><strong>Market-Implied Move:</strong> {data.movement_analysis?.expected_move_pct?.toFixed(2) || 'N/A'}%</p>
            {data.movement_analysis?.vol_compression_text && <p><strong>Volatility Compression:</strong> {data.movement_analysis.vol_compression_text}</p>}
            {data.movement_analysis?.earnings_note && <p><strong>Catalyst Event:</strong> {data.movement_analysis.earnings_note}</p>}
          </AnalysisCard>
          
          <AnalysisCard title="4. Quantitative Valuation (Undervalued Options)">
            {data.results_df && data.results_df.length > 0 ? (
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: '#f4f4f4' }}>
                    <th style={{ padding: '8px', border: '1px solid #ddd' }}>Strike</th>
                    <th style={{ padding: '8px', border: '1px solid #ddd' }}>Type</th>
                    <th style={{ padding: '8px', border: '1px solid #ddd' }}>Market Price</th>
                    <th style={{ padding: '8px', border: '1px solid #ddd' }}>Model Price</th>
                  </tr>
                </thead>
                <tbody>
                  {data.results_df.map((opt, i) => (
                    <tr key={i}>
                      <td style={{ padding: '8px', border: '1px solid #ddd' }}>${opt.Strike.toFixed(2)}</td>
                      <td style={{ padding: '8px', border: '1px solid #ddd' }}>{opt.Type}</td>
                      <td style={{ padding: '8px', border: '1px solid #ddd' }}>${opt['Market Price'].toFixed(2)}</td>
                      <td style={{ padding: '8px', border: '1px solid #ddd' }}>${opt['Model Price'].toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <p>No significantly undervalued options were found.</p>}
          </AnalysisCard>
        </>
      }
    </div>
  );
};

const ResultsDisplay = ({ analysisResult }) => {
  if (!analysisResult || !Array.isArray(analysisResult) || analysisResult.length === 0) {
    return <p>No analysis results to display.</p>;
  }
  
  const commonData = analysisResult[0]; // Use first result for common data like ticker and price

  return (
    <div style={{ marginTop: '20px' }}>
      <h2>Analysis for {commonData.ticker?.toUpperCase()}</h2>
      <p>Current Price: <strong>{typeof commonData.S_current === 'number' ? `$${commonData.S_current.toFixed(2)}` : 'N/A'}</strong></p>

      {analysisResult.map((result, index) => (
        <div key={index} style={{ borderTop: index > 0 ? '3px solid #007bff' : 'none', paddingTop: index > 0 ? '20px' : '0', marginTop: index > 0 ? '20px' : '0' }}>
          <AnalysisDetails data={result} />
        </div>
      ))}

      {/* Verdict history moved outside the results box */}
    </div>
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
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '16px' }}>
        <div>
          <h4>Add Current Verdict to History</h4>
          <div style={{ marginBottom: '8px' }}>
            <label>Label (optional):</label><br/>
            <input type="text" value={saveLabel} onChange={e => setSaveLabel(e.target.value)} placeholder="e.g., Before Earnings" style={{ width: '95%' }} />
          </div>
          <button onClick={handleSave} disabled={saving || !ticker || !currentResult} style={{ padding: '6px 12px' }}>
            {saving ? 'Saving...' : 'Add to History'}
          </button>
          {saveMsg && <div style={{ marginTop: '8px', fontSize: '0.9em' }}>{saveMsg}</div>}
        </div>

        <div>
          <h4>History</h4>
          {listLoading ? (
            <p>Loading verdict history...</p>
          ) : (
            <div style={{ maxHeight: '320px', overflow: 'auto', border: '1px solid #e0e0e0', borderRadius: 4 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: '#f7f7f7' }}>
                    <th style={{ textAlign: 'left', padding: '6px', borderBottom: '1px solid #e0e0e0' }}>Saved At</th>
                    <th style={{ textAlign: 'left', padding: '6px', borderBottom: '1px solid #e0e0e0' }}>Label</th>
                    <th style={{ textAlign: 'left', padding: '6px', borderBottom: '1px solid #e0e0e0' }}>Type</th>
                    <th style={{ textAlign: 'left', padding: '6px', borderBottom: '1px solid #e0e0e0' }}>Bias</th>
                    <th style={{ textAlign: 'left', padding: '6px', borderBottom: '1px solid #e0e0e0' }}>Expiration</th>
                    <th style={{ textAlign: 'right', padding: '6px', borderBottom: '1px solid #e0e0e0' }}>DTE</th>
                    <th style={{ textAlign: 'right', padding: '6px', borderBottom: '1px solid #e0e0e0' }}>Price</th>
                  </tr>
                </thead>
                <tbody>
                  {savedList && savedList.length > 0 ? (
                    savedList.map(item => {
                      const ts = item.created_at?.slice(0, 19).replace('T',' ');
                      const ov = item.overview || {};
                      const typeText = ov.method_label || ((item.analysis_method || '').includes('gpt')
                        ? (((item.analysis_method || '').includes('web') ? 'GPT Web Verdict' : 'GPT Verdict'))
                        : 'Model Verdict');
                      const isSelected = selectedId === item.id;
                      return (
                        <tr
                          key={item.id}
                          onClick={() => handleSelect(item.id)}
                          style={{ cursor: 'pointer', background: isSelected ? '#eef6ff' : 'transparent' }}
                        >
                          <td style={{ padding: '6px', borderBottom: '1px solid #f0f0f0' }}>{ts}</td>
                          <td style={{ padding: '6px', borderBottom: '1px solid #f0f0f0' }}>{item.label || ''}</td>
                          <td style={{ padding: '6px', borderBottom: '1px solid #f0f0f0' }}>{typeText}</td>
                          <td style={{ padding: '6px', borderBottom: '1px solid #f0f0f0' }}>{item.final_bias || ov.final_bias || ''}</td>
                          <td style={{ padding: '6px', borderBottom: '1px solid #f0f0f0' }}>{item.expiration_date || ov.expiration_date || ''}</td>
                          <td style={{ padding: '6px', borderBottom: '1px solid #f0f0f0', textAlign: 'right' }}>{ov.dte ?? ''}</td>
                          <td style={{ padding: '6px', borderBottom: '1px solid #f0f0f0', textAlign: 'right' }}>{typeof ov.S_current === 'number' ? `$${ov.S_current.toFixed(2)}` : ''}</td>
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan="7" style={{ padding: '10px', textAlign: 'center', color: '#777' }}>No saved verdicts yet.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
            <div>
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1} style={{ marginRight: 8 }}>Prev</button>
              <button onClick={() => setPage(p => (hasMore ? p + 1 : p))} disabled={!hasMore}>Next</button>
            </div>
            <div style={{ color: '#555', fontSize: '0.9em' }}>
              Page {page} of {Math.max(1, Math.ceil((total||0) / pageSize))} • {total} total
            </div>
            <div>
              <label style={{ marginRight: 6 }}>Page size:</label>
              <select value={pageSize} onChange={e => setPageSize(parseInt(e.target.value) || 10)}>
                {[10, 25, 50, 100].map(sz => <option key={sz} value={sz}>{sz}</option>)}
              </select>
            </div>
          </div>

          {selectedDoc && (
            <div style={{ marginTop: '12px' }}>
              <div><strong>Saved Bias:</strong> {previousBias || 'N/A'}</div>
              {biasChanged && (
                <div style={{ color: '#d9534f' }}><strong>Changed vs Current:</strong> {currentBias || 'N/A'}</div>
              )}
              <div style={{ marginTop: '8px' }}>
                <strong>Saved Summary</strong>
                <div dangerouslySetInnerHTML={{ __html: selectedDoc?.data?.final_conclusion_html || '<p>No saved summary.</p>' }} />
              </div>
            </div>
          )}
        </div>
      </div>
    </AnalysisCard>
  );
};

const MethodologyExplanation = ({ methodology }) => {
  if (methodology === 'gpt-5-web-verdict') {
    return (
      <AnalysisCard title="About: GPT-5 Web Verdict Analysis">
        <p>
          The <strong>GPT-5 Web Verdict</strong> methodology enhances the standard GPT Verdict by empowering the AI model with real-time web search capabilities.
        </p>
        <p>
          In addition to synthesizing the quantitative data provided by our internal analysis, the model will actively search for the latest news, analyst ratings, and market chatter related to the stock. This allows it to incorporate breaking developments and qualitative insights that are not captured in the raw market data, providing the most up-to-date and contextually-aware verdict possible.
        </p>
      </AnalysisCard>
    );
  }

  if (methodology === 'gpt-verdict') {
    return (
      <AnalysisCard title="About: GPT Verdict Analysis">
        <p>
          The <strong>GPT Verdict</strong> methodology leverages a powerful Large Language Model (LLM) to synthesize the output of all standard sub-analyses.
        </p>
        <p>
          Instead of relying on a rules-based scoring system, this approach provides the AI with the complete, structured data from the Trend, Sentiment, Volatility, and Quantitative analyses. The model then acts as an expert analyst, weighing the evidence, identifying nuanced connections, and generating a final verdict that includes a detailed rationale, actionable ideas, and key risk factors. This provides a qualitative, expert-level second opinion on the quantitative data.
        </p>
      </AnalysisCard>
    );
  }
  
  if (methodology === 'holistic-market-edge') {
    return (
      <AnalysisCard title="About: Holistic Market Edge Analysis">
        <p>
          The <strong>Holistic Market Edge</strong> methodology is a multi-faceted approach to stock and option analysis, designed to synthesize a wide range of market data into a single, actionable conclusion. It avoids relying on a single indicator and instead builds a &quot;weight of the evidence&quot; verdict.
        </p>
        <h5>How the Final Verdict is Generated:</h5>
        <p>
          The final bias (e.g., Bullish, Bearish, Neutral) is determined by a scoring system that aggregates sentiment from several core analytical components:
        </p>
        <ol>
          <li><strong>Price Trend &amp; Candlesticks:</strong> Establishes the market&apos;s primary and secondary trends using moving averages and identifies recent, psychologically significant candlestick patterns for short-term sentiment.</li>
          <li><strong>Sentiment Analysis:</strong> Gauges market sentiment by analyzing put/call ratios, unusual options activity (UOA), and significant open interest levels (support/resistance walls).</li>
          <li><strong>Volatility Analysis:</strong> Compares implied volatility (IV) to historical volatility (HV) to determine if options are &quot;cheap&quot; or &quot;expensive.&quot; It also checks for volatility compression, which often precedes large price moves.</li>
          <li><strong>Catalyst Events:</strong> Checks for upcoming earnings reports before the option&apos;s expiration date, as these are significant drivers of volatility and price movement.</li>
          <li><strong>Quantitative Valuation:</strong> Uses a binomial pricing model to calculate a theoretical option price, which is then compared to the market price to find potentially undervalued opportunities.</li>
        </ol>
        <p>
          Each component contributes a bullish, bearish, or neutral signal to the final score. A strong bias is formed only when the evidence from multiple, diverse components points in the same direction. This comprehensive approach aims to provide a robust and well-rounded trading edge.
        </p>
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
  }, [normalizedTickerForHistory, historyScope, historyPage]);

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
    <div>
      <MacroInsights onRateCalculated={setRiskFreeRate} />
      
      <MethodologyExplanation methodology={analysisMethod} />

      <AnalysisCard title="Stock and Option Analysis">
        <form onSubmit={handleAnalyze} style={{ marginBottom: '20px' }}>
          <div style={{ display: 'flex', gap: '15px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
              <div>
                <label>Ticker:</label><br/>
                <input type="text" value={ticker} onChange={(e) => setTicker(e.target.value)} required />
              </div>

              <div>
                <label>Analysis Methodology:</label><br/>
                <select value={analysisMethod} onChange={e => setAnalysisMethod(e.target.value)} style={{ padding: '4px', height: '29px' }}>
                    <option value="holistic-market-edge">Holistic Market Edge</option>
                    <option value="gpt-verdict">GPT Verdict</option>
                    <option value="gpt-5-web-verdict">GPT-5 Web Verdict</option>
                </select>
              </div>
              
              {/* Show GPT model selector only for GPT-based methodologies */}
              {analysisMethod.includes('gpt') && (
                <div>
                  <label>GPT Model:</label><br/>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <select 
                      value={selectedModel} 
                      onChange={e => setSelectedModel(e.target.value)} 
                      style={{ padding: '4px', height: '29px', flex: 1 }}
                      disabled={fetchingModels}
                    >
                      {fetchingModels ? (
                        <option>Loading models...</option>
                      ) : (
                        availableModels.map(model => (
                          <option key={model.id} value={model.id}>
                            {model.name}
                          </option>
                        ))
                      )}
                    </select>
                    <button 
                      type="button"
                      onClick={fetchGptModels}
                      disabled={fetchingModels}
                      style={{ padding: '4px 8px', fontSize: '12px', cursor: 'pointer' }}
                      title="Refresh models list"
                    >
                      🔄
                    </button>
                  </div>
                  {fetchingModels && <div style={{ fontSize: '0.8em', color: '#666' }}>Fetching available models...</div>}
                  {availableModels.some(m => m.name.includes('Fallback')) && (
                    <div style={{ fontSize: '0.8em', color: '#ff6600' }}>
                      ⚠️ Using fallback models - click 🔄 to retry loading from server
                    </div>
                  )}
                </div>
              )}

              <button type="button" onClick={handleFetchExpirations} disabled={fetchingExpirations || !ticker.trim()} style={{ padding: '5px 15px', cursor: 'pointer', height: 'fit-content' }}>
                {fetchingExpirations ? 'Fetching...' : '1. Fetch Expirations'}
              </button>

              {expirations.length > 0 && (
                <div>
                  <label>Expiration Date:</label><br/>
                  <select value={selectedExpiration} onChange={e => setSelectedExpiration(e.target.value)} style={{ padding: '4px', height: '29px' }}>
                    {expirations.map(exp => (
                      <option key={exp} value={exp}>
                        {new Date(exp.replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3')).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' })}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label>Risk-Free Rate:</label><br/>
                <input type="number" step="0.001" value={riskFreeRate} onChange={(e) => setRiskFreeRate(parseFloat(e.target.value))} required style={{width: '80px'}}/>
              </div>

              <button type="submit" disabled={loading || !selectedExpiration} style={{ padding: '5px 15px', cursor: 'pointer', height: 'fit-content' }}>
                {loading ? 'Analyzing...' : '2. Run Analysis'}
              </button>
          </div>
        </form>

        {error && <p style={{ color: 'red', border: '1px solid red', padding: '10px', borderRadius: '5px' }}><strong>Error:</strong> {error}</p>}
        {loading && <p>Loading analysis...</p>}
        {analysisResult && <ResultsDisplay analysisResult={analysisResult} />}
      </AnalysisCard>

      <AnalysisCard title="Recent Analyses">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px', flexWrap: 'wrap', marginBottom: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <label htmlFor="historyScopeSelect" style={{ fontSize: '0.9em', color: '#555' }}>Show:</label>
            <select
              id="historyScopeSelect"
              value={historyScope}
              onChange={e => {
                const nextScope = e.target.value;
                setHistoryScope(nextScope);
                setHistoryPage(1);
              }}
              style={{ padding: '4px', height: '30px' }}
            >
              <option value={HISTORY_SCOPE_ALL}>All tickers</option>
              <option value={HISTORY_SCOPE_CURRENT}>
                {hasHistoryTicker ? `Current ticker (${normalizedTickerForHistory})` : 'Current ticker'}
              </option>
            </select>
          </div>
          {historyScope === HISTORY_SCOPE_CURRENT && (
            <div style={{ fontSize: '0.85em', color: hasHistoryTicker ? '#555' : '#c0392b' }}>
              {hasHistoryTicker ? `Filtering on ${normalizedTickerForHistory}` : 'Enter a ticker above to filter by symbol.'}
            </div>
          )}
        </div>
        {historyLoading ? (
          <p style={{ margin: 0 }}>Loading history...</p>
        ) : (
          <>
            {historyError && (
              <p style={{ color: '#c0392b', margin: '0 0 10px 0' }}>{historyError}</p>
            )}
            {historyItems.length === 0 ? (
              <p style={{ margin: 0 }}>
                {historyScope === HISTORY_SCOPE_CURRENT
                  ? (hasHistoryTicker ? 'No history found for this ticker yet.' : 'Enter a ticker to view its recent analyses.')
                  : 'Run an analysis to build your personal history.'}
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {historyItems.map((entry) => (
                  <div
                    key={entry.id}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      border: '1px solid #e3e3e3',
                      borderRadius: '6px',
                      padding: '8px 12px',
                      background: '#fbfbfb',
                    }}
                  >
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <div style={{ fontWeight: 600 }}>
                        {entry.ticker}
                        {(entry.expiration_date || entry.expiration_date_raw) && (
                          <span style={{ fontWeight: 400, color: '#555', marginLeft: '6px' }}>
                            · Exp {formatExpiration(entry.expiration_date_raw || entry.expiration_date)}
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: '0.85em', color: '#555', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                        {entry.analysis_method && <span>{entry.analysis_method}</span>}
                        {entry.gpt_model && <span>Model: {entry.gpt_model}</span>}
                        {formatRiskFreeRate(entry.risk_free_rate) && (
                          <span>RF: {formatRiskFreeRate(entry.risk_free_rate)}</span>
                        )}
                        {formatTimestamp(entry.created_at) && (
                          <span>{formatTimestamp(entry.created_at)}</span>
                        )}
                        {entry.final_bias && (
                          <span>Bias: {entry.final_bias}</span>
                        )}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        type="button"
                        onClick={() => handleHistoryAnalyze(entry)}
                        style={{ padding: '6px 10px', cursor: 'pointer' }}
                      >
                        Analyze Again
                      </button>
                      <button
                        type="button"
                        onClick={() => handleRemoveHistoryItem(entry.id)}
                        style={{ padding: '6px 8px', cursor: 'pointer' }}
                        title="Remove from history"
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
            {historyItems.length > 0 && (
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginTop: '12px',
                  gap: '8px',
                  flexWrap: 'wrap',
                }}
              >
                <div style={{ fontSize: '0.85em', color: '#555' }}>
                  Showing {historyRangeStart}–{historyRangeEnd} of {historyTotal || historyRangeEnd}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <button
                    type="button"
                    onClick={() => setHistoryPage((prev) => Math.max(1, prev - 1))}
                    disabled={historyPage === 1 || historyLoading}
                    style={{ padding: '4px 10px', cursor: historyPage === 1 || historyLoading ? 'not-allowed' : 'pointer' }}
                  >
                    Previous
                  </button>
                  <span style={{ fontSize: '0.85em', color: '#555' }}>
                    Page {historyPage} of {totalHistoryPages}
                  </span>
                  <button
                    type="button"
                    onClick={() => setHistoryPage((prev) => prev + 1)}
                    disabled={!historyHasMore || historyLoading}
                    style={{ padding: '4px 10px', cursor: !historyHasMore || historyLoading ? 'not-allowed' : 'pointer' }}
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
            {historyItems.length > 0 && historyScope === HISTORY_SCOPE_CURRENT && hasHistoryTicker && (
              <div style={{ textAlign: 'right', marginTop: '12px' }}>
                <button type="button" onClick={handleClearHistory} style={{ padding: '4px 10px', cursor: 'pointer' }}>
                  Clear History
                </button>
              </div>
            )}
          </>
        )}
      </AnalysisCard>

      {/* Verdict History is accessible without running a new analysis */}
      <SavedVerdictsControls
        ticker={ticker}
        currentResult={analysisResult && Array.isArray(analysisResult) ? analysisResult[0] : null}
      />
    </div>
  );
}

export default AnalysisPage;
