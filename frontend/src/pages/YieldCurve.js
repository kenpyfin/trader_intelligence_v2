import React from 'react';
import { RiskFreeRateHistoryChart } from '../components';

const YieldCurvePage = () => {
  return (
    <div>
      <h2 style={{ marginTop: 0, marginBottom: 12 }}>Risk-Free Rates</h2>
      <p style={{ color: '#555', marginTop: 0 }}>
        Daily ETF-implied risk-free rate history used in analyses.
      </p>
      <RiskFreeRateHistoryChart />
    </div>
  );
};

export default YieldCurvePage;
