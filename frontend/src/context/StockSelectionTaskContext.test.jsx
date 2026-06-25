import React from 'react';
import { render, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { StockSelectionTaskProvider } from './StockSelectionTaskContext';

jest.mock('axios', () => ({
  get: jest.fn(),
  post: jest.fn(),
}));

const axios = require('axios');

const TestConsumer = () => <div>loaded</div>;

describe('StockSelectionTaskProvider', () => {
  beforeEach(() => {
    localStorage.clear();
    axios.get.mockImplementation((url) => {
      if (url === '/api/stock-selection/health') {
        return Promise.resolve({ data: { status: 'healthy' } });
      }
      if (url.startsWith('/api/tasks/') && url.endsWith('/result')) {
        return Promise.resolve({ data: { result: { status: 'success' } } });
      }
      if (url.startsWith('/api/tasks/')) {
        return Promise.resolve({
          data: {
            task: {
              state: 'SUCCESS',
              progress: 100,
              message: 'Completed',
            },
          },
        });
      }
      return Promise.reject(new Error(`Unexpected GET ${url}`));
    });
    axios.post.mockResolvedValue({
      data: { task_id: 'task-123' },
    });
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  test('does not start refresh when snapshot is healthy', async () => {
    render(
      <StockSelectionTaskProvider endPollingWhenProviderUnmounts>
        <TestConsumer />
      </StockSelectionTaskProvider>
    );

    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledWith('/api/stock-selection/health');
    });
    expect(axios.post).not.toHaveBeenCalled();
  });

  test('starts background refresh when snapshot is stale', async () => {
    axios.get.mockImplementation((url) => {
      if (url === '/api/stock-selection/health') {
        return Promise.resolve({ data: { status: 'stale', age_minutes: 2000 } });
      }
      if (url.startsWith('/api/tasks/') && url.endsWith('/result')) {
        return Promise.resolve({ data: { result: { status: 'success' } } });
      }
      if (url.startsWith('/api/tasks/')) {
        return Promise.resolve({
          data: {
            task: {
              state: 'SUCCESS',
              progress: 100,
              message: 'Completed',
            },
          },
        });
      }
      return Promise.reject(new Error(`Unexpected GET ${url}`));
    });

    render(
      <StockSelectionTaskProvider endPollingWhenProviderUnmounts>
        <TestConsumer />
      </StockSelectionTaskProvider>
    );

    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith('/api/stock-selection/run/async', {
        force: false,
        max_tickers: 800,
        top_n_per_group: 10,
        strategy_id: 'peer_v1',
      });
    });
  });

  test('skips auto refresh when a task is already persisted', async () => {
    localStorage.setItem(
      'stock_selection_active_task',
      JSON.stringify({ taskId: 'existing-task', taskName: 'Stock Selection' })
    );

    render(
      <StockSelectionTaskProvider endPollingWhenProviderUnmounts>
        <TestConsumer />
      </StockSelectionTaskProvider>
    );

    await waitFor(() => {
      expect(axios.get).not.toHaveBeenCalledWith('/api/stock-selection/health');
    });
    expect(axios.post).not.toHaveBeenCalledWith('/api/stock-selection/run/async', expect.any(Object));
  });
});
