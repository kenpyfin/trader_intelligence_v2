import React, { useState } from 'react';
import axios from 'axios';
import Plot from 'react-plotly.js';

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

const ResultsDisplay = ({ data }) => {
  const biasColor = data.final_bias.includes('Bullish') ? 'green' : data.final_bias.includes('Bearish') ? 'red' : 'orange';

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
    <div style={{ marginTop: '20px' }}>
      <h2>Analysis for {data.ticker.toUpperCase()}</h2>
      <p>Current Price: <strong>${data.S_current.toFixed(2)}</strong></p>
      
      <AnalysisCard title="Holistic Conclusion & Strategy">
        <h4 style={{ color: biasColor }}>Final Bias: {data.final_bias}</h4>
        <div dangerouslySetInnerHTML={{ __html: data.final_conclusion_html }} />
      </AnalysisCard>
      
      <AnalysisCard title="1. Price Trend & Candlestick Analysis">
        {data.candlestick_analysis.plot_data ? 
          <CandlestickChart plotData={data.candlestick_analysis.plot_data} ticker={data.ticker} /> :
          <p>{data.candlestick_analysis.error || "No chart data."}</p>
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


function App() {
  const [ticker, setTicker] = useState('SPY');
  const [expirationDate, setExpirationDate] = useState(new Date(new Date().setDate(new Date().getDate() + 30)).toISOString().split('T')[0]);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleAnalyze = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setAnalysisResult(null);
    try {
      const response = await axios.post('/api/analyze/stock', {
        ticker: ticker,
        expiration_date: expirationDate,
      });
      setAnalysisResult(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'An unexpected error occurred.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '20px', fontFamily: 'sans-serif', maxWidth: '900px', margin: 'auto' }}>
      <h1>Trader Intelligence</h1>
      
      <form onSubmit={handleAnalyze} style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
        <div>
          <label>Ticker: </label>
          <input type="text" value={ticker} onChange={(e) => setTicker(e.target.value)} required />
        </div>
        <div>
          <label>Expiration Date: </label>
          <input type="date" value={expirationDate} onChange={(e) => setExpirationDate(e.target.value)} required />
        </div>
        <button type="submit" disabled={loading} style={{ padding: '5px 10px' }}>
          {loading ? 'Analyzing...' : 'Analyze Stock'}
        </button>
      </form>

      {error && <p style={{ color: 'red', border: '1px solid red', padding: '10px', borderRadius: '5px' }}><strong>Error:</strong> {error}</p>}
      {loading && <p>Loading analysis...</p>}
      {analysisResult && <ResultsDisplay data={analysisResult} />}
    </div>
  );
}

export default App;
