import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import PortfolioPage from './Portfolio';

jest.mock('axios', () => ({
  get: jest.fn(),
  post: jest.fn(),
}));

jest.mock('../hooks/useTaskPolling', () => ({
  useTaskPolling: () => ({
    startTask: jest.fn(),
    loading: false,
    taskStatus: null,
    error: null,
    result: null,
  }),
}));

const axios = require('axios');

const stock = (symbol, position, unrealized = 0) => ({
  symbol,
  position,
  avgCost: Math.abs(position) * 10,
  marketValue: position * 12,
  unrealizedPNL: unrealized,
  contract_type: 'Stock',
});

const baseSummary = {
  market_value: 100000,
  unrealized_pnl: 50,
  realized_pnl_today: 0,
  available_cash: 10000,
  pnl_today: 10,
};

const mockPairPayload = {
  summary: baseSummary,
  positions: {
    options: {},
    stocks: [stock('KO', -100, 10), stock('PEP', 50, -5), stock('AAPL', 10, 2)],
    others: [],
  },
  underlying_spot_prices: {},
  action_hints: { close_now: [], strategy_exit_evals: {} },
  stock_pairs: {
    pairs: [
      {
        pair_id: 'KO_PEP',
        ticker1: 'KO',
        ticker2: 'PEP',
        status: 'size_mismatch',
        last_trade_at: '2026-09-01T14:32:00+00:00',
        combined_unrealized_pnl: 5,
        overlapping_pairs: [],
        legs: [
          {
            symbol: 'KO',
            role: 'ticker1',
            log_outstanding: -120,
            broker_qty: -100,
            qty_match: false,
            present_at_broker: true,
            position: stock('KO', -100, 10),
          },
          {
            symbol: 'PEP',
            role: 'ticker2',
            log_outstanding: 50,
            broker_qty: 50,
            qty_match: true,
            present_at_broker: true,
            position: stock('PEP', 50, -5),
          },
        ],
      },
    ],
    dangling: [stock('AAPL', 10, 2)],
  },
  stock_pairs_error: null,
};

describe('Portfolio stock pairs', () => {
  beforeEach(() => {
    axios.get.mockReset();
    axios.post.mockReset();
    axios.get.mockImplementation((url) => {
      if (url === '/api/portfolio/open-positions') {
        return Promise.resolve({ data: mockPairPayload });
      }
      if (url === '/api/portfolio/recent-orders') {
        return Promise.resolve({ data: [] });
      }
      if (url === '/api/portfolio/tracked-orders') {
        return Promise.resolve({ data: [] });
      }
      return Promise.reject(new Error(`Unexpected GET ${url}`));
    });
  });

  test('renders pair cards, size mismatch, and dangling banner', async () => {
    render(<PortfolioPage />);

    expect(await screen.findByTestId('stock-pairs-section')).toBeInTheDocument();
    expect(screen.getByTestId('pair-card-KO_PEP')).toBeInTheDocument();
    expect(screen.getByTestId('pair-status-KO_PEP')).toHaveTextContent('Size mismatch');
    expect(screen.getByText('mismatch')).toBeInTheDocument();
    expect(screen.getByTestId('dangling-stocks-section')).toBeInTheDocument();
    expect(screen.getByText(/not part of any open pair trade log/i)).toBeInTheDocument();
    expect(screen.getByText('AAPL')).toBeInTheDocument();
  });

  test('falls back to flat stock table when stock_pairs is absent', async () => {
    axios.get.mockImplementation((url) => {
      if (url === '/api/portfolio/open-positions') {
        return Promise.resolve({
          data: {
            summary: baseSummary,
            positions: {
              options: {},
              stocks: [stock('MSFT', 5)],
              others: [],
            },
            underlying_spot_prices: {},
            action_hints: { close_now: [], strategy_exit_evals: {} },
          },
        });
      }
      if (url === '/api/portfolio/recent-orders') {
        return Promise.resolve({ data: [] });
      }
      if (url === '/api/portfolio/tracked-orders') {
        return Promise.resolve({ data: [] });
      }
      return Promise.reject(new Error(`Unexpected GET ${url}`));
    });

    render(<PortfolioPage />);

    expect(await screen.findByText('Stock Positions')).toBeInTheDocument();
    expect(screen.getByText('MSFT')).toBeInTheDocument();
    expect(screen.queryByTestId('stock-pairs-section')).not.toBeInTheDocument();
  });

  test('closes a dangling stock position', async () => {
    axios.post.mockResolvedValue({
      data: {
        status: 'submitted',
        filled: 10,
        quantity_closed: 10,
      },
    });

    render(<PortfolioPage />);

    await screen.findByTestId('dangling-stocks-section');
    const closeButtons = screen.getAllByRole('button', { name: 'Close Position' });
    // AAPL is the dangling row; pair legs also have close buttons — click the last one (dangling table)
    fireEvent.click(closeButtons[closeButtons.length - 1]);

    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith('/api/portfolio/close-stock-position', {
        symbol: 'AAPL',
        quantity: 10,
      });
    });
  });
});
