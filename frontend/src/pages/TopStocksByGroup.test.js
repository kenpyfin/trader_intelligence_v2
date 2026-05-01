import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter } from 'react-router-dom';
import TopStocksByGroup from './TopStocksByGroup';

jest.mock('axios', () => ({
  get: jest.fn(),
  post: jest.fn(),
}));
const axios = require('axios');

const mockPayload = {
  metadata: {
    generated_at: '2026-05-01T12:00:00Z',
    tickers_considered: 100,
    tickers_ranked: 80,
    tickers_excluded: 20,
  },
  clusters: [
    {
      group_key: 'C001',
      group_label: 'Cluster C001',
      stocks: [
        {
          ticker: 'AAPL',
          selection_score: 0.91,
          cluster_rank: 1,
          global_rank: 1,
          confidence_score: 0.82,
          regime_bucket: 'calm_trend',
        },
      ],
    },
  ],
  sectors: [],
  regimes: [],
};

describe('TopStocksByGroup page', () => {
  beforeEach(() => {
    axios.get.mockResolvedValue({
      data: {
        status: 'success',
        payload: mockPayload,
      },
    });
    axios.post.mockResolvedValue({
      data: {
        status: 'success',
      },
    });
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  test('renders default clusters view and supports tab switching', async () => {
    render(
      <MemoryRouter>
        <TopStocksByGroup />
      </MemoryRouter>
    );
    expect(screen.getByText(/Top Stocks By Group/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Cluster C001')).toBeInTheDocument();
      expect(screen.getByText('AAPL')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Analyze/i })).toBeInTheDocument();
      expect(screen.getByRole('link', { name: 'AAPL' })).toHaveAttribute('href', expect.stringContaining('finviz.com/quote.ashx?t=AAPL'));
    });

    fireEvent.click(screen.getByRole('tab', { name: /Sectors/i }));
    await waitFor(() => {
      expect(axios.get).toHaveBeenCalled();
    });
  });
});

