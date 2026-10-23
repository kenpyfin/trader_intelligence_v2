import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import AnalysisChat from './AnalysisChat';

jest.mock('axios', () => ({
  post: jest.fn(),
}));
jest.mock('react-markdown', () => ({
  __esModule: true,
  default: ({ children }) => children,
}));
jest.mock('remark-gfm', () => () => {});

const axios = require('axios');

const sampleAnalysis = {
  ticker: 'AAPL',
  final_bias: 'Bullish',
  dte: 32,
  expiration_date: '2026-10-16',
  final_conclusion_html: '<p>Trend is up</p>',
};

describe('AnalysisChat', () => {
  beforeEach(() => {
    axios.post.mockReset();
  });

  test('shows preloaded context for ticker, bias, and DTE', () => {
    render(<AnalysisChat analysis={sampleAnalysis} model="gemini-2.5-flash" />);
    expect(screen.getByText(/Context loaded: AAPL · Bullish · DTE 32/)).toBeInTheDocument();
    expect(screen.getByText(/I've loaded the AAPL analysis \(Bullish, DTE 32 days\)/)).toBeInTheDocument();
  });

  test('sends analysis context and user message, then shows the reply', async () => {
    axios.post.mockResolvedValue({
      data: { status: 'success', reply: 'Because SMA stack is aligned.', model: 'gemini-2.5-flash' },
    });

    render(<AnalysisChat analysis={sampleAnalysis} model="gemini-2.5-flash" />);
    fireEvent.change(screen.getByLabelText('Ask a follow-up'), {
      target: { value: 'Why this bias?' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledTimes(1);
    });

    const [url, payload] = axios.post.mock.calls[0];
    expect(url).toBe('/api/analysis/chat');
    expect(payload.analysis).toEqual(sampleAnalysis);
    expect(payload.model).toBe('gemini-2.5-flash');
    expect(payload.messages[payload.messages.length - 1]).toEqual({
      role: 'user',
      content: 'Why this bias?',
    });
    expect(await screen.findByText('Because SMA stack is aligned.')).toBeInTheDocument();
  });

  test('falls back to Gemini when a non-Gemini model is provided', async () => {
    axios.post.mockResolvedValue({
      data: { status: 'success', reply: 'Using Gemini.', model: 'gemini-2.5-flash' },
    });

    render(<AnalysisChat analysis={sampleAnalysis} model="sonar-pro" />);
    fireEvent.change(screen.getByLabelText('Ask a follow-up'), {
      target: { value: 'Summarize the strategy.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledTimes(1);
    });
    expect(axios.post.mock.calls[0][1].model).toBe('gemini-2.5-flash');
  });

  test('shows an error alert and keeps the user message on failure', async () => {
    axios.post.mockRejectedValue({
      response: { data: { detail: 'Gemini chat timed out' } },
      message: 'timeout',
    });

    render(<AnalysisChat analysis={sampleAnalysis} model="gemini-2.5-flash" />);
    fireEvent.change(screen.getByLabelText('Ask a follow-up'), {
      target: { value: 'What is the main risk?' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    expect(await screen.findByText('Gemini chat timed out')).toBeInTheDocument();
    expect(screen.getByText('What is the main risk?')).toBeInTheDocument();
  });
});
