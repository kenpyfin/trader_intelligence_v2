import React, { useState, useEffect } from 'react';
import axios from 'axios';

const isFiniteNumber = (value) => typeof value === 'number' && Number.isFinite(value);

const formatCurrency = (value, fallback = '--') => {
  if (!isFiniteNumber(value)) {
    return fallback;
  }
  const formatted = value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `$${formatted}`;
};

const getPositionUnrealizedPnl = (position) => {
  const candidates = [
    position?.unrealizedPNL,
    position?.unrealizedPnl,
    position?.unrealized_pnl,
    position?.unrealizedPnL,
  ];
  return candidates.find((value) => isFiniteNumber(value));
};

const getPositionMarketPrice = (position, contractMultiplier = 1) => {
  const explicitCandidates = [
    position?.marketPrice,
    position?.market_price,
    position?.lastPrice,
    position?.last_price,
    position?.currentPrice,
    position?.current_price,
  ];
  const explicitPrice = explicitCandidates.find((value) => isFiniteNumber(value));
  if (isFiniteNumber(explicitPrice)) {
    return explicitPrice;
  }

  const marketValue = isFiniteNumber(position?.marketValue) ? position.marketValue : null;
  const quantity = isFiniteNumber(position?.position) ? position.position : null;
  if (!isFiniteNumber(marketValue) || !isFiniteNumber(quantity) || quantity === 0) {
    return null;
  }

  return marketValue / (quantity * contractMultiplier);
};

const formatDateTime = (value) => {
  if (!value) return 'N/A';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
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
                <td style={{ padding: '8px', border: '1px solid #ddd' }}>
                  {isFiniteNumber(order.avgFillPrice) && order.avgFillPrice > 0 ? formatCurrency(order.avgFillPrice) : 'N/A'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

const TrackedOrders = ({ orders, isLoading }) => {
  if (isLoading) {
    return (
      <div style={{ border: '1px solid #ddd', borderRadius: '8px', padding: '16px', marginBottom: '24px', background: '#f8f9fa' }}>
        <h2 style={{ marginTop: 0, marginBottom: '16px' }}>One-Button Execution History</h2>
        <p>Loading execution history...</p>
      </div>
    );
  }

  if (!orders || orders.length === 0) {
    return (
      <div style={{ border: '1px solid #ddd', borderRadius: '8px', padding: '16px', marginBottom: '24px', background: '#f8f9fa' }}>
        <h2 style={{ marginTop: 0, marginBottom: '16px' }}>One-Button Execution History</h2>
        <p>No tracked executions yet. Run a strategy from the Analysis page to populate this list.</p>
      </div>
    );
  }

  return (
    <div style={{ border: '1px solid #ddd', borderRadius: '8px', padding: '16px', marginBottom: '24px', background: '#f8f9fa' }}>
      <h2 style={{ marginTop: 0, marginBottom: '16px' }}>One-Button Execution History</h2>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {orders.map((order) => {
          const guidance = order.gpt_guidance || {};
          const recs = guidance.execution_recommendations || {};
          const entrySignals = Array.isArray(recs.entry_conditions) ? recs.entry_conditions : [];
          const exitSignals = Array.isArray(recs.exit_conditions) ? recs.exit_conditions : [];
          const ideas = Array.isArray(guidance.actionable_ideas) ? guidance.actionable_ideas : [];
          const risks = Array.isArray(guidance.risk_factors) ? guidance.risk_factors : [];
          const alternatives = Array.isArray(recs.alternative_strategies) ? recs.alternative_strategies : [];
          const legs = Array.isArray(order.legs) ? order.legs : [];
          const statusColor = order.status && order.status.toLowerCase().includes('filled') ? 'green' : '#555';

          return (
            <div key={order.id} style={{ border: '1px solid #e0e0e0', borderRadius: '6px', padding: '12px', background: '#fff', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '10px', flexWrap: 'wrap' }}>
                <div>
                  <div style={{ fontSize: '1.05em', fontWeight: 600 }}>
                    {order.ticker} • Exp {order.expiration_date || 'N/A'}
                  </div>
                  <div style={{ fontSize: '0.9em', color: '#666' }}>
                    Placed {formatDateTime(order.placed_at)} • Size {order.size} • {order.is_credit_spread ? 'Credit Spread' : 'Strategy'}
                  </div>
                </div>
                <div style={{ fontSize: '0.9em', fontWeight: 600, color: statusColor }}>
                  Status: {order.status || 'Submitted'}
                </div>
              </div>

              {legs.length > 0 && (
                <div style={{ marginTop: '10px', fontSize: '0.9em', color: '#444' }}>
                  <strong>Legs:</strong>
                  <ul style={{ margin: '6px 0 0 18px', padding: 0 }}>
                    {legs.map((leg, idx) => (
                      <li key={idx}>{leg.action} {leg.quantity} × {leg.right} {parseFloat(leg.strike).toFixed(2)}</li>
                    ))}
                  </ul>
                </div>
              )}

              {guidance.final_bias && (
                <div style={{ marginTop: '10px', fontWeight: 600 }}>
                  AI Bias: <span style={{ color: guidance.final_bias.includes('Bull') ? 'green' : guidance.final_bias.includes('Bear') ? 'red' : '#555' }}>{guidance.final_bias}</span>
                </div>
              )}

              {(entrySignals.length > 0 || exitSignals.length > 0 || recs.stop_loss_guidance || recs.profit_target_guidance || alternatives.length > 0) && (
                <div style={{ marginTop: '12px', background: '#f6f9ff', borderRadius: '6px', padding: '12px' }}>
                  <div style={{ fontWeight: 600, marginBottom: '8px' }}>🎯 AI-Powered Execution Guidance</div>
                  {entrySignals.length > 0 && (
                    <div style={{ marginBottom: '8px' }}>
                      <strong>📈 Entry Signals:</strong>
                      <ul style={{ margin: '4px 0 0 18px', padding: 0 }}>
                        {entrySignals.map((signal, idx) => (
                          <li key={idx}>{signal}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {exitSignals.length > 0 && (
                    <div style={{ marginBottom: '8px' }}>
                      <strong>📉 Exit Signals:</strong>
                      <ul style={{ margin: '4px 0 0 18px', padding: 0 }}>
                        {exitSignals.map((signal, idx) => (
                          <li key={idx}>{signal}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {recs.stop_loss_guidance && (
                    <div style={{ marginBottom: '6px' }}>
                      <strong>🛡️ Stop Loss:</strong> {recs.stop_loss_guidance}
                    </div>
                  )}
                  {recs.profit_target_guidance && (
                    <div style={{ marginBottom: '6px' }}>
                      <strong>🎯 Profit Target:</strong> {recs.profit_target_guidance}
                    </div>
                  )}
                  {alternatives.length > 0 && (
                    <div>
                      <strong>🔄 Alternative Strategies:</strong>
                      <ul style={{ margin: '4px 0 0 18px', padding: 0 }}>
                        {alternatives.map((alt, idx) => (
                          <li key={idx}>
                            {alt.type || 'Strategy'}
                            {alt.confidence && (
                              <span style={{ marginLeft: '5px', color: alt.confidence === 'High' ? 'green' : alt.confidence === 'Medium' ? 'orange' : '#c0392b' }}>
                                ({alt.confidence})
                              </span>
                            )}
                            {alt.description ? ` - ${alt.description}` : ''}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {(ideas.length > 0 || risks.length > 0) && (
                <div style={{ marginTop: '12px', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px' }}>
                  {ideas.length > 0 && (
                    <div style={{ background: '#f8fdf6', borderRadius: '6px', padding: '10px' }}>
                      <strong>💡 Key Ideas</strong>
                      <ul style={{ margin: '6px 0 0 18px', padding: 0 }}>
                        {ideas.map((idea, idx) => (
                          <li key={idx}>{idea}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {risks.length > 0 && (
                    <div style={{ background: '#fff6f6', borderRadius: '6px', padding: '10px' }}>
                      <strong>⚠️ Risk Factors</strong>
                      <ul style={{ margin: '6px 0 0 18px', padding: 0 }}>
                        {risks.map((risk, idx) => (
                          <li key={idx}>{risk}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

const PortfolioPage = () => {
  const [portfolioData, setPortfolioData] = useState(null);
  const [recentOrders, setRecentOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingOrders, setLoadingOrders] = useState(true);
  const [trackedOrders, setTrackedOrders] = useState([]);
  const [loadingTrackedOrders, setLoadingTrackedOrders] = useState(true);
  const [error, setError] = useState('');
  const [closingStatus, setClosingStatus] = useState({});
  const [stockClosingStatus, setStockClosingStatus] = useState({});

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

    const fetchTrackedOrders = async () => {
      try {
        const response = await axios.get('/api/portfolio/tracked-orders', { params: { limit: 10 } });
        setTrackedOrders(Array.isArray(response.data) ? response.data : []);
      } catch (err) {
        console.error('Failed to fetch tracked orders:', err.response?.data?.detail || err.message);
        setTrackedOrders([]);
      } finally {
        setLoadingTrackedOrders(false);
      }
    };

    fetchOpenPositions();
    fetchRecentOrders();
    fetchTrackedOrders();
  }, []);

  const handleCloseStrategy = async (symbol) => {
    setClosingStatus(prev => ({ ...prev, [symbol]: { inProgress: true } }));
    
    const legsToClose = portfolioData.positions.options[symbol].map(leg => ({
        symbol: leg.symbol,
        secType: 'OPT',
        expiry_date: leg.expiry?.replace(/-/g, ''),
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

  const handleCloseStockPosition = async (symbol, quantity) => {
    setStockClosingStatus(prev => ({ ...prev, [symbol]: { inProgress: true } }));
    
    try {
        const response = await axios.post('/api/portfolio/close-stock-position', {
            symbol: symbol,
            quantity: quantity
        });
        setStockClosingStatus(prev => ({ ...prev, [symbol]: { inProgress: false, data: response.data } }));
    } catch (err) {
        const errorMessage = err.response?.data?.detail || 'Failed to submit stock closing order.';
        setStockClosingStatus(prev => ({ ...prev, [symbol]: { inProgress: false, error: errorMessage } }));
    }
  };

  const PortfolioSummary = ({ summary }) => {
    if (!summary) return null;

    const hasPnlToday = isFiniteNumber(summary.pnl_today);
    const hasUnrealizedPnl = isFiniteNumber(summary.unrealized_pnl);
    const pnlTodayColor = hasPnlToday ? (summary.pnl_today >= 0 ? 'green' : 'red') : '#666';
    const unrealizedPnlColor = hasUnrealizedPnl ? (summary.unrealized_pnl >= 0 ? 'green' : 'red') : '#666';

    return (
        <div style={{ border: '1px solid #ddd', borderRadius: '8px', padding: '20px', marginBottom: '24px', background: '#f8f9fa' }}>
            <h2 style={{ marginTop: 0, marginBottom: '16px' }}>Portfolio Overview</h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', fontSize: '1.1em' }}>
                <div>
                    <div style={{ color: '#666', fontSize: '0.9em' }}>Total Account Value</div>
                    <strong style={{ fontSize: '1.2em' }}>{formatCurrency(summary.market_value)}</strong>
                </div>
                <div>
                    <div style={{ color: '#666', fontSize: '0.9em' }}>P/L Today</div>
                    <strong style={{ fontSize: '1.2em', color: pnlTodayColor }}>{formatCurrency(summary.pnl_today)}</strong>
                </div>
                <div>
                    <div style={{ color: '#666', fontSize: '0.9em' }}>Unrealized P/L</div>
                    <strong style={{ fontSize: '1.2em', color: unrealizedPnlColor }}>{formatCurrency(summary.unrealized_pnl)}</strong>
                </div>
                <div>
                    <div style={{ color: '#666', fontSize: '0.9em' }}>Available Cash</div>
                    <strong style={{ fontSize: '1.2em' }}>{formatCurrency(summary.available_cash)}</strong>
                </div>
            </div>
        </div>
    );
  };

const StrategyCard = ({ symbol, legs, gptGuidance, underlyingSpotPrice }) => {
    const status = closingStatus[symbol];
    const isClosing = status?.inProgress;
    const legTotal = legs.reduce((acc, leg) => acc + leg.position, 0);
    const validUnrealizedPnl = legs.filter((leg) => isFiniteNumber(leg.unrealizedPNL)).map((leg) => leg.unrealizedPNL);
    const validMarketValues = legs.filter((leg) => isFiniteNumber(leg.marketValue)).map((leg) => leg.marketValue);
    const aggregateUnrealizedPnl = validUnrealizedPnl.reduce((acc, value) => acc + value, 0);
    const aggregateMarketValue = validMarketValues.reduce((acc, value) => acc + value, 0);
    const hasAggregateUnrealizedPnl = validUnrealizedPnl.length > 0;
    const aggregatePnlColor = !hasAggregateUnrealizedPnl ? '#666' : (aggregateUnrealizedPnl >= 0 ? 'green' : 'red');
    const guidance = gptGuidance || {};
    const recs = guidance.execution_recommendations || {};
    const entrySignals = Array.isArray(recs.entry_conditions) ? recs.entry_conditions : [];
    const exitSignals = Array.isArray(recs.exit_conditions) ? recs.exit_conditions : [];
    const alternatives = Array.isArray(recs.alternative_strategies) ? recs.alternative_strategies : [];
    const ideas = Array.isArray(guidance.actionable_ideas) ? guidance.actionable_ideas : [];
    const risks = Array.isArray(guidance.risk_factors) ? guidance.risk_factors : [];

    return (
      <div style={{ border: '1px solid #ddd', borderRadius: '8px', padding: '16px', marginBottom: '16px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
            <div>
                <h3 style={{ marginTop: 0, marginBottom: '5px' }}>{symbol} <span style={{fontSize: '0.8em', color: '#666'}}>({legs.length} Legs)</span></h3>
                <div style={{ fontSize: '0.95em', color: '#333', marginBottom: '4px' }}>
                  <strong>Underlying market price (Alpaca):</strong> {formatCurrency(underlyingSpotPrice, '--')}
                </div>
                <div style={{ fontSize: '0.9em', color: '#555' }}>
                  Grouped by underlying symbol (not broker-native strategy IDs)
                </div>
                <div style={{ marginTop: '6px', fontSize: '0.95em' }}>
                  <strong>Strategy Unrealized P/L:</strong>{' '}
                  <span style={{ color: aggregatePnlColor }}>
                    {formatCurrency(aggregateUnrealizedPnl, '--')}
                  </span>
                  <span style={{ marginLeft: '12px', color: '#555' }}>
                    Net Market Value: {formatCurrency(aggregateMarketValue, '--')}
                  </span>
                </div>
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
                    <th style={{padding: '8px', border: '1px solid #ddd', textAlign: 'left'}}>Current Mkt Price</th>
                    <th style={{padding: '8px', border: '1px solid #ddd', textAlign: 'left'}}>Unrealized P/L</th>
                </tr>
            </thead>
            <tbody>
                {legs.map((leg, index) => {
                    const legUnrealizedPnl = getPositionUnrealizedPnl(leg);
                    const legPnlColor = !isFiniteNumber(legUnrealizedPnl) ? '#666' : (legUnrealizedPnl >= 0 ? 'green' : 'red');
                    const legCurrentMarketPrice = getPositionMarketPrice(leg, 100);
                    return (
                        <tr key={index}>
                            <td style={{padding: '8px', border: '1px solid #ddd', color: leg.position > 0 ? 'green' : 'red', fontWeight: 'bold'}}>{leg.position > 0 ? `+${leg.position}` : leg.position}</td>
                            <td style={{padding: '8px', border: '1px solid #ddd'}}>{leg.right === 'C' ? 'Call' : 'Put'}</td>
                            <td style={{padding: '8px', border: '1px solid #ddd'}}>{formatCurrency(leg.strike, '--')}</td>
                            <td style={{padding: '8px', border: '1px solid #ddd'}}>{leg.expiry}</td>
                            <td style={{padding: '8px', border: '1px solid #ddd'}}>
                              {formatCurrency(leg.position !== 0 ? (leg.avgCost / (leg.position * 100)) : 0)}
                            </td>
                            <td style={{padding: '8px', border: '1px solid #ddd'}}>
                              {formatCurrency(legCurrentMarketPrice, '--')}
                            </td>
                            <td style={{padding: '8px', border: '1px solid #ddd', color: legPnlColor, fontWeight: 600}}>
                              {formatCurrency(legUnrealizedPnl, '--')}
                            </td>
                        </tr>
                    );
                })}
            </tbody>
        </table>
        {status?.data && (
            <div style={{marginTop: '10px', padding: '10px', background: '#e8f5e9', borderRadius: '5px'}}>
                <strong>Closing Order Status:</strong> {status.data.status}
                
                {/* Handle new single strategy order response */}
                {status.data.trade && (
                    <div style={{marginTop: '8px'}}>
                        <div><strong>Strategy:</strong> {status.data.trade.strategy}</div>
                        <div><strong>Order Status:</strong> {status.data.trade.order_status}</div>
                        <div><strong>Filled:</strong> {status.data.trade.filled} / {status.data.trade.strategy_size}</div>
                        <div><strong>Remaining:</strong> {status.data.trade.remaining}</div>
                    </div>
                )}
                
                {/* Handle fallback individual leg orders response */}
                {status.data.trades && (
                    <div>
                        {status.data.note && (
                            <div style={{fontSize: '0.9em', color: '#856404', marginBottom: '8px'}}>
                                <em>{status.data.note}</em>
                            </div>
                        )}
                        <ul>
                            {status.data.trades.map((trade, i) => (
                                <li key={i}>{trade.leg}: {trade.order_status} (Filled: {trade.filled})</li>
                            ))}
                        </ul>
                    </div>
                )}
            </div>
        )}
        {status?.error && (
            <div style={{marginTop: '10px', padding: '10px', background: '#f8d7da', borderRadius: '5px', color: '#721c24'}}>
                <strong>Error:</strong> {status.error}
            </div>
        )}

        {guidance && (
          <div style={{ marginTop: '12px', borderTop: '1px solid #eee', paddingTop: '12px' }}>
            <div style={{ fontWeight: 600, marginBottom: '8px' }}>🤖 AI Execution Guidance</div>
            {guidance.final_bias && (
              <div style={{ marginBottom: '8px' }}>
                <strong>AI Bias:</strong>{' '}
                <span style={{ color: guidance.final_bias.includes('Bull') ? 'green' : guidance.final_bias.includes('Bear') ? 'red' : '#555' }}>
                  {guidance.final_bias}
                </span>
              </div>
            )}
            {(entrySignals.length > 0 || exitSignals.length > 0 || recs.stop_loss_guidance || recs.profit_target_guidance || alternatives.length > 0) && (
              <div style={{ background: '#f6f9ff', borderRadius: '6px', padding: '10px', marginBottom: '10px' }}>
                {entrySignals.length > 0 && (
                  <div style={{ marginBottom: '8px' }}>
                    <strong>📈 Entry Signals:</strong>
                    <ul style={{ margin: '4px 0 0 18px', padding: 0 }}>
                      {entrySignals.map((s, i) => <li key={i}>{s}</li>)}
                    </ul>
                  </div>
                )}
                {exitSignals.length > 0 && (
                  <div style={{ marginBottom: '8px' }}>
                    <strong>📉 Exit Signals:</strong>
                    <ul style={{ margin: '4px 0 0 18px', padding: 0 }}>
                      {exitSignals.map((s, i) => <li key={i}>{s}</li>)}
                    </ul>
                  </div>
                )}
                {recs.stop_loss_guidance && (
                  <div style={{ marginBottom: '6px' }}>
                    <strong>🛡️ Stop Loss:</strong> {recs.stop_loss_guidance}
                  </div>
                )}
                {recs.profit_target_guidance && (
                  <div style={{ marginBottom: '6px' }}>
                    <strong>🎯 Profit Target:</strong> {recs.profit_target_guidance}
                  </div>
                )}
                {alternatives.length > 0 && (
                  <div>
                    <strong>🔄 Alternative Strategies:</strong>
                    <ul style={{ margin: '4px 0 0 18px', padding: 0 }}>
                      {alternatives.map((alt, idx) => (
                        <li key={idx}>
                          {alt.type || 'Strategy'}
                          {alt.confidence && (
                            <span style={{ marginLeft: '5px', color: alt.confidence === 'High' ? 'green' : alt.confidence === 'Medium' ? 'orange' : '#c0392b' }}>
                              ({alt.confidence})
                            </span>
                          )}
                          {alt.description ? ` - ${alt.description}` : ''}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {(ideas.length > 0 || risks.length > 0) && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px' }}>
                {ideas.length > 0 && (
                  <div style={{ background: '#f8fdf6', borderRadius: '6px', padding: '10px' }}>
                    <strong>💡 Key Ideas</strong>
                    <ul style={{ margin: '6px 0 0 18px', padding: 0 }}>
                      {ideas.map((idea, idx) => <li key={idx}>{idea}</li>)}
                    </ul>
                  </div>
                )}
                {risks.length > 0 && (
                  <div style={{ background: '#fff6f6', borderRadius: '6px', padding: '10px' }}>
                    <strong>⚠️ Risk Factors</strong>
                    <ul style={{ margin: '6px 0 0 18px', padding: 0 }}>
                      {risks.map((risk, idx) => <li key={idx}>{risk}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            )}
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
              <th style={{ padding: '8px', border: '1px solid #ddd', textAlign: 'left' }}>Current Mkt Price</th>
              <th style={{ padding: '8px', border: '1px solid #ddd', textAlign: 'left' }}>Unrealized P/L</th>
              <th style={{ padding: '8px', border: '1px solid #ddd', textAlign: 'left' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {stocks.map((stock, index) => {
              const status = stockClosingStatus[stock.symbol];
              const isClosing = status?.inProgress;
              const positionColor = stock.position > 0 ? 'green' : stock.position < 0 ? 'red' : 'black';
              const stockUnrealizedPnl = getPositionUnrealizedPnl(stock);
              const stockPnlColor = !isFiniteNumber(stockUnrealizedPnl) ? '#666' : (stockUnrealizedPnl >= 0 ? 'green' : 'red');
              const stockCurrentMarketPrice = getPositionMarketPrice(stock);
              
              return (
                <tr key={index}>
                  <td style={{ padding: '8px', border: '1px solid #ddd', fontWeight: 'bold' }}>{stock.symbol}</td>
                  <td style={{ padding: '8px', border: '1px solid #ddd', color: positionColor, fontWeight: 'bold' }}>
                    {stock.position > 0 ? `+${stock.position}` : stock.position}
                  </td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>
                    {formatCurrency(stock.position !== 0 ? (stock.avgCost / stock.position) : 0)}
                  </td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>
                    {formatCurrency(stockCurrentMarketPrice, '--')}
                  </td>
                  <td style={{ padding: '8px', border: '1px solid #ddd', color: stockPnlColor, fontWeight: 600 }}>
                    {formatCurrency(stockUnrealizedPnl, '--')}
                  </td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>
                    <button 
                      onClick={() => handleCloseStockPosition(stock.symbol, stock.position)} 
                      disabled={isClosing || stock.position === 0}
                      style={{
                        backgroundColor: stock.position === 0 ? '#ccc' : '#dc3545',
                        color: 'white',
                        border: 'none',
                        padding: '6px 12px',
                        borderRadius: '4px',
                        cursor: stock.position === 0 ? 'not-allowed' : 'pointer',
                        fontSize: '0.9em'
                      }}
                    >
                      {isClosing ? 'Closing...' : 'Close Position'}
                    </button>
                    {status?.data && (
                      <div style={{marginTop: '8px', padding: '6px', background: '#e8f5e9', borderRadius: '4px', fontSize: '0.8em'}}>
                        <strong>Order Status:</strong> {status.data.status}
                        <br />Filled: {status.data.filled}/{status.data.quantity_closed}
                      </div>
                    )}
                    {status?.error && (
                      <div style={{marginTop: '8px', padding: '6px', background: '#f8d7da', borderRadius: '4px', color: '#721c24', fontSize: '0.8em'}}>
                        <strong>Error:</strong> {status.error}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  };

  if (loading) return <p>Loading open positions from broker...</p>;

  const positions = !error && portfolioData ? portfolioData.positions : null;
  const optionPositions = positions?.options || {};
  const underlyingSpotPrices = (!error && portfolioData?.underlying_spot_prices) || {};
  const stockPositions = positions?.stocks || [];
  const hasOptionPositions = Object.keys(optionPositions).length > 0;
  const hasStockPositions = Array.isArray(stockPositions) && stockPositions.length > 0;
  const hasAnyPositions = hasOptionPositions || hasStockPositions;

  // Build a quick lookup of latest guidance per ticker and per (ticker, expiration)
  const trackedByTicker = {};
  const trackedByTickerExp = {};
  (trackedOrders || []).forEach(o => {
    const keyT = o.ticker;
    const keyTE = `${o.ticker}|${o.expiration_date || ''}`;
    if (keyT && (!trackedByTicker[keyT] || (o.placed_at || '') > (trackedByTicker[keyT].placed_at || ''))) {
      trackedByTicker[keyT] = o;
    }
    if (o.ticker && o.expiration_date && (!trackedByTickerExp[keyTE] || (o.placed_at || '') > (trackedByTickerExp[keyTE].placed_at || ''))) {
      trackedByTickerExp[keyTE] = o;
    }
  });

  const getGuidanceFor = (sym, legsArr) => {
    if (!sym) return null;
    const expiries = (legsArr || [])
      .map(l => l.expiry)
      .filter(v => !!v);
    // Pick the most common expiry among legs
    let chosenExp = '';
    if (expiries.length > 0) {
      const counts = expiries.reduce((acc, e) => { acc[e] = (acc[e] || 0) + 1; return acc; }, {});
      chosenExp = Object.entries(counts).sort((a,b) => b[1]-a[1])[0][0];
    }
    const byExp = chosenExp ? trackedByTickerExp[`${sym}|${chosenExp}`] : null;
    const byTicker = trackedByTicker[sym] || null;
    const pick = byExp || byTicker;
    return pick ? (pick.gpt_guidance || null) : null;
  };

  return (
    <div>
      {error && (
        <div style={{
          border: '1px solid #f5c2c7',
          background: '#f8d7da',
          color: '#721c24',
          padding: '16px',
          borderRadius: '6px',
          marginBottom: '24px',
        }}>
          <strong>Unable to load live portfolio data.</strong>
          <div style={{ marginTop: '6px' }}>{error}</div>
        </div>
      )}

      <PortfolioSummary summary={portfolioData?.summary} />
      <RecentOrders orders={recentOrders} isLoading={loadingOrders} />

      {error ? (
        <div style={{ border: '1px solid #ddd', borderRadius: '8px', padding: '16px', marginTop: '24px', background: '#fdfdfd' }}>
          <strong>Broker positions are currently unavailable.</strong>
          <p style={{ marginTop: '8px', color: '#555' }}>Retry in a moment or check broker connectivity.</p>
        </div>
      ) : hasAnyPositions ? (
        <>
          {hasOptionPositions && (
            <div style={{marginTop: '24px'}}>
                <h2>Open Option Strategies</h2>
                <p>This page shows all open option positions in your account, grouped by underlying ticker.</p>
                {Object.entries(optionPositions).map(([symbol, legs]) => (
                    <StrategyCard
                      key={symbol}
                      symbol={symbol}
                      legs={legs}
                      gptGuidance={getGuidanceFor(symbol, legs)}
                      underlyingSpotPrice={underlyingSpotPrices[symbol]}
                    />
                ))}
            </div>
          )}
          {hasStockPositions && <StockPositions stocks={stockPositions} />}
        </>
      ) : (
        <div style={{ border: '1px solid #ddd', borderRadius: '8px', padding: '16px', marginTop: '24px', background: '#fdfdfd' }}>
          <strong>No open positions found in the account.</strong>
          <p style={{ marginTop: '8px', color: '#555' }}>Run an analysis and execute a strategy to populate this section.</p>
        </div>
      )}
    </div>
  );
};

export default PortfolioPage;
