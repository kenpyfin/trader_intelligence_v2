import React, { useState, useEffect } from 'react';
import axios from 'axios';

const PortfolioPage = () => {
  const [strategies, setStrategies] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [closingStatus, setClosingStatus] = useState({});

  useEffect(() => {
    const fetchOpenStrategies = async () => {
      try {
        const response = await axios.get('/api/portfolio/open-strategies');
        setStrategies(response.data);
      } catch (err) {
        setError(err.response?.data?.detail || 'Failed to fetch open positions.');
      } finally {
        setLoading(false);
      }
    };
    fetchOpenStrategies();
  }, []);

  const handleCloseStrategy = async (symbol) => {
    setClosingStatus(prev => ({ ...prev, [symbol]: { inProgress: true } }));
    
    const legsToClose = strategies[symbol].map(leg => ({
        symbol: leg.symbol,
        secType: 'OPT',
        expiry: leg.expiry,
        strike: leg.strike,
        right: leg.right,
        exchange: leg.exchange,
        currency: leg.currency,
        quantity: leg.position,
    }));

    try {
        const response = await axios.post('/api/portfolio/close-strategy', { legs: legsToClose });
        setClosingStatus(prev => ({ ...prev, [symbol]: { inProgress: false, data: response.data } }));
    } catch (err) {
        const errorMessage = err.response?.data?.detail || 'Failed to submit closing order.';
        setClosingStatus(prev => ({ ...prev, [symbol]: { inProgress: false, error: errorMessage } }));
    }
  };

  const StrategyCard = ({ symbol, legs }) => {
    const status = closingStatus[symbol];
    const isClosing = status?.inProgress;
    const legTotal = legs.reduce((acc, leg) => acc + leg.position, 0);

    return (
      <div style={{ border: '1px solid #ddd', borderRadius: '8px', padding: '16px', marginBottom: '16px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
            <h3 style={{ marginTop: 0 }}>{symbol} <span style={{fontSize: '0.8em', color: '#666'}}>({legs.length} Legs)</span></h3>
            <button 
                onClick={() => handleCloseStrategy(symbol)} 
                disabled={isClosing}
                style={{
                    backgroundColor: legTotal === 0 ? '#ccc' : '#dc3545', // Grey out if position is flat
                    color: 'white',
                    border: 'none',
                    padding: '8px 16px',
                    borderRadius: '5px',
                    cursor: 'pointer'
                }}
            >
                {isClosing ? 'Closing...' : 'Close Strategy'}
            </button>
        </div>
        
        <table style={{ width: '100%', marginTop: '10px', borderCollapse: 'collapse' }}>
            <thead>
                <tr style={{background: '#f8f9fa'}}>
                    <th style={{padding: '8px', border: '1px solid #ddd', textAlign: 'left'}}>Qty</th>
                    <th style={{padding: '8px', border: '1px solid #ddd', textAlign: 'left'}}>Type</th>
                    <th style={{padding: '8px', border: '1px solid #ddd', textAlign: 'left'}}>Strike</th>
                    <th style={{padding: '8px', border: '1px solid #ddd', textAlign: 'left'}}>Expiry</th>
                    <th style={{padding: '8px', border: '1px solid #ddd', textAlign: 'left'}}>Avg Cost</th>
                </tr>
            </thead>
            <tbody>
                {legs.map((leg, index) => (
                    <tr key={index}>
                        <td style={{padding: '8px', border: '1px solid #ddd', color: leg.position > 0 ? 'green' : 'red', fontWeight: 'bold'}}>{leg.position > 0 ? `+${leg.position}` : leg.position}</td>
                        <td style={{padding: '8px', border: '1px solid #ddd'}}>{leg.right === 'C' ? 'Call' : 'Put'}</td>
                        <td style={{padding: '8px', border: '1px solid #ddd'}}>${leg.strike.toFixed(2)}</td>
                        <td style={{padding: '8px', border: '1px solid #ddd'}}>{leg.expiry}</td>
                        <td style={{padding: '8px', border: '1px solid #ddd'}}>${(leg.avgCost / (leg.position * 100)).toFixed(2)}</td>
                    </tr>
                ))}
            </tbody>
        </table>
        {status?.data && (
            <div style={{marginTop: '10px', padding: '10px', background: '#e8f5e9', borderRadius: '5px'}}>
                <strong>Closing Order Status:</strong> {status.data.status}
                <ul>
                    {status.data.trades.map((trade, i) => (
                        <li key={i}>{trade.leg}: {trade.order_status} (Filled: {trade.filled})</li>
                    ))}
                </ul>
            </div>
        )}
        {status?.error && (
            <div style={{marginTop: '10px', padding: '10px', background: '#f8d7da', borderRadius: '5px', color: '#721c24'}}>
                <strong>Error:</strong> {status.error}
            </div>
        )}
      </div>
    );
  };

  if (loading) return <p>Loading open positions from broker...</p>;
  if (error) return <p style={{ color: 'red' }}>{error}</p>;
  if (Object.keys(strategies).length === 0) return <p>No open option positions found in the account.</p>;

  return (
    <div>
      <h2>Open Option Strategies</h2>
      <p>This page shows all open option positions in your account, grouped by underlying ticker.</p>
      {Object.entries(strategies).map(([symbol, legs]) => (
        <StrategyCard key={symbol} symbol={symbol} legs={legs} />
      ))}
    </div>
  );
};

export default PortfolioPage;
