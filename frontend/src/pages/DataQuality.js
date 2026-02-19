import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Grid,
  Typography,
  Button,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  TextField,
  Stack,
  Divider,
  Alert,
  AlertTitle,
  Chip,
  IconButton,
  Tooltip,
  Paper
} from '@mui/material';
import {
  Refresh,
  Settings,
  Download,
  Schedule,
  TrendingUp,
  Assessment,
  Security,
  Speed
} from '@mui/icons-material';
import Plot from 'react-plotly.js';

// Import our new components
import DataQualityDashboard from '../components/DataQualityDashboard';
import DataQualityAlerts from '../components/DataQualityAlerts';
import useDataQualityWebSocket from '../hooks/useDataQualityWebSocket';

// Mock data generator for demonstration (replace with real API calls)
const generateMockQualityData = () => ({
  overall_quality_level: Math.random() > 0.3 ? 'acceptable' : Math.random() > 0.5 ? 'good' : 'poor',
  combined_score: 0.4 + Math.random() * 0.4,
  completeness_score: 0.5 + Math.random() * 0.4,
  quality_score: 0.6 + Math.random() * 0.3,
  overlap_score: 0.3 + Math.random() * 0.5,
  pass_threshold: 0.6,
  issues: [
    {
      id: 1,
      description: 'Missing bid-ask data for 15% of strikes',
      impact: 'Reduced accuracy in volatility calculations',
      severity: 'warning',
      recommendation: 'Use alternative data sources for missing strikes'
    },
    {
      id: 2,
      description: 'High latency in real-time data feed',
      impact: 'Delayed strategy recommendations',
      severity: 'info',
      recommendation: 'Monitor data provider connection'
    }
  ],
  recommendations: [
    'Consider using data from alternative strike ranges',
    'Implement data quality caching mechanisms',
    'Set up automated data quality monitoring alerts'
  ],
  asset_type: 'equity',
  strike_count: 45,
  valid_strikes: 38,
  coverage_data: {
    strike_prices: [100, 105, 110, 115, 120, 125, 130],
    valid_data: [12, 15, 18, 20, 16, 14, 10],
    missing_data: [3, 2, 1, 0, 2, 4, 5]
  },
  trends_data: {
    timestamps: ['09:30', '10:00', '10:30', '11:00', '11:30', '12:00'],
    completeness_scores: [75, 78, 82, 80, 85, 83],
    quality_scores: [68, 72, 70, 75, 73, 76],
    coverage_scores: [85, 87, 89, 88, 90, 87]
  }
});

const generateMockAlerts = () => [
  {
    id: 'alert-1',
    type: 'data_quality_degraded',
    severity: 'high',
    title: 'Data Quality Degraded',
    message: 'Overall data quality has dropped to 65% for SPY options',
    timestamp: new Date(Date.now() - 300000).toISOString(), // 5 minutes ago
    details: 'Strike coverage: 78%, Completeness: 82%, Quality: 65%',
    recommendations: ['Review data provider connection', 'Consider backup data sources']
  },
  {
    id: 'alert-2',
    type: 'missing_strikes',
    severity: 'medium',
    title: 'Missing Strike Data',
    message: '12 out-of-the-money strikes missing bid/ask data',
    timestamp: new Date(Date.now() - 600000).toISOString(), // 10 minutes ago
    details: 'Affects strikes: 140, 145, 150, 155, 160, 165, 170, 175, 180, 185, 190, 195',
    recommendations: ['Use interpolation for missing strikes', 'Alert trading team']
  },
  {
    id: 'alert-3',
    type: 'validation_failed',
    severity: 'critical',
    title: 'Validation Failed',
    message: 'Critical validation checks failed for real-time market data',
    timestamp: new Date(Date.now() - 120000).toISOString(), // 2 minutes ago
    details: 'Price validation failed: Bid > Ask detected in 8 options contracts',
    recommendations: ['Halt automated trading', 'Review data integrity', 'Contact data provider']
  }
];

// Asset selector component
const AssetSelector = ({ selectedAsset, onAssetChange, availableAssets }) => {
  return (
    <Card elevation={2}>
      <CardContent>
        <Grid container spacing={2} alignItems="center">
          <Grid item>
            <Typography variant="h6" fontWeight="bold">
              Asset Selection
            </Typography>
          </Grid>
          <Grid item>
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>Symbol</InputLabel>
              <Select
                value={selectedAsset.symbol}
                label="Symbol"
                onChange={(e) => onAssetChange({ ...selectedAsset, symbol: e.target.value })}
              >
                {availableAssets.map(asset => (
                  <MenuItem key={asset.symbol} value={asset.symbol}>
                    {asset.symbol} - {asset.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item>
            <FormControl size="small" sx={{ minWidth: 100 }}>
              <InputLabel>Type</InputLabel>
              <Select
                value={selectedAsset.type}
                label="Type"
                onChange={(e) => onAssetChange({ ...selectedAsset, type: e.target.value })}
              >
                <MenuItem value="equity">Equity</MenuItem>
                <MenuItem value="etf">ETF</MenuItem>
                <MenuItem value="index">Index</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item>
            <TextField
              label="Expiration"
              type="date"
              size="small"
              value={selectedAsset.expiration}
              onChange={(e) => onAssetChange({ ...selectedAsset, expiration: e.target.value })}
              InputLabelProps={{ shrink: true }}
            />
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );
};

// Historical analysis component
const HistoricalAnalysis = ({ historicalData, onExportData }) => {
  const plotData = [
    {
      x: historicalData?.dates || [],
      y: historicalData?.overall_scores || [],
      type: 'scatter',
      mode: 'lines+markers',
      name: 'Overall Quality',
      line: { color: '#2196f3' },
    },
    {
      x: historicalData?.dates || [],
      y: historicalData?.completeness || [],
      type: 'scatter',
      mode: 'lines',
      name: 'Completeness',
      line: { color: '#4caf50' },
    },
    {
      x: historicalData?.dates || [],
      y: historicalData?.coverage || [],
      type: 'scatter',
      mode: 'lines',
      name: 'Coverage',
      line: { color: '#ff9800' },
    }
  ];

  const layout = {
    title: 'Data Quality Trends (30 Days)',
    xaxis: { title: 'Date' },
    yaxis: { title: 'Score (%)', range: [0, 100] },
    height: 400,
    margin: { t: 40, r: 20, b: 40, l: 40 },
    showlegend: true,
    legend: { x: 0, y: 1 }
  };

  return (
    <Card elevation={2}>
      <CardHeader
        avatar={<TrendingUp />}
        title="Historical Analysis"
        subheader="30-day data quality performance trends"
        action={
          <Tooltip title="Export historical data">
            <IconButton onClick={onExportData}>
              <Download />
            </IconButton>
          </Tooltip>
        }
      />
      <CardContent>
        <Plot data={plotData} layout={layout} style={{ width: '100%' }} />
      </CardContent>
    </Card>
  );
};

// System health component
const SystemHealth = ({ systemStatus }) => {
  const statusConfig = {
    healthy: { color: '#4caf50', label: 'Healthy', icon: '✓' },
    degraded: { color: '#ff9800', label: 'Degraded', icon: '⚠' },
    down: { color: '#f44336', label: 'Down', icon: '✗' }
  };

  const systems = [
    { name: 'Market Data Provider', status: systemStatus?.marketData || 'healthy' },
    { name: 'Options Data Feed', status: systemStatus?.optionsData || 'healthy' },
    { name: 'Validation Engine', status: systemStatus?.validation || 'degraded' },
    { name: 'Real-time Processing', status: systemStatus?.realTime || 'healthy' },
    { name: 'Data Storage', status: systemStatus?.storage || 'healthy' }
  ];

  return (
    <Card elevation={2}>
      <CardHeader
        avatar={<Security />}
        title="System Health"
        subheader="Data pipeline component status"
      />
      <CardContent>
        <Stack spacing={2}>
          {systems.map((system, index) => {
            const config = statusConfig[system.status] || statusConfig.down;
            return (
              <Box key={index} display="flex" justifyContent="space-between" alignItems="center">
                <Typography variant="body2">
                  {system.name}
                </Typography>
                <Chip
                  icon={<span>{config.icon}</span>}
                  label={config.label}
                  size="small"
                  sx={{
                    backgroundColor: config.color,
                    color: 'white',
                    fontWeight: 'bold',
                    '& .MuiChip-icon': { color: 'white' }
                  }}
                />
              </Box>
            );
          })}
        </Stack>
      </CardContent>
    </Card>
  );
};

// Main Data Quality page component
const DataQualityPage = () => {
  // State management
  const [qualityData, setQualityData] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [realTimeEnabled, setRealTimeEnabled] = useState(false);
  const [selectedAsset, setSelectedAsset] = useState({
    symbol: 'SPY',
    type: 'etf',
    expiration: new Date().toISOString().split('T')[0]
  });

  // WebSocket connection for real-time updates
  const {
    connectionState,
    isConnected,
    qualityData: wsQualityData,
    lastUpdate,
    requestUpdate,
    subscribeToAsset
  } = useDataQualityWebSocket('ws://localhost:8511/ws/data-quality', {
    autoReconnect: true,
    onConnect: () => console.log('Connected to data quality WebSocket'),
    onError: (error) => console.error('WebSocket error:', error)
  });

  // Mock available assets
  const availableAssets = [
    { symbol: 'SPY', name: 'SPDR S&P 500 ETF' },
    { symbol: 'QQQ', name: 'Invesco QQQ ETF' },
    { symbol: 'AAPL', name: 'Apple Inc.' },
    { symbol: 'TSLA', name: 'Tesla Inc.' },
    { symbol: 'MSFT', name: 'Microsoft Corporation' }
  ];

  // Load initial data
  const fetchQualityData = useCallback(async () => {
    setLoading(true);
    try {
      // In a real implementation, this would be an API call
      // const response = await axios.get(`/api/data-quality/${selectedAsset.symbol}`);

      // Using mock data for demonstration
      await new Promise(resolve => setTimeout(resolve, 1000)); // Simulate API delay
      const mockData = generateMockQualityData();
      setQualityData(mockData);

      // Load mock alerts
      const mockAlerts = generateMockAlerts();
      setAlerts(mockAlerts);

    } catch (error) {
      console.error('Error fetching quality data:', error);
    } finally {
      setLoading(false);
    }
  }, [selectedAsset]);

  // Handle real-time toggle
  const handleToggleRealTime = useCallback((enabled) => {
    setRealTimeEnabled(enabled);
    if (enabled && isConnected) {
      subscribeToAsset(selectedAsset.symbol, selectedAsset.type);
    }
  }, [isConnected, subscribeToAsset, selectedAsset]);

  // Handle asset change
  const handleAssetChange = useCallback((newAsset) => {
    setSelectedAsset(newAsset);
    if (realTimeEnabled && isConnected) {
      subscribeToAsset(newAsset.symbol, newAsset.type);
    }
  }, [realTimeEnabled, isConnected, subscribeToAsset]);

  // Handle alert dismissal
  const handleDismissAlert = useCallback((alertId) => {
    setAlerts(prev => prev.filter(alert => alert.id !== alertId));
  }, []);

  // Handle alert details view
  const handleViewAlertDetails = useCallback((alert) => {
    // In a real implementation, this would show a detailed modal or navigate to details page
    console.log('View alert details:', alert);
  }, []);

  // Export data functionality
  const handleExportData = useCallback(() => {
    // In a real implementation, this would export data to CSV/Excel
    console.log('Export data requested');
  }, []);

  // Initial data load
  useEffect(() => {
    fetchQualityData();
  }, [fetchQualityData]);

  // Update data when WebSocket receives new data
  useEffect(() => {
    if (wsQualityData && realTimeEnabled) {
      setQualityData(wsQualityData);
    }
  }, [wsQualityData, realTimeEnabled]);

  // Mock historical data for demonstration
  const mockHistoricalData = {
    dates: ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05'],
    overall_scores: [75, 78, 72, 80, 76],
    completeness: [82, 85, 79, 88, 83],
    coverage: [68, 71, 65, 72, 69]
  };

  const mockSystemStatus = {
    marketData: 'healthy',
    optionsData: 'healthy',
    validation: 'degraded',
    realTime: 'healthy',
    storage: 'healthy'
  };

  return (
    <Box>
      {/* Page Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box>
          <Typography variant="h4" fontWeight="bold" gutterBottom>
            Data Quality Monitoring
          </Typography>
          <Typography variant="subtitle1" color="text.secondary">
            Real-time monitoring and analysis of trading data quality
          </Typography>
        </Box>
        <Stack direction="row" spacing={2}>
          <Chip
            icon={isConnected ? <Speed /> : <Schedule />}
            label={isConnected ? 'Connected' : 'Connecting...'}
            color={isConnected ? 'success' : 'warning'}
            variant="outlined"
          />
          <Button
            variant="outlined"
            startIcon={<Refresh />}
            onClick={fetchQualityData}
            disabled={loading}
          >
            Refresh
          </Button>
          <Button
            variant="outlined"
            startIcon={<Settings />}
          >
            Settings
          </Button>
        </Stack>
      </Box>

      {/* Asset Selection */}
      <Box mb={3}>
        <AssetSelector
          selectedAsset={selectedAsset}
          onAssetChange={handleAssetChange}
          availableAssets={availableAssets}
        />
      </Box>

      {/* Main Dashboard */}
      <Box mb={3}>
        <DataQualityDashboard
          qualityData={qualityData}
          onRefresh={fetchQualityData}
          realTimeEnabled={realTimeEnabled}
          onToggleRealTime={handleToggleRealTime}
          showHistoricalTrends={true}
        />
      </Box>

      {/* Alerts Section */}
      <Box mb={3}>
        <DataQualityAlerts
          alerts={alerts}
          onDismissAlert={handleDismissAlert}
          onViewAlertDetails={handleViewAlertDetails}
          showToasts={true}
          maxDisplayedAlerts={5}
        />
      </Box>

      {/* Bottom Grid - Historical Analysis and System Health */}
      <Grid container spacing={3}>
        <Grid item xs={12} md={8}>
          <HistoricalAnalysis
            historicalData={mockHistoricalData}
            onExportData={handleExportData}
          />
        </Grid>
        <Grid item xs={12} md={4}>
          <SystemHealth systemStatus={mockSystemStatus} />
        </Grid>
      </Grid>
    </Box>
  );
};

export default DataQualityPage;