import React, { createContext, useCallback, useContext, useMemo } from 'react';
import { useTaskPolling } from '../hooks/useTaskPolling';

const RISK_FREE_RATE_TASK_STORAGE_KEY = 'risk_free_rate_active_task';

const RiskFreeRateTaskContext = createContext(null);

/**
 * Tracks manual/async risk-free rate calculation tasks.
 * Daily refresh is handled by the backend background scheduler.
 */
export const RiskFreeRateTaskProvider = ({ children, endPollingWhenProviderUnmounts = false }) => {
  const { startTask, loading, taskStatus, error, result, setError } = useTaskPolling(2000, {
    persistedTaskStorageKey: RISK_FREE_RATE_TASK_STORAGE_KEY,
    stopOnUnmount: Boolean(endPollingWhenProviderUnmounts),
  });

  const startDailyRateCalculation = useCallback(
    () => startTask('/api/risk-free-rate/run/async', {}, 'Risk-Free Rate'),
    [startTask]
  );

  const value = useMemo(
    () => ({
      calcLoading: loading,
      calcTaskStatus: taskStatus,
      calcError: error,
      calcResult: result,
      startDailyRateCalculation,
      clearCalcError: () => setError(''),
    }),
    [loading, taskStatus, error, result, startDailyRateCalculation, setError]
  );

  return (
    <RiskFreeRateTaskContext.Provider value={value}>
      {children}
    </RiskFreeRateTaskContext.Provider>
  );
};

export const useRiskFreeRateTask = () => {
  const ctx = useContext(RiskFreeRateTaskContext);
  if (!ctx) {
    throw new Error('useRiskFreeRateTask must be used within RiskFreeRateTaskProvider');
  }
  return ctx;
};
