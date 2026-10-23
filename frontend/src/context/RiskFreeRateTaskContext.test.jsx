import React from 'react';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom';
import { RiskFreeRateTaskProvider } from './RiskFreeRateTaskContext';

jest.mock('axios', () => ({
  get: jest.fn(),
  post: jest.fn(),
}));

const axios = require('axios');

const TestConsumer = () => <div>loaded</div>;

describe('RiskFreeRateTaskProvider', () => {
  beforeEach(() => {
    localStorage.clear();
    axios.get.mockReset();
    axios.post.mockReset();
  });

  test('does not auto-start calculation on mount', () => {
    render(
      <RiskFreeRateTaskProvider endPollingWhenProviderUnmounts>
        <TestConsumer />
      </RiskFreeRateTaskProvider>
    );

    expect(axios.get).not.toHaveBeenCalled();
    expect(axios.post).not.toHaveBeenCalled();
  });
});
