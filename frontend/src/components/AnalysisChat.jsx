import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Chip,
  CircularProgress,
  IconButton,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import SendIcon from '@mui/icons-material/Send';
import RestartAltIcon from '@mui/icons-material/RestartAlt';

const buildWelcomeMessage = (analysis) => {
  const ticker = (analysis?.ticker || 'this ticker').toUpperCase();
  const bias = analysis?.final_bias || 'Unknown';
  const dte = analysis?.dte ?? '—';
  return {
    role: 'assistant',
    content: `I've loaded the ${ticker} analysis (${bias}, DTE ${dte} days). Ask about the thesis, risks, strategies, or any figure in this result.`,
  };
};

const AnalysisChat = ({ analysis, model = 'gemini-2.5-flash', threadKey }) => {
  const resolvedThreadKey = threadKey
    || `${analysis?.ticker || ''}-${analysis?.dte ?? ''}-${analysis?.expiration_date || ''}`;
  const [messages, setMessages] = useState(() => [buildWelcomeMessage(analysis)]);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const listRef = useRef(null);

  useEffect(() => {
    setMessages([buildWelcomeMessage(analysis)]);
    setDraft('');
    setError('');
    setSending(false);
    // Reset when the loaded result identity changes, not on every parent render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedThreadKey]);

  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, sending]);

  const ticker = (analysis?.ticker || '').toUpperCase() || 'TICKER';
  const bias = analysis?.final_bias || 'Unknown';
  const dte = analysis?.dte ?? '—';

  const handleClear = () => {
    setMessages([buildWelcomeMessage(analysis)]);
    setDraft('');
    setError('');
  };

  const handleSend = async () => {
    const content = draft.trim();
    if (!content || sending) return;

    const chatModel = /^gemini/i.test(model || '') ? model : 'gemini-2.5-flash';
    const userMessage = { role: 'user', content };
    const nextMessages = [...messages, userMessage];
    setMessages(nextMessages);
    setDraft('');
    setError('');
    setSending(true);

    try {
      const response = await axios.post('/api/analysis/chat', {
        analysis,
        messages: nextMessages,
        model: chatModel,
      });
      const reply = response.data?.reply;
      if (!reply) {
        throw new Error('Empty chat reply');
      }
      setMessages((prev) => [...prev, { role: 'assistant', content: reply }]);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : (err.message || 'Failed to send message'));
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  };

  return (
    <Card sx={{ mb: 3, boxShadow: 3 }}>
      <CardHeader
        title="Ask about this analysis"
        action={(
          <Stack direction="row" spacing={1} alignItems="center" sx={{ pr: 1 }}>
            <Chip
              size="small"
              color="primary"
              variant="outlined"
              label={`Context loaded: ${ticker} · ${bias} · DTE ${dte}`}
            />
            <Tooltip title="Clear conversation">
              <span>
                <IconButton
                  aria-label="Clear conversation"
                  onClick={handleClear}
                  disabled={sending}
                  size="small"
                >
                  <RestartAltIcon fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
          </Stack>
        )}
        titleTypographyProps={{ variant: 'h6', fontWeight: 'bold' }}
        sx={{ borderBottom: '1px solid #eee', pb: 1 }}
      />
      <CardContent>
        <Box
          ref={listRef}
          sx={{
            maxHeight: 360,
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: 1.5,
            mb: 2,
            pr: 0.5,
          }}
        >
          {messages.map((message, index) => {
            const isUser = message.role === 'user';
            return (
              <Box
                key={`${message.role}-${index}`}
                sx={{
                  alignSelf: isUser ? 'flex-end' : 'flex-start',
                  maxWidth: '85%',
                  bgcolor: isUser ? 'primary.main' : '#f8fafc',
                  color: isUser ? 'primary.contrastText' : 'text.primary',
                  border: isUser ? 'none' : '1px solid',
                  borderColor: 'divider',
                  borderRadius: 2,
                  px: 1.5,
                  py: 1,
                }}
              >
                {isUser ? (
                  <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                    {message.content}
                  </Typography>
                ) : (
                  <Box
                    sx={{
                      '& p': { m: 0, mb: 1 },
                      '& p:last-child': { mb: 0 },
                      '& ul': { pl: 2, mb: 1 },
                    }}
                  >
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {message.content}
                    </ReactMarkdown>
                  </Box>
                )}
              </Box>
            );
          })}
          {sending && (
            <Stack direction="row" spacing={1} alignItems="center" sx={{ color: 'text.secondary' }}>
              <CircularProgress size={16} />
              <Typography variant="caption">Thinking…</Typography>
            </Stack>
          )}
        </Box>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>
            {error}
          </Alert>
        )}

        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'flex-end' }}>
          <TextField
            label="Ask a follow-up"
            placeholder="Why this bias? What is the main risk?"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            multiline
            minRows={2}
            maxRows={6}
            fullWidth
            disabled={sending}
          />
          <Button
            variant="contained"
            onClick={handleSend}
            disabled={sending || !draft.trim()}
            startIcon={sending ? <CircularProgress size={16} color="inherit" /> : <SendIcon />}
            sx={{ minWidth: 112, cursor: 'pointer' }}
          >
            Send
          </Button>
        </Stack>
      </CardContent>
    </Card>
  );
};

export default AnalysisChat;
