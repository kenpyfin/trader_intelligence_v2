import React, { createContext, useCallback, useContext, useMemo } from 'react';
import { useTaskPolling } from '../hooks/useTaskPolling';

const STOCK_SELECTION_TASK_STORAGE_KEY = 'stock_selection_active_task';
const DEFAULT_AUTO_REFRESH_PAYLOAD = {
  force: false,
  max_tickers: 800,
  top_n_per_group: 10,
  strategy_id: 'peer_v1',
};

const StockSelectionTaskContext = createContext(null);

/**
 * @param {{ children: React.ReactNode, endPollingWhenProviderUnmounts?: boolean }} props
 * When `endPollingWhenProviderUnmounts` is true (e.g. tests), polling stops when the provider unmounts.
 * Default false so recomputation continues while navigating the app.
 * Daily refresh is handled by the backend background scheduler.
 */
export const StockSelectionTaskProvider = ({ children, endPollingWhenProviderUnmounts = false }) => {
  const { startTask, loading, taskStatus, error, result, setError } = useTaskPolling(2000, {
    persistedTaskStorageKey: STOCK_SELECTION_TASK_STORAGE_KEY,
    stopOnUnmount: Boolean(endPollingWhenProviderUnmounts),
  });

  const startStockSelectionRecompute = useCallback(
    (payload = DEFAULT_AUTO_REFRESH_PAYLOAD) =>
      startTask('/api/stock-selection/run/async', payload, 'Stock Selection'),
    [startTask]
  );

  const value = useMemo(
    () => ({
      recomputeLoading: loading,
      recomputeTaskStatus: taskStatus,
      recomputeError: error,
      recomputeResult: result,
      startStockSelectionRecompute,
      clearRecomputeError: () => setError(''),
    }),
    [loading, taskStatus, error, result, startStockSelectionRecompute, setError]
  );

  return (
    <StockSelectionTaskContext.Provider value={value}>
      {children}
    </StockSelectionTaskContext.Provider>
  );
};

export const useStockSelectionTask = () => {
  const ctx = useContext(StockSelectionTaskContext);
  if (!ctx) {
    throw new Error('useStockSelectionTask must be used within StockSelectionTaskProvider');
  }
  return ctx;
};
