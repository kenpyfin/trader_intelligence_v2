import React from 'react';
import { RiskFreeRateHistoryChart } from '../components';

const YieldCurvePage = () => {
  return (
    <div>
      <h2 style={{ marginTop: 0, marginBottom: 12 }}>Risk-Free Rates</h2>
      <p style={{ color: '#555', marginTop: 0 }}>
        Daily market-implied risk-free rate derived from SPY, QQQ, and IWM option chains, used in analyses.
      </p>
      <RiskFreeRateHistoryChart />
    </div>
  );
};

export default YieldCurvePage;
