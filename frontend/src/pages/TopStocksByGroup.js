import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Tab,
  Tabs,
  Tooltip,
  Typography,
} from '@mui/material';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';

const viewToParam = {
  clusters: 'clusters',
  sectors: 'sectors',
  regimes: 'regimes',
};

const columnDefinitions = [
  {
    key: 'ticker',
    label: 'Ticker',
    tooltip: 'Stock ticker symbol for the ranked company.',
  },
  {
    key: 'score',
    label: 'Score',
    tooltip: 'Composite selection score for the current mode. Higher means more aligned with the selected strategy.',
  },
  {
    key: 'clusterRank',
    label: 'Cluster Rank',
    tooltip: 'Rank within this peer cluster. 1 is the strongest stock in this cluster.',
  },
  {
    key: 'globalRank',
    label: 'Global Rank',
    tooltip: 'Rank across the full evaluated universe for this run and mode.',
  },
  {
    key: 'confidence',
    label: 'Confidence',
    tooltip: 'Confidence in this ranking based on data completeness, cluster quality, and signal alignment.',
  },
  {
    key: 'regime',
    label: 'Regime',
    tooltip: 'Current market behavior bucket for the stock (for example calm_trend or stress).',
  },
  {
    key: 'actions',
    label: 'Actions',
    tooltip: 'Quick actions for this ticker: open Finviz or send it to the Analysis page.',
  },
];

const TopStocksByGroup = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('clusters');
  const [mode, setMode] = useState('sell_premium');
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState('');

  const fetchData = async (view, nextMode) => {
    setLoading(true);
    setError('');
    try {
      const response = await axios.get('/api/stock-selection/latest', {
        params: { view: viewToParam[view], mode: nextMode },
      });
      if (response.data?.status !== 'success') {
        throw new Error(response.data?.message || 'Failed to load stock selection snapshot.');
      }
      setPayload(response.data.payload || null);
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || 'Unable to fetch stock selection data.');
      setPayload(null);
    } finally {
      setLoading(false);
    }
  };

  const runRefresh = async () => {
    setRunning(true);
    setError('');
    try {
      const response = await axios.post('/api/stock-selection/run', {
        force: true,
        max_tickers: 800,
        top_n_per_group: 10,
      });
      if (response.data?.status !== 'success') {
        throw new Error(response.data?.message || 'Failed to refresh stock selection snapshot.');
      }
      await fetchData(activeTab, mode);
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || 'Unable to refresh stock selection snapshot.');
    } finally {
      setRunning(false);
    }
  };

  useEffect(() => {
    fetchData(activeTab, mode);
  }, [activeTab, mode]);

  const groups = useMemo(() => {
    if (!payload) return [];
    if (activeTab === 'clusters') return payload.clusters || [];
    if (activeTab === 'sectors') return payload.sectors || [];
    return payload.regimes || [];
  }, [payload, activeTab]);

  const metadata = payload?.metadata || {};

  const handleAnalyzeTicker = (ticker) => {
    if (!ticker) return;
    const normalizedTicker = String(ticker).trim().toUpperCase();
    try {
      window.localStorage.setItem('ticker', JSON.stringify(normalizedTicker));
    } catch (error) {
      // Best effort: navigation still works even if storage is blocked.
      console.error('Unable to persist ticker to localStorage:', error);
    }
    navigate('/');
  };

  return (
    <Box>
      <Typography variant="h4" sx={{ mb: 2, fontWeight: 700 }}>
        Top Stocks By Group
      </Typography>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 2 }}>
        Cached peer-model rankings grouped by clusters, sectors, and regimes.
      </Typography>

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'center' }}>
            <FormControl size="small" sx={{ minWidth: 220 }}>
              <InputLabel id="mode-select-label">Ranking Mode</InputLabel>
              <Select
                labelId="mode-select-label"
                value={mode}
                label="Ranking Mode"
                onChange={(e) => setMode(e.target.value)}
              >
                <MenuItem value="sell_premium">Sell Premium</MenuItem>
                <MenuItem value="buy_premium">Buy Premium</MenuItem>
              </Select>
            </FormControl>
            <Button variant="contained" onClick={runRefresh} disabled={running}>
              {running ? 'Refreshing...' : 'Recompute Snapshot'}
            </Button>
            {metadata.generated_at && (
              <Typography variant="body2" color="text.secondary">
                Last update: {metadata.generated_at}
              </Typography>
            )}
          </Box>
          {metadata.tickers_ranked != null && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              Ranked {metadata.tickers_ranked} / {metadata.tickers_considered} tickers; excluded {metadata.tickers_excluded}.
            </Typography>
          )}
        </CardContent>
      </Card>

      <Tabs
        value={activeTab}
        onChange={(_, value) => setActiveTab(value)}
        sx={{ mb: 2 }}
      >
        <Tab label="Clusters" value="clusters" />
        <Tab label="Sectors" value="sectors" />
        <Tab label="Regimes" value="regimes" />
      </Tabs>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {loading && (
        <Box sx={{ display: 'flex', justifyContent: 'center', my: 6 }}>
          <CircularProgress />
        </Box>
      )}

      {!loading && !error && groups.length === 0 && (
        <Alert severity="warning">No grouped results found for this view.</Alert>
      )}

      {!loading && !error && groups.map((group) => (
        <Card key={group.group_key} sx={{ mb: 2 }}>
          <CardContent>
            <Typography variant="h6" sx={{ mb: 1 }}>
              {group.group_label}
            </Typography>
            <Box sx={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    {columnDefinitions.map((column) => (
                      <th key={column.key} style={{ textAlign: 'left', padding: 8 }}>
                        <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5 }}>
                          <span>{column.label}</span>
                          <Tooltip title={column.tooltip} arrow>
                            <IconButton
                              size="small"
                              sx={{ p: 0.25 }}
                              aria-label={`Explain ${column.label}`}
                            >
                              <InfoOutlinedIcon fontSize="inherit" />
                            </IconButton>
                          </Tooltip>
                        </Box>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(group.stocks || []).map((stock) => (
                    <tr key={`${group.group_key}-${stock.ticker}-${stock.global_rank}`}>
                      <td style={{ padding: 8, borderTop: '1px solid #eee' }}>
                        <a
                          href={`https://finviz.com/quote.ashx?t=${encodeURIComponent(stock.ticker)}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ color: '#1976d2', textDecoration: 'none', fontWeight: 500 }}
                        >
                          {stock.ticker}
                        </a>
                      </td>
                      <td style={{ padding: 8, borderTop: '1px solid #eee' }}>{Number(stock.selection_score || 0).toFixed(3)}</td>
                      <td style={{ padding: 8, borderTop: '1px solid #eee' }}>{stock.cluster_rank}</td>
                      <td style={{ padding: 8, borderTop: '1px solid #eee' }}>{stock.global_rank}</td>
                      <td style={{ padding: 8, borderTop: '1px solid #eee' }}>{Number(stock.confidence_score || 0).toFixed(3)}</td>
                      <td style={{ padding: 8, borderTop: '1px solid #eee' }}>{stock.regime_bucket}</td>
                      <td style={{ padding: 8, borderTop: '1px solid #eee' }}>
                        <Button
                          variant="outlined"
                          size="small"
                          onClick={() => handleAnalyzeTicker(stock.ticker)}
                        >
                          Analyze
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Box>
          </CardContent>
        </Card>
      ))}
    </Box>
  );
};

export default TopStocksByGroup;

