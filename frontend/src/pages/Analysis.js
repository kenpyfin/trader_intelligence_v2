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

  // Map data arrays to named properties for Plotly
  const trace = {
    x: dates,
    close: data.map(row => row[findCol('Close')]),
    high: data.map(row => row[findCol('High')]),
    low: data.map(row => row[findCol('Low')]),
    open: data.map(row => row[findCol('Open')]),
    type: 'candlestick',
    name: ticker,
  };
  
  const layout = {
    title: `${ticker} Price Chart`,
    xaxis: { rangeslider: { visible: false } },
    yaxis: { title: 'Price' },
    margin: { t: 40, b: 40, l: 50, r: 20 },
    height: 400,
  };

  return <Plot data={[trace]} layout={layout} style={{ width: '100%' }} />;
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

const StrategyOrder = ({ strategy, ticker, expirationDate }) => {
    const [isOrdering, setIsOrdering] = useState(false);
    const [orderStatus, setOrderStatus] = useState(null);

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
            {/* TODO: Add quantity input here */}
            <button onClick={handleExecute} disabled={isOrdering} style={{ padding: '5px 15px', cursor: 'pointer' }}>
                {isOrdering ? 'Placing Order...' : `Execute ${strategy.name}`}
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

const AnalysisDetails = ({ data }) => {
  const finalBias = data.final_bias || '';
  const biasColor = finalBias.includes('Bullish') ? 'green' : finalBias.includes('Bearish') ? 'red' : 'orange';

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
      <AnalysisCard title={`Holistic Conclusion & Strategy (DTE: ${data.dte} days)`}>
        <h4 style={{ color: biasColor }}>Final Bias: {finalBias}</h4>
        <div dangerouslySetInnerHTML={{ __html: data.final_conclusion_html }} />
      </AnalysisCard>
      
      <StrategyOrder strategy={data.recommended_strategy} ticker={data.ticker} expirationDate={data.expiration_date} />
      
      <AnalysisCard title="1. Price Trend & Candlestick Analysis">
        {data.candlestick_analysis?.plot_data ? 
          <CandlestickChart plotData={data.candlestick_analysis.plot_data} ticker={data.ticker} /> :
          <p>{data.candlestick_analysis?.error || "No chart data."}</p>
        }
        <p><strong>Primary Trend:</strong> {data.candlestick_analysis?.context?.primary_trend}</p>
        <p><strong>Secondary Trend:</strong> {data.candlestick_analysis?.context?.secondary_trend}</p>
        
        {data.candlestick_analysis?.patterns && data.candlestick_analysis.patterns.length > 0 ? (
          <div style={{marginTop: '15px'}}>
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
          <p style={{marginTop: '15px'}}><strong>Patterns:</strong> No significant candlestick patterns identified in the last few periods.</p>
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
    </div>
  );
};

const AnalysisPage = () => {
  const [ticker, setTicker] = useStickyState('SPY', 'ticker');
  const [riskFreeRate, setRiskFreeRate] = useStickyState(0.045, 'riskFreeRate');
  const [expirations, setExpirations] = useState([]);
  const [selectedExpiration, setSelectedExpiration] = useState('');
  const [fetchingExpirations, setFetchingExpirations] = useState(false);
  const [analysisResult, setAnalysisResult] = useStickyState(null, 'analysisResult');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

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
      });
      setAnalysisResult(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'An unexpected error occurred.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <MacroInsights onRateCalculated={setRiskFreeRate} />
      
      <AnalysisCard title="Stock and Option Analysis">
        <form onSubmit={handleAnalyze} style={{ marginBottom: '20px' }}>
          <div style={{ display: 'flex', gap: '15px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
              <div>
                <label>Ticker:</label><br/>
                <input type="text" value={ticker} onChange={(e) => setTicker(e.target.value)} required />
              </div>

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
