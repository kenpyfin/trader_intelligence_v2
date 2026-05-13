import React, { useState } from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  Typography,
  Box,
  LinearProgress,
  Chip,
  Alert,
  AlertTitle,
  Collapse,
  IconButton,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Divider,
  Button,
  Stack
} from '@mui/material';
import {
  ExpandMore,
  ExpandLess,
  Warning,
  Error,
  CheckCircle,
  Info,
  TrendingUp
} from '@mui/icons-material';

// Quality level configuration
const QUALITY_LEVELS = {
  excellent: {
    color: '#4caf50',
    bgColor: '#e8f5e8',
    label: 'Excellent',
    icon: CheckCircle,
    description: 'High quality data with comprehensive coverage'
  },
  good: {
    color: '#8bc34a',
    bgColor: '#f1f8e9',
    label: 'Good',
    icon: CheckCircle,
    description: 'Good quality data with minor gaps'
  },
  acceptable: {
    color: '#ff9800',
    bgColor: '#fff3e0',
    label: 'Acceptable',
    icon: Warning,
    description: 'Acceptable quality with some limitations'
  },
  poor: {
    color: '#f44336',
    bgColor: '#ffebee',
    label: 'Poor',
    icon: Error,
    description: 'Poor quality data with significant issues'
  },
  failed: {
    color: '#d32f2f',
    bgColor: '#ffebee',
    label: 'Failed',
    icon: Error,
    description: 'Insufficient data quality for analysis'
  }
};

// Quality score progress bar component
const QualityScoreBar = ({ label, score, maxScore = 1.0, color, showPercentage = true }) => {
  const percentage = (score / maxScore) * 100;

  return (
    <Box sx={{ mb: 2 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
        <Typography variant="body2" color="text.secondary">
          {label}
        </Typography>
        <Typography variant="body2" fontWeight="bold">
          {showPercentage ? `${percentage.toFixed(1)}%` : `${score.toFixed(2)}/${maxScore}`}
        </Typography>
      </Box>
      <LinearProgress
        variant="determinate"
        value={percentage}
        sx={{
          height: 8,
          borderRadius: 4,
          backgroundColor: '#e0e0e0',
          '& .MuiLinearProgress-bar': {
            backgroundColor: color,
            borderRadius: 4,
          },
        }}
      />
    </Box>
  );
};

// Individual issue item component
const QualityIssueItem = ({ issue, severity = 'warning' }) => {
  const severityConfig = {
    error: { icon: Error, color: '#f44336' },
    warning: { icon: Warning, color: '#ff9800' },
    info: { icon: Info, color: '#2196f3' }
  };

  const config = severityConfig[severity] || severityConfig.warning;
  const IconComponent = config.icon;

  return (
    <ListItem sx={{ py: 0.5 }}>
      <ListItemIcon sx={{ minWidth: 32 }}>
        <IconComponent sx={{ color: config.color, fontSize: 20 }} />
      </ListItemIcon>
      <ListItemText
        primary={issue.description}
        secondary={issue.impact}
        primaryTypographyProps={{ variant: 'body2' }}
        secondaryTypographyProps={{ variant: 'caption', color: 'text.secondary' }}
      />
    </ListItem>
  );
};

const DataQualityCard = ({
  qualityData,
  showRetryOptions = true
}) => {
  const [expanded, setExpanded] = useState(false);

  if (!qualityData) return null;

  const {
    overall_level = 'failed',
    component_scores = { completeness: 0, quality: 0, overlap: 0 },
    issues = [],
    recommendations = [],
    total_rows = 0,
    valid_strikes_count = 0,
    complete_greeks_count = 0,
    average_spread_percentage = null,
    display_metrics = {}
  } = qualityData;

  const overall_quality_level = overall_level;
  const valid_strikes = valid_strikes_count;
  const strike_count = total_rows;
  
  const completeness_ratio = strike_count > 0 ? valid_strikes / strike_count : 0;
  const greeks_ratio = strike_count > 0 ? complete_greeks_count / strike_count : 0;
  const pricingMetrics = display_metrics?.completeness?.options_pricing || null;
  const ivMetrics = display_metrics?.completeness?.iv_data || null;
  const greeksMetrics = display_metrics?.completeness?.greeks_data || null;
  const coverageMetrics = display_metrics?.coverage?.strikes_with_call_put || null;
  const freshnessMetrics = display_metrics?.freshness || null;
  const avgAgeMinutes = freshnessMetrics?.average_age_minutes;
  const optionLastTradeNote = freshnessMetrics?.option_last_trade_note;

  const qualityConfig = QUALITY_LEVELS[overall_quality_level] || QUALITY_LEVELS.failed;
  const IconComponent = qualityConfig.icon;

  const handleToggleExpanded = () => {
    setExpanded(!expanded);
  };

  return (
    <Card
      sx={{
        mb: 2,
        borderLeft: `4px solid ${qualityConfig.color}`,
        backgroundColor: qualityConfig.bgColor
      }}
    >
      <CardHeader
        avatar={<IconComponent sx={{ color: qualityConfig.color }} />}
        title={
          <Box display="flex" alignItems="center" gap={1}>
            <Typography variant="h6" component="span">
              Data Quality Assessment
            </Typography>
            <Chip
              label={qualityConfig.label}
              size="small"
              sx={{
                backgroundColor: qualityConfig.color,
                color: 'white',
                fontWeight: 'bold'
              }}
            />
          </Box>
        }
        subheader={qualityConfig.description}
        action={
          <IconButton onClick={handleToggleExpanded}>
            {expanded ? <ExpandLess /> : <ExpandMore />}
          </IconButton>
        }
      />

      <CardContent sx={{ pt: 0 }}>
        {/* Overall Quality Snapshot */}
        <Box mb={2}>
          <Typography variant="body2" color="text.secondary">
            Raw data quality metrics are shown below (completeness, freshness, and coverage).
          </Typography>
        </Box>

        {/* Retry Options */}
        <Stack direction="row" spacing={1} mb={2}>
          {showRetryOptions && (
            <Button
              variant="outlined"
              color="primary"
              size="small"
            >
              Try Different Date
            </Button>
          )}
        </Stack>

        {/* Summary Alert */}
        <Alert
          severity="info"
          sx={{ mb: 2 }}
        >
          <AlertTitle>Data Availability Summary</AlertTitle>
          Found {valid_strikes} valid strikes out of {strike_count} total strikes.
          This card reports raw data completeness, freshness, and coverage for transparency.
        </Alert>

        {/* Expandable Details */}
        <Collapse in={expanded}>
          <Divider sx={{ mb: 2 }} />

          <Typography variant="subtitle2" gutterBottom>
            Data Status Breakdown
          </Typography>
          <Box sx={{ mb: 3 }}>
            {pricingMetrics && (
              <QualityScoreBar
                label={`Options Pricing Completeness (${pricingMetrics.complete_count} / ${pricingMetrics.total_count})`}
                score={pricingMetrics.ratio || 0}
                color={(pricingMetrics.ratio || 0) >= 0.7 ? '#4caf50' : (pricingMetrics.ratio || 0) >= 0.4 ? '#ff9800' : '#f44336'}
                showPercentage={true}
              />
            )}
            {ivMetrics && (
              <QualityScoreBar
                label={`IV Completeness (${ivMetrics.complete_count} / ${ivMetrics.total_count})`}
                score={ivMetrics.ratio || 0}
                color={(ivMetrics.ratio || 0) >= 0.7 ? '#4caf50' : (ivMetrics.ratio || 0) >= 0.4 ? '#ff9800' : '#f44336'}
                showPercentage={true}
              />
            )}
            <QualityScoreBar
              label={`Valid Strikes (${valid_strikes} / ${strike_count})`}
              score={completeness_ratio}
              color={completeness_ratio >= 0.7 ? '#4caf50' : completeness_ratio >= 0.4 ? '#ff9800' : '#f44336'}
              showPercentage={true}
            />
            <QualityScoreBar
              label={`Complete Greeks (${(greeksMetrics?.complete_count ?? complete_greeks_count)} / ${(greeksMetrics?.total_count ?? strike_count)})`}
              score={greeksMetrics?.ratio ?? greeks_ratio}
              color={(greeksMetrics?.ratio ?? greeks_ratio) >= 0.7 ? '#4caf50' : (greeksMetrics?.ratio ?? greeks_ratio) >= 0.4 ? '#ff9800' : '#f44336'}
              showPercentage={true}
            />
            {coverageMetrics && (
              <QualityScoreBar
                label={`Call/Put Strike Coverage (${coverageMetrics.count} / ${coverageMetrics.total_strikes})`}
                score={coverageMetrics.ratio || 0}
                color={(coverageMetrics.ratio || 0) >= 0.7 ? '#4caf50' : (coverageMetrics.ratio || 0) >= 0.4 ? '#ff9800' : '#f44336'}
                showPercentage={true}
              />
            )}
            {average_spread_percentage !== null && (
              <Box sx={{ mt: 1, mb: 2 }}>
                <Typography variant="body2" color="text.secondary">
                  <strong>Average Bid-Ask Spread:</strong> {(average_spread_percentage * 100).toFixed(2)}%
                </Typography>
              </Box>
            )}
            <Box sx={{ mt: 1, mb: 2 }}>
              <Typography variant="body2" color="text.secondary">
                <strong>Data Freshness:</strong>{' '}
                {avgAgeMinutes !== null && avgAgeMinutes !== undefined
                  ? `Average quote age ${avgAgeMinutes.toFixed(1)} minutes`
                  : 'Timestamp freshness not available from source data'}
              </Typography>
              {freshnessMetrics?.latest_timestamp && (
                <Typography variant="caption" color="text.secondary">
                  Latest observed quote timestamp: {freshnessMetrics.latest_timestamp}
                </Typography>
              )}
              {optionLastTradeNote && (
                <Typography variant="caption" color="text.secondary" display="block">
                  Option last trade (informational only): {optionLastTradeNote}
                </Typography>
              )}
            </Box>
          </Box>

          {/* Issues List */}
          {issues.length > 0 && (
            <Box mb={3}>
              <Typography variant="subtitle2" gutterBottom>
                Identified Issues
              </Typography>
              <List dense>
                {issues.map((issue, index) => (
                  <QualityIssueItem
                    key={index}
                    issue={issue}
                    severity={issue.severity || 'warning'}
                  />
                ))}
              </List>
            </Box>
          )}

          {/* Recommendations */}
          {recommendations.length > 0 && (
            <Box>
              <Typography variant="subtitle2" gutterBottom>
                Recommendations
              </Typography>
              <List dense>
                {recommendations.map((rec, index) => (
                  <ListItem key={index} sx={{ py: 0.5 }}>
                    <ListItemIcon sx={{ minWidth: 32 }}>
                      <TrendingUp sx={{ color: '#4caf50', fontSize: 20 }} />
                    </ListItemIcon>
                    <ListItemText
                      primary={rec}
                      primaryTypographyProps={{ variant: 'body2' }}
                    />
                  </ListItem>
                ))}
              </List>
            </Box>
          )}
        </Collapse>
      </CardContent>
    </Card>
  );
};

export default DataQualityCard;