import React, { useState } from 'react';
import axios from 'axios';

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
    <div style={{ padding: '20px', fontFamily: 'sans-serif' }}>
      <h1>Trader Intelligence</h1>
      <p>Phase 1: Core Logic Migration & API Validation</p>
      
      <form onSubmit={handleAnalyze}>
        <div>
          <label>Ticker:</label>
          <input type="text" value={ticker} onChange={(e) => setTicker(e.target.value)} required />
        </div>
        <div style={{ marginTop: '10px' }}>
          <label>Expiration Date:</label>
          <input type="date" value={expirationDate} onChange={(e) => setExpirationDate(e.target.value)} required />
        </div>
        <button type="submit" disabled={loading} style={{ marginTop: '10px' }}>
          {loading ? 'Analyzing...' : 'Analyze Stock'}
        </button>
      </form>

      {error && <p style={{ color: 'red' }}>Error: {error}</p>}

      {analysisResult && (
        <div style={{ marginTop: '20px' }}>
          <h2>Analysis Results</h2>
          <pre style={{ background: '#f4f4f4', padding: '10px', borderRadius: '5px', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
            {JSON.stringify(analysisResult, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

export default App;
