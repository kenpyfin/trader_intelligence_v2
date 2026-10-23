import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import PromptConfigPage from './PromptConfig';

jest.mock('axios', () => ({
  get: jest.fn(),
  put: jest.fn(),
  post: jest.fn(),
}));

const axios = require('axios');

const mockPrompts = [
  {
    id: 'gpt_verdict.analyst.system',
    name: 'GPT Verdict — Analyst (system)',
    category: 'GPT Verdict',
    description: 'Stage 1 analyst instructions.',
    role: 'system',
    placeholders: ['ticker'],
    text: 'You are a Senior Quantitative Analyst for {ticker}.',
    default_text: 'You are a Senior Quantitative Analyst for {ticker}.',
    is_customized: false,
    updated_at: null,
  },
  {
    id: 'exit_signal.system',
    name: 'Exit Signals — Evaluator (system)',
    category: 'Exit Signals',
    description: 'Exit condition evaluator.',
    role: 'system',
    placeholders: [],
    text: 'Custom exit prompt',
    default_text: 'Default exit prompt',
    is_customized: true,
    updated_at: '2026-09-03T12:00:00+00:00',
  },
];

describe('PromptConfig page', () => {
  beforeEach(() => {
    axios.get.mockReset();
    axios.put.mockReset();
    axios.post.mockReset();
    axios.get.mockResolvedValue({
      data: {
        status: 'success',
        prompts: mockPrompts,
        categories: ['GPT Verdict', 'Exit Signals'],
      },
    });
  });

  const renderPage = () => render(<PromptConfigPage />);

  test('lists prompts and saves an edit', async () => {
    axios.put.mockResolvedValue({
      data: {
        status: 'success',
        prompt: {
          ...mockPrompts[0],
          text: 'Edited analyst prompt for {ticker}.',
          is_customized: true,
        },
      },
    });

    renderPage();

    expect(await screen.findByText('GPT Prompt Config')).toBeInTheDocument();
    expect(await screen.findByText('GPT Verdict — Analyst (system)')).toBeInTheDocument();
    expect(screen.getByText('Customized')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('prompt-header-gpt_verdict.analyst.system'));
    const editor = await screen.findByLabelText('GPT Verdict — Analyst (system) prompt text');
    fireEvent.change(editor, { target: { value: 'Edited analyst prompt for {ticker}.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(axios.put).toHaveBeenCalledWith(
        '/api/config/prompts/gpt_verdict.analyst.system',
        { text: 'Edited analyst prompt for {ticker}.' }
      );
    });
    expect(await screen.findByText(/Prompt saved/)).toBeInTheDocument();
  });

  test('filters prompts by category', async () => {
    renderPage();
    expect(await screen.findByText('Exit Signals — Evaluator (system)')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^GPT Verdict$/ }));
    expect(screen.queryByText('Exit Signals — Evaluator (system)')).not.toBeInTheDocument();
    expect(screen.getByText('GPT Verdict — Analyst (system)')).toBeInTheDocument();
  });
});
