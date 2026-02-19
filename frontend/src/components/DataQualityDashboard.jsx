import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Typography,
  Grid,
  LinearProgress,
  Chip,
  Alert,
  AlertTitle,
  IconButton,
  Collapse,
  Divider,
  Stack,
  Tooltip,
  Paper,
  Badge,
  Switch,
  FormControlLabel
} from '@mui/material';
import {
  ExpandMore,
  ExpandLess,
  Refresh,
  Warning,
  Error,
  CheckCircle,
  Info,
  TrendingUp,
  TrendingDown,
  Speed,
  Assessment,
  Timeline,
  Notifications,
  NotificationsActive,
  Shield
} from '@mui/icons-material';
import Plot from 'react-plotly.js';

// Quality level configuration with enhanced styling
const QUALITY_LEVELS = {
  excellent: {
    color: '#4caf50',
    bgColor: '#e8f5e8',
    label: 'Excellent',
    icon: CheckCircle,
    description: 'High quality data with comprehensive coverage',
    threshold: 0.9
  },
  good: {
    color: '#8bc34a',
    bgColor: '#f1f8e9',
    label: 'Good',
    icon: CheckCircle,
    description: 'Good quality data with minor gaps',
    threshold: 0.8
  },
  acceptable: {
    color: '#ff9800',
    bgColor: '#fff3e0',
    label: 'Acceptable',
    icon: Warning,
    description: 'Acceptable quality with some limitations',
    threshold: 0.6
  },
  poor: {
    color: '#f44336',
    bgColor: '#ffebee',
    label: 'Poor',
    icon: Error,
    description: 'Poor quality data with significant issues',
    threshold: 0.4
  },
  failed: {
    color: '#d32f2f',
    bgColor: '#ffebee',
    label: 'Failed',
    icon: Error,
    description: 'Insufficient data quality for analysis',
    threshold: 0
  }
};

// Enhanced metric card component
const MetricCard = ({ title, value, unit, trend, color, icon: Icon, subtitle }) => {
  const trendColor = trend > 0 ? '#4caf50' : trend < 0 ? '#f44336' : '#757575';
  const TrendIcon = trend > 0 ? TrendingUp : trend < 0 ? TrendingDown : null;

  return (
    <Card elevation={2}>
      <CardContent>
        <Box display="flex" justifyContent="space-between" alignItems="flex-start">
          <Box>
            <Typography variant="h4" sx={{ color, fontWeight: 'bold', mb: 0.5 }}>
              {value}{unit}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {title}
            </Typography>
            {subtitle && (
              <Typography variant="caption" color="text.secondary">
                {subtitle}
              </Typography>
            )}
            {trend !== 0 && TrendIcon && (
              <Box display="flex" alignItems="center" gap={0.5} mt={1}>
                <TrendIcon sx={{ color: trendColor, fontSize: 16 }} />
                <Typography variant="caption" sx={{ color: trendColor }}>
                  {Math.abs(trend).toFixed(1)}% {trend > 0 ? 'improvement' : 'decline'}
                </Typography>
              </Box>
            )}
          </Box>
          {Icon && (
            <Icon sx={{ color: 'text.secondary', fontSize: 40, opacity: 0.3 }} />
          )}
        </Box>
      </CardContent>
    </Card>
  );
};

// Strike coverage visualization component
const StrikeCoverageChart = ({ coverageData, expanded = false }) => {
  if (!coverageData || !expanded) return null;

  const plotData = [
    {
      x: coverageData.strike_prices || [],
      y: coverageData.valid_data || [],
      type: 'bar',
      name: 'Valid Data Points',
      marker: { color: '#4caf50' },
    },
    {
      x: coverageData.strike_prices || [],
      y: coverageData.missing_data || [],
      type: 'bar',
      name: 'Missing Data Points',
      marker: { color: '#f44336' },
    }
  ];

  const layout = {
    title: 'Strike Coverage Analysis',
    xaxis: { title: 'Strike Prices' },
    yaxis: { title: 'Data Points' },
    barmode: 'stack',
    height: 300,
    margin: { t: 40, r: 20, b: 40, l: 40 },
    showlegend: true,
    legend: { x: 0, y: 1 }
  };

  return (
    <Box mt={2}>
      <Plot data={plotData} layout={layout} style={{ width: '100%' }} />
    </Box>
  );
};

// Real-time validation issues component
const ValidationIssuesPanel = ({ issues = [], realTimeEnabled }) => {
  const [expanded, setExpanded] = useState(false);

  const groupedIssues = issues.reduce((acc, issue) => {
    const severity = issue.severity || 'warning';
    if (!acc[severity]) acc[severity] = [];
    acc[severity].push(issue);
    return acc;
  }, {});

  const severityConfig = {
    error: { icon: Error, color: '#f44336', label: 'Critical' },
    warning: { icon: Warning, color: '#ff9800', label: 'Warning' },
    info: { icon: Info, color: '#2196f3', label: 'Info' }
  };

  return (
    <Card elevation={2}>
      <CardHeader
        avatar={
          <Badge
            badgeContent={issues.length}
            color="error"
            invisible={issues.length === 0}
          >
            <Assessment sx={{ color: 'text.secondary' }} />
          </Badge>
        }
        title={
          <Box display="flex" alignItems="center" gap={1}>
            <Typography variant="h6">Validation Issues</Typography>
            {realTimeEnabled && (
              <Chip
                icon={<NotificationsActive />}
                label="Live"
                size="small"
                color="primary"
                variant="outlined"
              />
            )}
          </Box>
        }
        subheader={`${issues.length} active issues detected`}
        action={
          <IconButton onClick={() => setExpanded(!expanded)}>
            {expanded ? <ExpandLess /> : <ExpandMore />}
          </IconButton>
        }
      />
      <Collapse in={expanded}>
        <CardContent>
          {Object.entries(groupedIssues).map(([severity, issueList]) => {
            const config = severityConfig[severity];
            const IconComponent = config.icon;

            return (
              <Box key={severity} mb={2}>
                <Box display="flex" alignItems="center" gap={1} mb={1}>
                  <IconComponent sx={{ color: config.color, fontSize: 20 }} />
                  <Typography variant="subtitle2" sx={{ color: config.color }}>
                    {config.label} ({issueList.length})
                  </Typography>
                </Box>
                <Stack spacing={1} ml={3}>
                  {issueList.map((issue, index) => (
                    <Paper
                      key={index}
                      elevation={1}
                      sx={{
                        p: 2,
                        borderLeft: `3px solid ${config.color}`,
                        backgroundColor: `${config.color}08`
                      }}
                    >
                      <Typography variant="body2" fontWeight="bold">
                        {issue.description}
                      </Typography>
                      {issue.impact && (
                        <Typography variant="caption" color="text.secondary">
                          Impact: {issue.impact}
                        </Typography>
                      )}
                      {issue.recommendation && (
                        <Typography variant="caption" color="primary.main" display="block" mt={0.5}>
                          💡 {issue.recommendation}
                        </Typography>
                      )}
                    </Paper>
                  ))}
                </Stack>
              </Box>
            );
          })}
          {issues.length === 0 && (
            <Box textAlign="center" py={2}>
              <CheckCircle sx={{ color: '#4caf50', fontSize: 48, mb: 1 }} />
              <Typography variant="body2" color="text.secondary">
                No validation issues detected
              </Typography>
            </Box>
          )}
        </CardContent>
      </Collapse>
    </Card>
  );
};

// Historical quality trends component
const QualityTrendsChart = ({ trendsData, expanded = false }) => {
  if (!trendsData || !expanded) return null;

  const plotData = [
    {
      x: trendsData.timestamps || [],
      y: trendsData.completeness_scores || [],
      type: 'scatter',
      mode: 'lines+markers',
      name: 'Completeness',
      line: { color: '#2196f3' },
    },
    {
      x: trendsData.timestamps || [],
      y: trendsData.quality_scores || [],
      type: 'scatter',
      mode: 'lines+markers',
      name: 'Quality',
      line: { color: '#4caf50' },
    },
    {
      x: trendsData.timestamps || [],
      y: trendsData.coverage_scores || [],
      type: 'scatter',
      mode: 'lines+markers',
      name: 'Coverage',
      line: { color: '#ff9800' },
    }
  ];

  const layout = {
    title: 'Data Quality Trends (Last 24 Hours)',
    xaxis: { title: 'Time' },
    yaxis: { title: 'Score (%)', range: [0, 100] },
    height: 300,
    margin: { t: 40, r: 20, b: 40, l: 40 },
    showlegend: true,
    legend: { x: 0, y: 1 }
  };

  return (
    <Box mt={2}>
      <Plot data={plotData} layout={layout} style={{ width: '100%' }} />
    </Box>
  );
};

// Main Data Quality Dashboard Component
const DataQualityDashboard = ({
  qualityData = null,
  onRefresh,
  realTimeEnabled = false,
  onToggleRealTime,
  showHistoricalTrends = true
}) => {
  const [expanded, setExpanded] = useState(false);
  const [trendsExpanded, setTrendsExpanded] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(new Date());

  // Auto-refresh data when real-time is enabled
  useEffect(() => {
    if (!realTimeEnabled) return;

    const interval = setInterval(() => {
      if (onRefresh) {
        onRefresh();
        setLastUpdate(new Date());
      }
    }, 5000); // Refresh every 5 seconds

    return () => clearInterval(interval);
  }, [realTimeEnabled, onRefresh]);

  if (!qualityData) {
    return (
      <Card elevation={2}>
        <CardContent>
          <Box display="flex" alignItems="center" gap={2}>
            <LinearProgress sx={{ flexGrow: 1 }} />
            <Typography variant="body2" color="text.secondary">
              Loading data quality metrics...
            </Typography>
          </Box>
        </CardContent>
      </Card>
    );
  }

  const {
    overall_quality_level = 'failed',
    combined_score = 0,
    completeness_score = 0,
    quality_score = 0,
    overlap_score = 0,
    issues = [],
    strike_count = 0,
    valid_strikes = 0,
    coverage_data = null,
    trends_data = null
  } = qualityData;

  const qualityConfig = QUALITY_LEVELS[overall_quality_level] || QUALITY_LEVELS.failed;
  const coveragePercentage = strike_count > 0 ? (valid_strikes / strike_count) * 100 : 0;

  return (
    <Box>
      {/* Main Dashboard Header */}
      <Card elevation={3} sx={{ mb: 2, borderLeft: `4px solid ${qualityConfig.color}` }}>
        <CardHeader
          avatar={<Speed sx={{ color: qualityConfig.color }} />}
          title={
            <Box display="flex" alignItems="center" gap={2}>
              <Typography variant="h5" fontWeight="bold">
                Data Quality Monitoring
              </Typography>
              <Chip
                label={qualityConfig.label}
                sx={{
                  backgroundColor: qualityConfig.color,
                  color: 'white',
                  fontWeight: 'bold'
                }}
              />
              {realTimeEnabled && (
                <Chip
                  icon={<NotificationsActive />}
                  label="Real-Time"
                  color="primary"
                  variant="outlined"
                  size="small"
                />
              )}
            </Box>
          }
          subheader={`Overall Quality: ${(combined_score * 100).toFixed(1)}% • Last Updated: ${lastUpdate.toLocaleTimeString()}`}
          action={
            <Stack direction="row" spacing={1} alignItems="center">
              <FormControlLabel
                control={
                  <Switch
                    checked={realTimeEnabled}
                    onChange={(e) => onToggleRealTime && onToggleRealTime(e.target.checked)}
                    size="small"
                  />
                }
                label="Real-time"
                sx={{ mr: 1 }}
              />
              <Tooltip title="Refresh data">
                <IconButton onClick={onRefresh}>
                  <Refresh />
                </IconButton>
              </Tooltip>
              <IconButton onClick={() => setExpanded(!expanded)}>
                {expanded ? <ExpandLess /> : <ExpandMore />}
              </IconButton>
            </Stack>
          }
        />
      </Card>

      {/* Key Metrics Grid */}
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard
            title="Overall Quality"
            value={(combined_score * 100).toFixed(1)}
            unit="%"
            trend={0}
            color={qualityConfig.color}
            icon={Shield}
            subtitle={qualityConfig.description}
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard
            title="Data Completeness"
            value={(completeness_score * 100).toFixed(1)}
            unit="%"
            trend={0}
            color={completeness_score >= 0.7 ? '#4caf50' : completeness_score >= 0.4 ? '#ff9800' : '#f44336'}
            icon={Assessment}
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard
            title="Strike Coverage"
            value={coveragePercentage.toFixed(1)}
            unit="%"
            trend={0}
            color={overlap_score >= 0.7 ? '#4caf50' : overlap_score >= 0.4 ? '#ff9800' : '#f44336'}
            icon={Timeline}
            subtitle={`${valid_strikes}/${strike_count} strikes`}
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard
            title="Active Issues"
            value={issues.length}
            unit=""
            trend={0}
            color={issues.length === 0 ? '#4caf50' : issues.length < 5 ? '#ff9800' : '#f44336'}
            icon={Warning}
            subtitle={issues.length === 0 ? 'All clear' : 'Needs attention'}
          />
        </Grid>
      </Grid>

      {/* Validation Issues Panel */}
      <ValidationIssuesPanel issues={issues} realTimeEnabled={realTimeEnabled} />

      {/* Expanded Details */}
      <Collapse in={expanded}>
        <Box mt={2}>
          {/* Historical Trends */}
          {showHistoricalTrends && (
            <Card elevation={2} sx={{ mb: 2 }}>
              <CardHeader
                avatar={<Timeline />}
                title="Quality Trends"
                subheader="Historical data quality performance"
                action={
                  <IconButton onClick={() => setTrendsExpanded(!trendsExpanded)}>
                    {trendsExpanded ? <ExpandLess /> : <ExpandMore />}
                  </IconButton>
                }
              />
              <Collapse in={trendsExpanded}>
                <CardContent>
                  <QualityTrendsChart trendsData={trends_data} expanded={trendsExpanded} />
                </CardContent>
              </Collapse>
            </Card>
          )}

          {/* Strike Coverage Analysis */}
          <Card elevation={2}>
            <CardHeader
              avatar={<Assessment />}
              title="Strike Coverage Analysis"
              subheader="Detailed breakdown of data availability across strikes"
            />
            <CardContent>
              <StrikeCoverageChart coverageData={coverage_data} expanded={true} />
            </CardContent>
          </Card>
        </Box>
      </Collapse>
    </Box>
  );
};

export default DataQualityDashboard;