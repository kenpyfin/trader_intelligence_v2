import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';

/**
 * YieldCurvePanel
 * - Stage 1 frontend component to visualize/select Risk-Free Rate source
 * - Supports:
 *   • Toggle between Treasury curve and ETF-implied rate
 *   • Enter tickers for ETF-implied calculation
 *   • Fetch and display curve data with graceful fallbacks
 *   • Persist preferred source (optional backend endpoint)
 *
 * Integration:
 *   import { YieldCurvePanel } from '../components';
 *   ...
 *   <YieldCurvePanel defaultSource="treasury" defaultTickers="SPY, QQQ, IWM" onSourceSaved={() => {}} />
 */
export const YieldCurvePanel = ({ defaultSource = 'treasury', defaultTickers = 'SPY, QQQ, IWM', onSourceSaved }) => {
  const [source, setSource] = useState(defaultSource); // 'treasury' | 'etf'
  const [tickers, setTickers] = useState(defaultTickers);
  const [curve, setCurve] = useState([]); // [{ tenor: '1M', rate: 0.05 }, ...]
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [logs, setLogs] = useState([]);

  // Standard display tenors for fallback/normalization
  const STANDARD_TENORS = useMemo(
    () => ['1M', '3M', '6M', '1Y', '2Y', '5Y', '10Y'],
    []
  );

  const formatPercent = (v) => {
    if (typeof v !== 'number' || Number.isNaN(v)) return 'N/A';
    return `${(v * 100).toFixed(2)}%`;
  };

  const normalizeCurve = (raw) => {
    // Accept multiple shapes:
    // 1) { curve: [{tenor, rate}], source, logs? }
    // 2) [{tenor, rate}, ...]
    // 3) { '1M': 0.05, '2Y': 0.04, ... }
    if (!raw) return [];
    let arr = [];
    if (Array.isArray(raw)) {
      arr = raw;
    } else if (raw.curve && Array.isArray(raw.curve)) {
      arr = raw.curve;
      if (raw.logs && Array.isArray(raw.logs)) setLogs(raw.logs);
    } else if (typeof raw === 'object') {
      arr = Object.entries(raw)
        .filter(([k, v]) => typeof v === 'number')
        .map(([k, v]) => ({ tenor: k, rate: v }));
    }
    // Ensure objects have tenor and rate
    arr = arr
      .filter(x => x && typeof x.tenor === 'string' && typeof x.rate === 'number')
      .sort((a, b) => STANDARD_TENORS.indexOf(a.tenor) - STANDARD_TENORS.indexOf(b.tenor));
    return arr;
  };

  const makeFlatCurveFromRate = (rate) => {
    return STANDARD_TENORS.map(t => ({ tenor: t, rate }));
  };

  const fetchCurve = async () => {
    setLoading(true);
    setError('');
    setLogs([]);
    setCurve([]);

    try {
      if (source === 'treasury') {
        // Preferred endpoint if backend provides a constructed Treasury curve
        // GET /api/yield-curve?source=treasury -> { curve: [{tenor, rate}], logs? } or mapping
        try {
          const res = await axios.get('/api/yield-curve', { params: { source: 'treasury' } });
          const normalized = normalizeCurve(res.data);
          if (normalized.length > 0) {
            setCurve(normalized);
            return;
          }
        } catch (e) {
          // Soft-fail to generic macro endpoint fallback if available
        }
        // Optional fallback: GET /api/macro-data (if it includes a curve; normalize if possible)
        try {
          const res = await axios.get('/api/macro-data');
          const normalized = normalizeCurve(res.data?.treasury_curve || res.data?.yield_curve);
          if (normalized.length > 0) {
            setCurve(normalized);
            return;
          }
        } catch (e) {
          // proceed to error
        }
        throw new Error('Could not fetch Treasury yield curve from backend.');
      } else {
        // ETF-implied: prefer a full curve endpoint if backend supports it
        // GET /api/yield-curve?source=etf&tickers=SPY,QQQ,IWM -> { curve: [...] }
        const tickersParam = tickers.split(',').map(t => t.trim().toUpperCase()).filter(Boolean).join(',');
        let normalized = [];
        try {
          const res = await axios.get('/api/yield-curve', { params: { source: 'etf', tickers: tickersParam } });
          normalized = normalizeCurve(res.data);
        } catch (e) {
          // If full curve not available, fallback to single implied rate and build flat curve
          const res = await axios.post('/api/calculate-risk-free-rate', {
            tickers: tickersParam.split(',').filter(Boolean)
          });
          const singleRate = res.data?.risk_free_rate;
          if (typeof singleRate === 'number') {
            normalized = makeFlatCurveFromRate(singleRate);
            if (Array.isArray(res.data?.logs)) setLogs(res.data.logs);
          }
        }
        if (normalized.length === 0) throw new Error('Could not fetch ETF-implied rate/curve from backend.');
        setCurve(normalized);
      }
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to fetch yield curve.');
    } finally {
      setLoading(false);
    }
  };

  const savePreference = async () => {
    try {
      await axios.post('/api/settings/risk-free-source', {
        source,
        tickers: source === 'etf' ? tickers.split(',').map(t => t.trim().toUpperCase()).filter(Boolean) : undefined
      });
      if (typeof onSourceSaved === 'function') onSourceSaved(source);
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to save preference.');
    }
  };

  useEffect(() => {
    // Auto-fetch on mount for default source
    fetchCurve();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div style={{ border: '1px solid #ddd', borderRadius: 8, padding: 16, marginBottom: 16 }}>
      <h2 style={{ marginTop: 0, marginBottom: 12 }}>Yield Curve & Risk-Free Source</h2>

      <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
        <div>
          <label style={{ marginRight: 8 }}>
            <input
              type="radio"
              name="rf-source"
              value="treasury"
              checked={source === 'treasury'}
              onChange={() => setSource('treasury')}
            />
            <span style={{ marginLeft: 6 }}>Treasury Curve</span>
          </label>
          <label style={{ marginLeft: 16 }}>
            <input
              type="radio"
              name="rf-source"
              value="etf"
              checked={source === 'etf'}
              onChange={() => setSource('etf')}
            />
            <span style={{ marginLeft: 6 }}>ETF-Implied (via Put-Call Parity)</span>
          </label>
        </div>

        {source === 'etf' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <label htmlFor="rf-tickers" style={{ fontSize: 12, color: '#555' }}>Tickers:</label>
            <input
              id="rf-tickers"
              type="text"
              value={tickers}
              onChange={(e) => setTickers(e.target.value)}
              placeholder="SPY, QQQ, IWM"
              style={{
                padding: '6px 8px',
                border: '1px solid #ccc',
                borderRadius: 6,
                minWidth: 220
              }}
            />
          </div>
        )}

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button
            onClick={fetchCurve}
            disabled={loading}
            style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #ccc', background: '#fff', cursor: 'pointer' }}
          >
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
          <button
            onClick={savePreference}
            style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #2a7', background: '#eaffea', color: '#184', cursor: 'pointer' }}
          >
            Make Default
          </button>
        </div>
      </div>

      {error && (
        <div style={{ marginTop: 12, padding: 10, background: '#ffecec', border: '1px solid #f5c2c2', borderRadius: 6, color: '#a33' }}>
          {error}
        </div>
      )}

      <div style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0, marginBottom: 8 }}>Current {source === 'treasury' ? 'Treasury' : 'ETF-Implied'} Curve</h3>
        {curve.length === 0 ? (
          <p style={{ color: '#666' }}>{loading ? 'Loading…' : 'No curve data to display.'}</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 420 }}>
              <thead>
                <tr style={{ background: '#f7f7f7' }}>
                  <th style={{ textAlign: 'left', padding: '8px 10px', borderBottom: '1px solid #eee' }}>Tenor</th>
                  <th style={{ textAlign: 'right', padding: '8px 10px', borderBottom: '1px solid #eee' }}>Rate</th>
                  <th style={{ textAlign: 'left', padding: '8px 10px', borderBottom: '1px solid #eee' }}>Bar</th>
                </tr>
              </thead>
              <tbody>
                {curve.map((row, idx) => {
                  const pct = typeof row.rate === 'number' ? Math.max(0, Math.min(1, row.rate)) : 0;
                  const barWidth = `${(pct * 100).toFixed(0)}%`;
                  return (
                    <tr key={`${row.tenor}-${idx}`}>
                      <td style={{ padding: '8px 10px', borderBottom: '1px solid #f1f1f1' }}>{row.tenor}</td>
                      <td style={{ padding: '8px 10px', textAlign: 'right', borderBottom: '1px solid #f1f1f1' }}>{formatPercent(row.rate)}</td>
                      <td style={{ padding: '8px 10px', borderBottom: '1px solid #f1f1f1' }}>
                        <div style={{ background: '#eef6ff', borderRadius: 4, height: 8, width: '100%' }}>
                          <div style={{ width: barWidth, background: '#3b82f6', height: 8, borderRadius: 4 }} />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {logs && logs.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <details>
            <summary style={{ cursor: 'pointer', userSelect: 'none' }}>Calculation Log</summary>
            <ul style={{ marginTop: 8, paddingLeft: 20 }}>
              {logs.map((l, i) => <li key={i} style={{ color: '#666', fontSize: 13 }}>{String(l)}</li>)}
            </ul>
          </details>
        </div>
      )}
    </div>
  );
};

export default YieldCurvePanel;
