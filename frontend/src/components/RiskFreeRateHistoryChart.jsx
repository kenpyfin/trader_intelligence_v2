import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import Plot from 'react-plotly.js';
import {
  Box,
  Button,
  CircularProgress,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  TextField,
  Typography,
  Alert,
} from '@mui/material';

const formatRatePercent = (value) => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return '—';
  const pct = Math.abs(numeric) <= 1 ? numeric * 100 : numeric;
  return `${pct.toFixed(3)}%`;
};

const RiskFreeRateHistoryChart = () => {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [tickerFilter, setTickerFilter] = useState('');
  const [days, setDays] = useState(365);

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = { limit: 500, days };
      const normalizedTicker = tickerFilter.trim().toUpperCase();
      if (normalizedTicker) params.ticker = normalizedTicker;

      const response = await axios.get('/api/risk-free-rate/history', { params });
      setItems(Array.isArray(response.data?.items) ? response.data.items : []);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load risk-free rate history.');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [tickerFilter, days]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const plotData = useMemo(() => {
    const sorted = [...items].sort((a, b) => {
      const aTime = new Date(a.created_at || 0).getTime();
      const bTime = new Date(b.created_at || 0).getTime();
      return aTime - bTime;
    });

    const x = sorted.map((row) => row.created_at);
    const y = sorted.map((row) => {
      const rate = Number(row.risk_free_rate);
      if (!Number.isFinite(rate)) return null;
      return Math.abs(rate) <= 1 ? rate * 100 : rate;
    });
    const text = sorted.map((row) => {
      const parts = [formatRatePercent(row.risk_free_rate)];
      if (row.ticker) parts.push(row.ticker);
      if (row.analysis_method) parts.push(row.analysis_method);
      return parts.join(' · ');
    });

    return { x, y, text, sorted };
  }, [items]);

  return (
    <Paper variant="outlined" sx={{ p: 2, mt: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 2, flexWrap: 'wrap', mb: 2 }}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 600 }}>Risk-Free Rate History</Typography>
          <Typography variant="body2" color="text.secondary">
            Implied from SPY, QQQ, and IWM option chains. One in-session point per trading day.
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
          <TextField
            label="Ticker filter"
            size="small"
            value={tickerFilter}
            onChange={(e) => setTickerFilter(e.target.value.toUpperCase())}
            placeholder="All tickers"
            sx={{ width: 140 }}
          />
          <FormControl size="small" sx={{ minWidth: 120 }}>
            <InputLabel>Window</InputLabel>
            <Select
              value={days}
              label="Window"
              onChange={(e) => setDays(Number(e.target.value))}
            >
              <MenuItem value={30}>30 days</MenuItem>
              <MenuItem value={90}>90 days</MenuItem>
              <MenuItem value={180}>180 days</MenuItem>
              <MenuItem value={365}>1 year</MenuItem>
            </Select>
          </FormControl>
          <Button variant="outlined" size="small" onClick={fetchHistory} disabled={loading}>
            Refresh
          </Button>
        </Box>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
          <CircularProgress size={28} />
        </Box>
      ) : plotData.sorted.length === 0 ? (
        <Typography color="text.secondary" align="center" sx={{ py: 3 }}>
          No risk-free rate history yet. Run an analysis to start building the curve.
        </Typography>
      ) : (
        <>
          <Plot
            data={[
              {
                x: plotData.x,
                y: plotData.y,
                text: plotData.text,
                type: 'scatter',
                mode: 'lines+markers',
                name: 'Risk-free rate',
                line: { color: '#1976d2', width: 2 },
                marker: { size: 6 },
                hovertemplate: '%{text}<br>%{x}<extra></extra>',
              },
            ]}
            layout={{
              autosize: true,
              height: 360,
              margin: { l: 48, r: 16, t: 16, b: 48 },
              xaxis: { title: 'Date', type: 'date' },
              yaxis: { title: 'Rate (%)', tickformat: '.3f' },
              paper_bgcolor: 'rgba(0,0,0,0)',
              plot_bgcolor: 'rgba(0,0,0,0)',
            }}
            config={{ responsive: true, displayModeBar: false }}
            style={{ width: '100%' }}
          />
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
            {plotData.sorted.length} data point{plotData.sorted.length === 1 ? '' : 's'}
            {tickerFilter.trim() ? ` for ${tickerFilter.trim().toUpperCase()}` : ''}
            {' · '}
            Latest: {formatRatePercent(plotData.sorted[plotData.sorted.length - 1]?.risk_free_rate)}
          </Typography>
        </>
      )}
    </Paper>
  );
};

export default RiskFreeRateHistoryChart;
