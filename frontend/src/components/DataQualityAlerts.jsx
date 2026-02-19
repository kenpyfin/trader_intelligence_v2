import React, { useState, useEffect } from 'react';
import {
  Alert,
  AlertTitle,
  Box,
  Button,
  Card,
  CardContent,
  Collapse,
  Divider,
  IconButton,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Snackbar,
  Stack,
  Typography,
  Chip,
  Tooltip,
  Badge
} from '@mui/material';
import {
  Close,
  Warning,
  Error,
  Info,
  CheckCircle,
  Notifications,
  NotificationsActive,
  Schedule,
  TrendingDown,
  Security,
  DataUsage
} from '@mui/icons-material';

// Alert severity configuration
const ALERT_SEVERITY = {
  critical: {
    icon: Error,
    color: '#d32f2f',
    bgColor: '#ffebee',
    label: 'Critical',
    priority: 1
  },
  high: {
    icon: Warning,
    color: '#f57c00',
    bgColor: '#fff3e0',
    label: 'High',
    priority: 2
  },
  medium: {
    icon: Warning,
    color: '#ff9800',
    bgColor: '#fff8e1',
    label: 'Medium',
    priority: 3
  },
  low: {
    icon: Info,
    color: '#1976d2',
    bgColor: '#e3f2fd',
    label: 'Low',
    priority: 4
  },
  info: {
    icon: Info,
    color: '#2196f3',
    bgColor: '#f3f9ff',
    label: 'Info',
    priority: 5
  }
};

// Alert type configuration
const ALERT_TYPES = {
  data_quality_degraded: {
    title: 'Data Quality Degraded',
    icon: TrendingDown,
    description: 'Overall data quality has fallen below acceptable thresholds'
  },
  missing_strikes: {
    title: 'Missing Strike Data',
    icon: DataUsage,
    description: 'Critical strike data is unavailable or incomplete'
  },
  validation_failed: {
    title: 'Validation Failed',
    icon: Error,
    description: 'Data validation checks have failed'
  },
  connection_issues: {
    title: 'Data Connection Issues',
    icon: Security,
    description: 'Issues with data provider connections detected'
  },
  latency_warning: {
    title: 'High Data Latency',
    icon: Schedule,
    description: 'Data updates are significantly delayed'
  }
};

// Individual alert component
const AlertItem = ({ alert, onDismiss, onViewDetails }) => {
  const severityConfig = ALERT_SEVERITY[alert.severity] || ALERT_SEVERITY.medium;
  const alertTypeConfig = ALERT_TYPES[alert.type] || {};

  const SeverityIcon = severityConfig.icon;
  const TypeIcon = alertTypeConfig.icon || Info;

  const formatTime = (timestamp) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString();
  };

  return (
    <Card
      elevation={2}
      sx={{
        mb: 1,
        borderLeft: `4px solid ${severityConfig.color}`,
        backgroundColor: severityConfig.bgColor
      }}
    >
      <CardContent sx={{ py: 2 }}>
        <Box display="flex" alignItems="flex-start" gap={2}>
          <Box display="flex" alignItems="center" gap={1}>
            <SeverityIcon sx={{ color: severityConfig.color, fontSize: 20 }} />
            <TypeIcon sx={{ color: 'text.secondary', fontSize: 18 }} />
          </Box>

          <Box flex={1}>
            <Box display="flex" alignItems="center" gap={1} mb={1}>
              <Typography variant="subtitle2" fontWeight="bold">
                {alertTypeConfig.title || alert.title}
              </Typography>
              <Chip
                label={severityConfig.label}
                size="small"
                sx={{
                  backgroundColor: severityConfig.color,
                  color: 'white',
                  fontSize: '11px',
                  height: 20
                }}
              />
              <Typography variant="caption" color="text.secondary">
                {formatTime(alert.timestamp)}
              </Typography>
            </Box>

            <Typography variant="body2" color="text.secondary" mb={1}>
              {alert.message || alertTypeConfig.description}
            </Typography>

            {alert.details && (
              <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                {alert.details}
              </Typography>
            )}

            {alert.recommendations && alert.recommendations.length > 0 && (
              <Box mt={1}>
                <Typography variant="caption" fontWeight="bold" color="primary.main">
                  Recommendations:
                </Typography>
                <List dense sx={{ mt: 0.5 }}>
                  {alert.recommendations.map((rec, index) => (
                    <ListItem key={index} sx={{ py: 0, pl: 0 }}>
                      <ListItemText
                        primary={`• ${rec}`}
                        primaryTypographyProps={{ variant: 'caption', color: 'text.secondary' }}
                      />
                    </ListItem>
                  ))}
                </List>
              </Box>
            )}
          </Box>

          <Stack direction="row" spacing={1}>
            {onViewDetails && (
              <Button
                size="small"
                variant="outlined"
                onClick={() => onViewDetails(alert)}
                sx={{ fontSize: '11px' }}
              >
                Details
              </Button>
            )}
            <IconButton
              size="small"
              onClick={() => onDismiss(alert.id)}
              sx={{ color: 'text.secondary' }}
            >
              <Close fontSize="small" />
            </IconButton>
          </Stack>
        </Box>
      </CardContent>
    </Card>
  );
};

// Toast notification component
const AlertToast = ({ alert, open, onClose }) => {
  const severityConfig = ALERT_SEVERITY[alert?.severity] || ALERT_SEVERITY.info;

  return (
    <Snackbar
      open={open}
      autoHideDuration={6000}
      onClose={onClose}
      anchorOrigin={{ vertical: 'top', horizontal: 'right' }}
    >
      <Alert
        onClose={onClose}
        severity={alert?.severity === 'critical' ? 'error' : 'warning'}
        variant="filled"
        sx={{
          borderLeft: `4px solid ${severityConfig.color}`,
          '& .MuiAlert-icon': {
            color: 'white'
          }
        }}
      >
        <AlertTitle sx={{ fontWeight: 'bold' }}>
          {ALERT_TYPES[alert?.type]?.title || alert?.title}
        </AlertTitle>
        {alert?.message || ALERT_TYPES[alert?.type]?.description}
      </Alert>
    </Snackbar>
  );
};

// Main alerts panel component
const DataQualityAlerts = ({
  alerts = [],
  onDismissAlert,
  onViewAlertDetails,
  showToasts = true,
  maxDisplayedAlerts = 10
}) => {
  const [dismissedAlerts, setDismissedAlerts] = useState(new Set());
  const [toastAlert, setToastAlert] = useState(null);
  const [toastOpen, setToastOpen] = useState(false);

  // Sort alerts by severity and timestamp
  const sortedAlerts = alerts
    .filter(alert => !dismissedAlerts.has(alert.id))
    .sort((a, b) => {
      const severityA = ALERT_SEVERITY[a.severity]?.priority || 999;
      const severityB = ALERT_SEVERITY[b.severity]?.priority || 999;

      if (severityA !== severityB) {
        return severityA - severityB; // Lower priority number = higher severity
      }

      return new Date(b.timestamp) - new Date(a.timestamp); // Newer first
    });

  const displayedAlerts = sortedAlerts.slice(0, maxDisplayedAlerts);
  const hiddenCount = sortedAlerts.length - displayedAlerts.length;

  // Handle new alert notifications
  useEffect(() => {
    if (alerts.length === 0 || !showToasts) return;

    const latestAlert = alerts[alerts.length - 1];

    // Only show toast for critical and high severity alerts
    if (latestAlert.severity === 'critical' || latestAlert.severity === 'high') {
      if (!dismissedAlerts.has(latestAlert.id)) {
        setToastAlert(latestAlert);
        setToastOpen(true);
      }
    }
  }, [alerts, dismissedAlerts, showToasts]);

  const handleDismissAlert = (alertId) => {
    setDismissedAlerts(prev => new Set([...prev, alertId]));
    if (onDismissAlert) {
      onDismissAlert(alertId);
    }
  };

  const handleClearAll = () => {
    const allAlertIds = alerts.map(alert => alert.id);
    setDismissedAlerts(new Set(allAlertIds));
  };

  const handleToastClose = () => {
    setToastOpen(false);
  };

  const criticalCount = displayedAlerts.filter(a => a.severity === 'critical').length;
  const highCount = displayedAlerts.filter(a => a.severity === 'high').length;

  if (displayedAlerts.length === 0) {
    return (
      <Card elevation={2}>
        <CardContent>
          <Box display="flex" alignItems="center" gap={2} py={2}>
            <CheckCircle sx={{ color: '#4caf50', fontSize: 24 }} />
            <Typography variant="body1" color="text.secondary">
              No active data quality alerts
            </Typography>
          </Box>
        </CardContent>
      </Card>
    );
  }

  return (
    <Box>
      {/* Header */}
      <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
        <Box display="flex" alignItems="center" gap={2}>
          <Badge badgeContent={displayedAlerts.length} color="error">
            <NotificationsActive sx={{ color: 'text.secondary' }} />
          </Badge>
          <Typography variant="h6" fontWeight="bold">
            Data Quality Alerts
          </Typography>
        </Box>

        <Stack direction="row" spacing={1} alignItems="center">
          {criticalCount > 0 && (
            <Chip
              label={`${criticalCount} Critical`}
              size="small"
              sx={{
                backgroundColor: ALERT_SEVERITY.critical.color,
                color: 'white',
                fontWeight: 'bold'
              }}
            />
          )}
          {highCount > 0 && (
            <Chip
              label={`${highCount} High`}
              size="small"
              sx={{
                backgroundColor: ALERT_SEVERITY.high.color,
                color: 'white',
                fontWeight: 'bold'
              }}
            />
          )}
          <Button
            size="small"
            variant="outlined"
            onClick={handleClearAll}
            sx={{ fontSize: '12px' }}
          >
            Clear All
          </Button>
        </Stack>
      </Box>

      {/* Alerts List */}
      <Box>
        {displayedAlerts.map(alert => (
          <AlertItem
            key={alert.id}
            alert={alert}
            onDismiss={handleDismissAlert}
            onViewDetails={onViewAlertDetails}
          />
        ))}

        {hiddenCount > 0 && (
          <Card elevation={1}>
            <CardContent sx={{ py: 1 }}>
              <Typography variant="caption" color="text.secondary" textAlign="center" display="block">
                +{hiddenCount} more alerts (showing {maxDisplayedAlerts} most recent)
              </Typography>
            </CardContent>
          </Card>
        )}
      </Box>

      {/* Toast Notifications */}
      <AlertToast
        alert={toastAlert}
        open={toastOpen}
        onClose={handleToastClose}
      />
    </Box>
  );
};

export default DataQualityAlerts;