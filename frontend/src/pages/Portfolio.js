import React, { useState, useEffect } from 'react';
import axios from 'axios';

const formatCurrency = (value) => {
  if (typeof value !== 'number' || isNaN(value)) {
    return '0.00';
  }
  return value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

const RecentOrders = ({ orders, isLoading }) => {
  if (isLoading) {
    return (
      <div style={{ border: '1px solid #ddd', borderRadius: '8px', padding: '16px', marginBottom: '24px', background: '#f8f9fa' }}>
        <h2 style={{ marginTop: 0, marginBottom: '16px' }}>Recent Orders</h2>
        <p>Loading recent orders...</p>
      </div>
    );
  }

  if (!orders || orders.length === 0) {
    return (
        <div style={{ border: '1px solid #ddd', borderRadius: '8px', padding: '16px', marginBottom: '24px', background: '#f8f9fa' }}>
            <h2 style={{ marginTop: 0, marginBottom: '16px' }}>Recent Orders</h2>
            <p>No recent orders found for this session.</p>
        </div>
    );
  }

  return (
    <div style={{ border: '1px solid #ddd', borderRadius: '8px', padding: '16px', marginBottom: '24px', background: '#f8f9fa' }}>
      <h2 style={{ marginTop: 0, marginBottom: '16px' }}>Recent Orders (Last 10)</h2>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9em' }}>
        <thead>
          <tr style={{ background: '#f0f0f0' }}>
            <th style={{ padding: '8px', border: '1px solid #ddd', textAlign: 'left' }}>Time</th>
            <th style={{ padding: '8px', border: '1px solid #ddd', textAlign: 'left' }}>Symbol</th>
            <th style={{ padding: '8px', border: '1px solid #ddd', textAlign: 'left' }}>Description</th>
            <th style={{ padding: '8px', border: '1px solid #ddd', textAlign: 'left' }}>Action</th>
            <th style={{ padding: '8px', border: '1px solid #ddd', textAlign: 'left' }}>Qty</th>
            <th style={{ padding: '8px', border: '1px solid #ddd', textAlign: 'left' }}>Status</th>
            <th style={{ padding: '8px', border: '1px solid #ddd', textAlign: 'left' }}>Avg Fill Price</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((order, index) => {
            const actionColor = order.action === 'BUY' ? 'green' : 'red';
            const statusColor = order.status === 'Filled' ? 'green' : (order.status === 'Cancelled' ? 'red' : 'orange');
            const time = order.lastFillTime ? new Date(order.lastFillTime).toLocaleString() : 'N/A';
            return (
              <tr key={index}>
                <td style={{ padding: '8px', border: '1px solid #ddd' }}>{time}</td>
                <td style={{ padding: '8px', border: '1px solid #ddd', fontWeight: 'bold' }}>{order.symbol}</td>
                <td style={{ padding: '8px', border: '1px solid #ddd' }}>{order.description || order.secType}</td>
                <td style={{ padding: '8px', border: '1px solid #ddd', color: actionColor, fontWeight: 'bold' }}>{order.action}</td>
                <td style={{ padding: '8px', border: '1px solid #ddd' }}>{order.quantity}</td>
                <td style={{ padding: '8px', border: '1px solid #ddd', color: statusColor, fontWeight: 'bold' }}>{order.status}</td>
                <td style={{ padding: '8px', border: '1px solid #ddd' }}>{order.avgFillPrice > 0 ? `$${formatCurrency(order.avgFillPrice)}` : 'N/A'}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

const PortfolioPage = () => {
  const [portfolioData, setPortfolioData] = useState(null);
  const [recentOrders, setRecentOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingOrders, setLoadingOrders] = useState(true);
  const [error, setError] = useState('');
  const [closingStatus, setClosingStatus] = useState({});

  useEffect(() => {
    const fetchOpenPositions = async () => {
      try {
        const response = await axios.get('/api/portfolio/open-positions');
        setPortfolioData(response.data);
      } catch (err) {
        setError(err.response?.data?.detail || 'Failed to fetch open positions.');
      } finally {
        setLoading(false);
      }
    };

    const fetchRecentOrders = async () => {
        try {
            const response = await axios.get('/api/portfolio/recent-orders');
            setRecentOrders(response.data);
        } catch (err) {
            console.error('Failed to fetch recent orders:', err.response?.data?.detail || err.message);
        } finally {
            setLoadingOrders(false);
        }
    };

    fetchOpenPositions();
    fetchRecentOrders();
  }, []);

  const handleCloseStrategy = async (symbol) => {
    setClosingStatus(prev => ({ ...prev, [symbol]: { inProgress: true } }));
    
    const legsToClose = portfolioData.positions.options[symbol].map(leg => ({
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

  const PortfolioSummary = ({ summary }) => {
    if (!summary) return null;

    const pnlColor = summary.unrealized_pnl >= 0 ? 'green' : 'red';

    return (
        <div style={{ border: '1px solid #ddd', borderRadius: '8px', padding: '20px', marginBottom: '24px', background: '#f8f9fa' }}>
            <h2 style={{ marginTop: 0, marginBottom: '16px' }}>Portfolio Overview</h2>
            <div style={{ display: 'flex', justifyContent: 'space-around', fontSize: '1.2em' }}>
                <div>
                    <span style={{ color: '#666', marginRight: '10px' }}>Total Market Value:</span>
                    <strong>${formatCurrency(summary.market_value)}</strong>
                </div>
                <div>
                    <span style={{ color: '#666', marginRight: '10px' }}>Unrealized P&L:</span>
                    <strong style={{ color: pnlColor }}>${formatCurrency(summary.unrealized_pnl)}</strong>
                </div>
            </div>
        </div>
    );
  };

  const StrategyCard = ({ symbol, legs }) => {
    const status = closingStatus[symbol];
    const isClosing = status?.inProgress;
    const legTotal = legs.reduce((acc, leg) => acc + leg.position, 0);
    const strategyUnrealizedPNL = legs.reduce((acc, leg) => acc + (leg.unrealizedPNL || 0), 0);
    const pnlColor = strategyUnrealizedPNL >= 0 ? 'green' : 'red';

    return (
      <div style={{ border: '1px solid #ddd', borderRadius: '8px', padding: '16px', marginBottom: '16px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
            <div>
                <h3 style={{ marginTop: 0, marginBottom: '5px' }}>{symbol} <span style={{fontSize: '0.8em', color: '#666'}}>({legs.length} Legs)</span></h3>
                <span style={{fontSize: '0.9em'}}>Unrealized P/L: <strong style={{color: pnlColor}}>${formatCurrency(strategyUnrealizedPNL)}</strong></span>
            </div>
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
                    <th style={{padding: '8px', border: '1px solid #ddd', textAlign: 'left'}}>Unrealized P/L</th>
                </tr>
            </thead>
            <tbody>
                {legs.map((leg, index) => {
                    const legPnlColor = leg.unrealizedPNL >= 0 ? 'green' : 'red';
                    return (
                        <tr key={index}>
                            <td style={{padding: '8px', border: '1px solid #ddd', color: leg.position > 0 ? 'green' : 'red', fontWeight: 'bold'}}>{leg.position > 0 ? `+${leg.position}` : leg.position}</td>
                            <td style={{padding: '8px', border: '1px solid #ddd'}}>{leg.right === 'C' ? 'Call' : 'Put'}</td>
                            <td style={{padding: '8px', border: '1px solid #ddd'}}>${leg.strike.toFixed(2)}</td>
                            <td style={{padding: '8px', border: '1px solid #ddd'}}>{leg.expiry}</td>
                            <td style={{padding: '8px', border: '1px solid #ddd'}}>${formatCurrency(leg.position !== 0 ? (leg.avgCost / (leg.position * 100)) : 0)}</td>
                            <td style={{padding: '8px', border: '1px solid #ddd', color: legPnlColor}}>${formatCurrency(leg.unrealizedPNL)}</td>
                        </tr>
                    );
                })}
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

  const StockPositions = ({ stocks }) => {
    if (!stocks || stocks.length === 0) {
      return null;
    }

    return (
      <div style={{ marginTop: '24px' }}>
        <h2>Stock Positions</h2>
        <table style={{ width: '100%', marginTop: '10px', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: '#f8f9fa' }}>
              <th style={{ padding: '8px', border: '1px solid #ddd', textAlign: 'left' }}>Symbol</th>
              <th style={{ padding: '8px', border: '1px solid #ddd', textAlign: 'left' }}>Quantity</th>
              <th style={{ padding: '8px', border: '1px solid #ddd', textAlign: 'left' }}>Avg Cost/Share</th>
            </tr>
          </thead>
          <tbody>
            {stocks.map((stock, index) => {
              return (
                <tr key={index}>
                  <td style={{ padding: '8px', border: '1px solid #ddd', fontWeight: 'bold' }}>{stock.symbol}</td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>{stock.position}</td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>${formatCurrency(stock.position !== 0 ? (stock.avgCost / stock.position) : 0)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  };

  if (loading) return <p>Loading open positions from broker...</p>;
  if (error) return <p style={{ color: 'red' }}>{error}</p>;
  
  const positions = portfolioData ? portfolioData.positions : null;

  if (!portfolioData || !positions || (Object.keys(positions.options || {}).length === 0 && (!positions.stocks || positions.stocks.length === 0))) {
      return <p>No open positions found in the account.</p>;
  }

  return (
    <div>
      <PortfolioSummary summary={portfolioData.summary} />
      <RecentOrders orders={recentOrders} isLoading={loadingOrders} />

      {Object.keys(positions.options || {}).length > 0 && (
        <div style={{marginTop: '24px'}}>
            <h2>Open Option Strategies</h2>
            <p>This page shows all open option positions in your account, grouped by underlying ticker.</p>
            {Object.entries(positions.options).map(([symbol, legs]) => (
                <StrategyCard key={symbol} symbol={symbol} legs={legs} />
            ))}
        </div>
      )}
      <StockPositions stocks={positions.stocks} />
    </div>
  );
};

export default PortfolioPage;
