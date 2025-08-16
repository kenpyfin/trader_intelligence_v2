import React from 'react';
import { YieldCurvePanel } from '../components';

const YieldCurvePage = () => {
  return (
    <div>
      <h2 style={{ marginTop: 0, marginBottom: 12 }}>Yield Curve</h2>
      <p style={{ color: '#555', marginTop: 0 }}>
        Compare Treasury curve vs ETF-implied risk-free rate and choose your default source.
      </p>
      <YieldCurvePanel />
    </div>
  );
};

export default YieldCurvePage;
