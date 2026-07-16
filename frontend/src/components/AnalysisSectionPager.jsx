import React from 'react';
import { Box, IconButton, Tab, Tabs, Typography } from '@mui/material';
import {
  ChevronLeft as ChevronLeftIcon,
  ChevronRight as ChevronRightIcon,
} from '@mui/icons-material';

const AnalysisSectionPager = ({
  tabs,
  activeTab,
  onTabChange,
  heading,
}) => {
  if (!tabs.length) return null;

  const activeIndex = tabs.findIndex((tab) => tab.key === activeTab);
  const safeIndex = activeIndex >= 0 ? activeIndex : 0;
  const hasPrevious = safeIndex > 0;
  const hasNext = safeIndex < tabs.length - 1;

  const goToPrevious = () => {
    if (hasPrevious) onTabChange(tabs[safeIndex - 1].key);
  };

  const goToNext = () => {
    if (hasNext) onTabChange(tabs[safeIndex + 1].key);
  };

  return (
    <Box sx={{ mb: 2 }}>
      {heading && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: 'block', mb: 0.75, fontWeight: 600 }}
        >
          {heading}
        </Typography>
      )}

      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 0.5,
          borderBottom: 1,
          borderColor: 'divider',
          bgcolor: 'background.paper',
          borderRadius: '8px 8px 0 0',
        }}
      >
        <IconButton
          size="small"
          onClick={goToPrevious}
          disabled={!hasPrevious}
          aria-label="Previous section"
          sx={{ ml: 0.5, cursor: hasPrevious ? 'pointer' : 'default' }}
        >
          <ChevronLeftIcon fontSize="small" />
        </IconButton>

        <Tabs
          value={activeTab}
          onChange={(_, value) => onTabChange(value)}
          variant="scrollable"
          scrollButtons="auto"
          aria-label="Analysis sections"
          sx={{
            flex: 1,
            minHeight: 44,
            '& .MuiTab-root': {
              cursor: 'pointer',
              textTransform: 'none',
              minHeight: 44,
              transition: 'color 0.2s ease',
            },
          }}
        >
          {tabs.map(({ key, label }) => (
            <Tab
              key={key}
              value={key}
              label={label}
              sx={{ fontWeight: activeTab === key ? 600 : 400 }}
            />
          ))}
        </Tabs>

        <IconButton
          size="small"
          onClick={goToNext}
          disabled={!hasNext}
          aria-label="Next section"
          sx={{ mr: 0.5, cursor: hasNext ? 'pointer' : 'default' }}
        >
          <ChevronRightIcon fontSize="small" />
        </IconButton>
      </Box>

      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>
        Section {safeIndex + 1} of {tabs.length}
      </Typography>
    </Box>
  );
};

export default AnalysisSectionPager;
