import React from 'react';
import {
  Alert,
  AlertTitle,
  Box,
  Chip,
  Typography,
  Tooltip,
  Paper
} from '@mui/material';
import {
  Warning,
  Shield,
  ErrorOutline
} from '@mui/icons-material';

// Floating warning banner for caution mode
export const CautionBanner = ({ qualityScore, onDisableCaution }) => {
  return (
    <Alert
      severity="warning"
      sx={{
        mb: 2,
        border: '2px solid #ff9800',
        borderRadius: 2,
        backgroundColor: '#fff8e1'
      }}
      icon={<Warning />}
      action={
        onDisableCaution && (
          <Chip
            label="Exit Caution Mode"
            size="small"
            onClick={onDisableCaution}
            variant="outlined"
            color="warning"
          />
        )
      }
    >
      <AlertTitle sx={{ fontWeight: 'bold' }}>
        ⚠️ Proceeding with Caution Mode
      </AlertTitle>
      <Typography variant="body2">
        Analysis is running with <strong>{(qualityScore * 100).toFixed(1)}%</strong> data quality.
        Results may have reduced accuracy. Exercise additional scrutiny when making trading decisions.
      </Typography>
    </Alert>
  );
};

// Inline warning chip for individual components
export const CautionChip = ({ size = 'small', tooltip = null }) => {
  const chip = (
    <Chip
      icon={<Warning sx={{ fontSize: '16px !important' }} />}
      label="Caution"
      size={size}
      color="warning"
      variant="outlined"
      sx={{
        fontSize: '11px',
        height: size === 'small' ? 20 : 24,
        '& .MuiChip-icon': {
          fontSize: size === 'small' ? 14 : 16
        }
      }}
    />
  );

  if (tooltip) {
    return (
      <Tooltip title={tooltip} placement="top">
        {chip}
      </Tooltip>
    );
  }

  return chip;
};

// Warning overlay for analysis cards
export const CautionOverlay = ({ children, show = true, message }) => {
  if (!show) return children;

  return (
    <Box sx={{ position: 'relative' }}>
      {children}
      <Paper
        elevation={0}
        sx={{
          position: 'absolute',
          top: 8,
          right: 8,
          backgroundColor: 'rgba(255, 152, 0, 0.1)',
          border: '1px solid #ff9800',
          borderRadius: 1,
          p: 0.5,
          display: 'flex',
          alignItems: 'center',
          gap: 0.5,
          zIndex: 1
        }}
      >
        <Warning sx={{ color: '#ff9800', fontSize: 16 }} />
        <Typography variant="caption" color="#e65100" fontWeight="bold">
          {message || 'CAUTION'}
        </Typography>
      </Paper>
    </Box>
  );
};

// Confidence level indicator with caution styling
export const ConfidenceIndicator = ({ confidence, inCautionMode = false }) => {
  const getConfidenceColor = (conf) => {
    if (inCautionMode) {
      // Reduced confidence colors in caution mode
      switch (conf?.toLowerCase()) {
        case 'high': return '#ff9800'; // Orange instead of green
        case 'medium': return '#ff5722'; // Red-orange instead of orange
        case 'low': return '#d32f2f'; // Dark red
        default: return '#757575'; // Gray for unknown
      }
    } else {
      // Normal confidence colors
      switch (conf?.toLowerCase()) {
        case 'high': return '#4caf50'; // Green
        case 'medium': return '#ff9800'; // Orange
        case 'low': return '#f44336'; // Red
        default: return '#757575'; // Gray for unknown
      }
    }
  };

  const confidenceColor = getConfidenceColor(confidence);

  return (
    <Box display="flex" alignItems="center" gap={1}>
      <Typography variant="body2" color="text.secondary">
        Confidence:
      </Typography>
      <Chip
        label={confidence || 'Unknown'}
        size="small"
        sx={{
          backgroundColor: inCautionMode ? 'rgba(255, 152, 0, 0.1)' : 'transparent',
          color: confidenceColor,
          border: `1px solid ${confidenceColor}`,
          fontWeight: 'bold'
        }}
      />
      {inCautionMode && (
        <Tooltip title="Confidence levels are reduced due to data quality issues">
          <ErrorOutline sx={{ color: '#ff9800', fontSize: 16, ml: 0.5 }} />
        </Tooltip>
      )}
    </Box>
  );
};

// Quality-aware strategy card wrapper
export const StrategyCardWithCaution = ({
  children,
  strategy,
  inCautionMode = false,
  qualityScore = null
}) => {
  if (!inCautionMode) return children;

  return (
    <Box sx={{ position: 'relative' }}>
      {/* Caution mode styling overlay */}
      <Box
        sx={{
          border: '2px solid #ff9800',
          borderRadius: 2,
          backgroundColor: 'rgba(255, 152, 0, 0.02)',
          position: 'relative',
          '&::before': {
            content: '""',
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: 4,
            backgroundColor: '#ff9800',
            borderRadius: '2px 2px 0 0',
            zIndex: 1
          }
        }}
      >
        {children}

        {/* Floating caution indicator */}
        <Box
          sx={{
            position: 'absolute',
            top: 12,
            right: 12,
            display: 'flex',
            alignItems: 'center',
            gap: 0.5,
            backgroundColor: 'rgba(255, 152, 0, 0.9)',
            color: 'white',
            px: 1,
            py: 0.5,
            borderRadius: 1,
            fontSize: '11px',
            fontWeight: 'bold',
            zIndex: 2
          }}
        >
          <Shield sx={{ fontSize: 14 }} />
          CAUTION
        </Box>

        {/* Bottom quality score indicator */}
        {qualityScore && (
          <Box
            sx={{
              position: 'absolute',
              bottom: 8,
              left: 8,
              backgroundColor: 'rgba(255, 152, 0, 0.1)',
              border: '1px solid #ff9800',
              borderRadius: 1,
              px: 1,
              py: 0.5
            }}
          >
            <Typography variant="caption" color="#e65100" fontWeight="bold">
              Quality: {(qualityScore * 100).toFixed(1)}%
            </Typography>
          </Box>
        )}
      </Box>
    </Box>
  );
};

// Quality score badge component
export const QualityScoreBadge = ({ score, threshold = 0.6, size = 'medium' }) => {
  const getScoreColor = (score, threshold) => {
    if (score >= threshold) return '#4caf50'; // Green
    if (score >= threshold * 0.7) return '#ff9800'; // Orange
    return '#f44336'; // Red
  };

  const scoreColor = getScoreColor(score, threshold);
  const percentage = (score * 100).toFixed(1);

  return (
    <Tooltip title={`Data quality score: ${percentage}%. Threshold: ${(threshold * 100).toFixed(1)}%`}>
      <Chip
        icon={<Shield sx={{ fontSize: size === 'small' ? '14px !important' : '16px !important' }} />}
        label={`${percentage}%`}
        size={size}
        sx={{
          backgroundColor: scoreColor,
          color: 'white',
          fontWeight: 'bold',
          '& .MuiChip-icon': {
            color: 'white'
          }
        }}
      />
    </Tooltip>
  );
};

export default {
  CautionBanner,
  CautionChip,
  CautionOverlay,
  ConfidenceIndicator,
  StrategyCardWithCaution,
  QualityScoreBadge
};