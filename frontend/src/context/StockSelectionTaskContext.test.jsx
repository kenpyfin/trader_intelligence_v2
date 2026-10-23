import React from 'react';
import { render } from '@testing-library/react';
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
    axios.get.mockReset();
    axios.post.mockReset();
  });

  test('does not auto-start recompute on mount', () => {
    render(
      <StockSelectionTaskProvider endPollingWhenProviderUnmounts>
        <TestConsumer />
      </StockSelectionTaskProvider>
    );

    expect(axios.get).not.toHaveBeenCalledWith('/api/stock-selection/health');
    expect(axios.post).not.toHaveBeenCalledWith('/api/stock-selection/run/async', expect.any(Object));
  });
});
