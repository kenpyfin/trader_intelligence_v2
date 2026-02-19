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
  Stack,
  Tooltip
} from '@mui/material';
import {
  ExpandMore,
  ExpandLess,
  Warning,
  Error,
  CheckCircle,
  Info,
  TrendingDown,
  TrendingUp,
  Help
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
  onProceedWithCaution,
  allowCaution = false,
  showRetryOptions = true
}) => {
  const [expanded, setExpanded] = useState(false);

  if (!qualityData) return null;

  const {
    overall_quality_level = 'failed',
    combined_score = 0,
    completeness_score = 0,
    quality_score = 0,
    overlap_score = 0,
    pass_threshold = 0.6,
    issues = [],
    recommendations = [],
    asset_type = 'standard',
    strike_count = 0,
    valid_strikes = 0
  } = qualityData;

  const qualityConfig = QUALITY_LEVELS[overall_quality_level] || QUALITY_LEVELS.failed;
  const IconComponent = qualityConfig.icon;

  const canProceedWithCaution = allowCaution &&
    (overall_quality_level === 'acceptable' || overall_quality_level === 'poor') &&
    combined_score >= 0.35; // Minimum threshold for caution mode

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
        {/* Overall Score */}
        <Box mb={2}>
          <QualityScoreBar
            label="Overall Quality Score"
            score={combined_score}
            color={qualityConfig.color}
            showPercentage={true}
          />
          <Box display="flex" alignItems="center" gap={1} mb={1}>
            <Typography variant="body2" color="text.secondary">
              Required Threshold: {(pass_threshold * 100).toFixed(1)}%
            </Typography>
            <Tooltip title={`This ${asset_type} asset requires a minimum quality score of ${(pass_threshold * 100).toFixed(1)}% to proceed with full analysis`}>
              <Help sx={{ fontSize: 16, color: 'text.secondary' }} />
            </Tooltip>
          </Box>
        </Box>

        {/* Action Buttons */}
        <Stack direction="row" spacing={1} mb={2}>
          {canProceedWithCaution && (
            <Button
              variant="outlined"
              color="warning"
              startIcon={<Warning />}
              onClick={onProceedWithCaution}
              size="small"
            >
              Proceed with Caution
            </Button>
          )}
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
          severity={overall_quality_level === 'failed' ? 'error' : 'warning'}
          sx={{ mb: 2 }}
        >
          <AlertTitle>Quality Summary</AlertTitle>
          Found {valid_strikes} valid strikes out of {strike_count} total strikes.
          {combined_score < pass_threshold
            ? ` Quality score of ${(combined_score * 100).toFixed(1)}% is below the required ${(pass_threshold * 100).toFixed(1)}% threshold.`
            : ` Quality score of ${(combined_score * 100).toFixed(1)}% meets requirements.`
          }
          {canProceedWithCaution && (
            <> You can proceed with caution for reduced accuracy analysis.</>
          )}
        </Alert>

        {/* Expandable Details */}
        <Collapse in={expanded}>
          <Divider sx={{ mb: 2 }} />

          {/* Component Scores */}
          <Typography variant="subtitle2" gutterBottom>
            Quality Component Breakdown
          </Typography>
          <Box sx={{ mb: 3 }}>
            <QualityScoreBar
              label="Data Completeness (40% weight)"
              score={completeness_score}
              color={completeness_score >= 0.7 ? '#4caf50' : completeness_score >= 0.4 ? '#ff9800' : '#f44336'}
              showPercentage={true}
            />
            <QualityScoreBar
              label="Data Quality (40% weight)"
              score={quality_score}
              color={quality_score >= 0.7 ? '#4caf50' : quality_score >= 0.4 ? '#ff9800' : '#f44336'}
              showPercentage={true}
            />
            <QualityScoreBar
              label="Strike Coverage (20% weight)"
              score={overlap_score}
              color={overlap_score >= 0.7 ? '#4caf50' : overlap_score >= 0.4 ? '#ff9800' : '#f44336'}
              showPercentage={true}
            />
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