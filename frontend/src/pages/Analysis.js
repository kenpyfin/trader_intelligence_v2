import React, { useState, useEffect } from 'react';
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
    xaxis: { rangeslider: { visible: false } },
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

const StrategyOrder = ({ strategy, ticker, expirationDate, gptVerdict }) => {
    const [isOrdering, setIsOrdering] = useState(false);
    const [orderStatus, setOrderStatus] = useState(null);
    const [showGptInsights, setShowGptInsights] = useState(false);

    const handleExecute = async () => {
        setIsOrdering(true);
        setOrderStatus(null);
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
                    sources: gptVerdict.sources || []
                } : null
            };
            const response = await axios.post('/api/orders/strategy', payload);
            setOrderStatus(response.data);
        } catch (err) {
            setOrderStatus({ status: 'error', message: err.response?.data?.detail || 'Order failed.' });
        } finally {
            setIsOrdering(false);
        }
    };

    if (!strategy || !strategy.name || strategy.name === 'None' || strategy.legs.length === 0) {
        return null;
    }

    const legDescriptions = strategy.legs.map((leg, i) => (
      <li key={i}>{leg.action} {leg.strike.toFixed(2)} {leg.right}</li>
    ));

    return (
        <AnalysisCard title="Execute Recommended Strategy">
            <p><strong>Strategy:</strong> {strategy.name}</p>
            <ul style={{ margin: '5px 0', paddingLeft: '20px' }}>
                {legDescriptions}
            </ul>
            
            {/* GPT Insights Section */}
            {gptVerdict && (
                <div style={{ marginBottom: '15px', padding: '10px', border: '1px solid #e0e0e0', borderRadius: '5px', backgroundColor: '#f8f9fa' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                        <strong>🤖 AI Trading Insights</strong>
                        <button 
                            onClick={() => setShowGptInsights(!showGptInsights)}
                            style={{ padding: '2px 8px', fontSize: '12px', cursor: 'pointer' }}
                        >
                            {showGptInsights ? 'Hide' : 'Show'} Details
                        </button>
                    </div>
                    
                    <div><strong>AI Bias:</strong> <span style={{ color: gptVerdict.final_bias?.includes('Bull') ? 'green' : gptVerdict.final_bias?.includes('Bear') ? 'red' : 'gray' }}>{gptVerdict.final_bias}</span></div>
                    
                    {showGptInsights && (
                        <div style={{ marginTop: '10px' }}>
                            {gptVerdict.execution_recommendations && (
                                <div style={{ marginBottom: '12px' }}>
                                    <strong>🎯 Execution Strategy:</strong>
                                    <div style={{ marginLeft: '10px', fontSize: '14px' }}>
                                        <div style={{ marginBottom: '6px' }}>
                                            <strong>Primary:</strong> {gptVerdict.execution_recommendations.primary_strategy?.type} 
                                            <span style={{ color: gptVerdict.execution_recommendations.primary_strategy?.confidence === 'High' ? 'green' : gptVerdict.execution_recommendations.primary_strategy?.confidence === 'Medium' ? 'orange' : 'red', marginLeft: '5px' }}>
                                                ({gptVerdict.execution_recommendations.primary_strategy?.confidence})
                                            </span>
                                        </div>
                                        <div style={{ fontSize: '13px', color: '#666', marginBottom: '6px' }}>
                                            {gptVerdict.execution_recommendations.primary_strategy?.description}
                                        </div>
                                        {gptVerdict.execution_recommendations.position_sizing && (
                                            <div style={{ fontSize: '13px', marginBottom: '6px' }}>
                                                <strong>Position Size:</strong> {gptVerdict.execution_recommendations.position_sizing.suggested_allocation} 
                                                <span style={{ color: gptVerdict.execution_recommendations.position_sizing.risk_level === 'Conservative' ? 'green' : gptVerdict.execution_recommendations.position_sizing.risk_level === 'Moderate' ? 'orange' : 'red', marginLeft: '5px' }}>
                                                    ({gptVerdict.execution_recommendations.position_sizing.risk_level})
                                                </span>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}
                            
                            {gptVerdict.actionable_ideas?.length > 0 && (
                                <div style={{ marginBottom: '8px' }}>
                                    <strong>💡 Key Ideas:</strong>
                                    <ul style={{ margin: '5px 0', paddingLeft: '20px', fontSize: '14px' }}>
                                        {gptVerdict.actionable_ideas.slice(0, 3).map((idea, i) => (
                                            <li key={i}>{idea}</li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                            
                            {gptVerdict.risk_factors?.length > 0 && (
                                <div style={{ marginBottom: '8px' }}>
                                    <strong>⚠️ Risk Factors:</strong>
                                    <ul style={{ margin: '5px 0', paddingLeft: '20px', fontSize: '14px' }}>
                                        {gptVerdict.risk_factors.slice(0, 3).map((risk, i) => (
                                            <li key={i}>{risk}</li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}
            
            {/* Enhanced Execution Options */}
            {gptVerdict?.execution_recommendations && (
                <div style={{ marginTop: '15px', padding: '12px', border: '1px solid #dee2e6', borderRadius: '6px', backgroundColor: '#f8f9fa' }}>
                    <h4 style={{ margin: '0 0 10px 0', fontSize: '16px' }}>🎯 AI-Powered Execution Guidance</h4>
                    
                    {/* Entry/Exit Conditions */}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '10px' }}>
                        {gptVerdict.execution_recommendations.entry_conditions?.length > 0 && (
                            <div>
                                <strong style={{ fontSize: '14px' }}>📈 Entry Signals:</strong>
                                <ul style={{ margin: '5px 0', paddingLeft: '15px', fontSize: '13px' }}>
                                    {gptVerdict.execution_recommendations.entry_conditions.slice(0, 3).map((condition, i) => (
                                        <li key={i}>{condition}</li>
                                    ))}
                                </ul>
                            </div>
                        )}
                        
                        {gptVerdict.execution_recommendations.exit_conditions?.length > 0 && (
                            <div>
                                <strong style={{ fontSize: '14px' }}>📉 Exit Signals:</strong>
                                <ul style={{ margin: '5px 0', paddingLeft: '15px', fontSize: '13px' }}>
                                    {gptVerdict.execution_recommendations.exit_conditions.slice(0, 3).map((condition, i) => (
                                        <li key={i}>{condition}</li>
                                    ))}
                                </ul>
                            </div>
                        )}
                    </div>
                    
                    {/* Risk Management */}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '10px' }}>
                        {gptVerdict.execution_recommendations.stop_loss_guidance && (
                            <div style={{ fontSize: '13px' }}>
                                <strong>🛡️ Stop Loss:</strong> {gptVerdict.execution_recommendations.stop_loss_guidance}
                            </div>
                        )}
                        
                        {gptVerdict.execution_recommendations.profit_target_guidance && (
                            <div style={{ fontSize: '13px' }}>
                                <strong>🎯 Profit Target:</strong> {gptVerdict.execution_recommendations.profit_target_guidance}
                            </div>
                        )}
                    </div>
                    
                    {/* Alternative Strategies */}
                    {gptVerdict.execution_recommendations.alternative_strategies?.length > 0 && (
                        <div style={{ marginBottom: '10px' }}>
                            <strong style={{ fontSize: '14px' }}>🔄 Alternative Strategies:</strong>
                            <div style={{ fontSize: '13px', marginTop: '5px' }}>
                                {gptVerdict.execution_recommendations.alternative_strategies.slice(0, 2).map((alt, i) => (
                                    <div key={i} style={{ marginBottom: '4px' }}>
                                        • {alt.type} 
                                        <span style={{ color: alt.confidence === 'High' ? 'green' : alt.confidence === 'Medium' ? 'orange' : 'red', marginLeft: '5px' }}>
                                            ({alt.confidence})
                                        </span>
                                        - {alt.description}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}
            
            {/* TODO: Add quantity input here */}
            <button onClick={handleExecute} disabled={isOrdering} style={{ padding: '5px 15px', cursor: 'pointer' }}>
                {isOrdering ? 'Placing Order...' : `Execute ${strategy.name}${gptVerdict ? ' (with AI insights)' : ''}`}
            </button>
            {orderStatus && (
                <div style={{ marginTop: '10px', padding: '10px', borderRadius: '5px', background: orderStatus.status === 'error' ? '#ffdddd' : '#e8f5e9' }}>
                    <p><strong>Status:</strong> {orderStatus.message}</p>
                    {orderStatus.status === 'success' && <p>Order Status from Broker: {orderStatus.order_status}</p>}
                </div>
            )}
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
        strategy={data.recommended_strategy} 
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

      <SavedVerdictsControls currentResult={analysisResult[0]} />
    </div>
  );
};

const SavedVerdictsControls = ({ currentResult }) => {
  const [saving, setSaving] = useState(false);
  const [saveLabel, setSaveLabel] = useState('');
  const [saveMsg, setSaveMsg] = useState('');

  const [listLoading, setListLoading] = useState(false);
  const [savedList, setSavedList] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [selectedDoc, setSelectedDoc] = useState(null);

  const ticker = currentResult?.ticker || '';

  const loadList = async () => {
    if (!ticker) return;
    setListLoading(true);
    try {
      const resp = await axios.get(`/api/analysis/verdicts/${encodeURIComponent(ticker)}`);
      setSavedList(resp.data?.items || []);
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
    if (ticker) loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker]);

  const handleSave = async () => {
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
    <AnalysisCard title="Saved Verdicts">
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
        <div>
          <h4>Save Current Verdict</h4>
          <div style={{ marginBottom: '8px' }}>
            <label>Label (optional):</label><br/>
            <input type="text" value={saveLabel} onChange={e => setSaveLabel(e.target.value)} placeholder="e.g., Before Earnings" style={{ width: '95%' }} />
          </div>
          <button onClick={handleSave} disabled={saving || !ticker} style={{ padding: '6px 12px' }}>
            {saving ? 'Saving...' : 'Save Verdict'}
          </button>
          {saveMsg && <div style={{ marginTop: '8px', fontSize: '0.9em' }}>{saveMsg}</div>}
        </div>

        <div>
          <h4>Load Previous Verdict</h4>
          {listLoading ? (
            <p>Loading saved verdicts...</p>
          ) : (
            <select value={selectedId} onChange={e => handleSelect(e.target.value)} style={{ width: '100%', padding: '6px' }}>
              <option value="">Select a saved verdict...</option>
              {savedList.map(item => (
                <option key={item.id} value={item.id}>
                  {`${item.created_at?.slice(0, 19).replace('T',' ')} | ${item.label || ''} | ${item.final_bias || ''}`}
                </option>
              ))}
            </select>
          )}
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
    if (!selectedExpiration) {
      setError('Please fetch and select an expiration date.');
      return;
    }
    setLoading(true);
    setError('');
    setAnalysisResult(null);
    try {
      const response = await axios.post('/api/analysis/stock', {
        ticker: ticker,
        expiration_date: selectedExpiration, // Send as YYYYMMDD
        risk_free_rate: riskFreeRate,
        analysis_method: analysisMethod,
        gpt_model: selectedModel, // Include selected GPT model
      });
      const result = response.data;
      // The ResultsDisplay component expects an array. If the API returns a single object,
      // wrap it in an array for consistent handling.
      if (result && typeof result === 'object' && !Array.isArray(result)) {
        setAnalysisResult([result]);
      } else {
        setAnalysisResult(result);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'An unexpected error occurred.');
    } finally {
      setLoading(false);
    }
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
    </div>
  );
}

export default AnalysisPage;
