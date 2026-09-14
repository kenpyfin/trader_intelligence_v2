import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Snackbar,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import SaveIcon from '@mui/icons-material/Save';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import SearchIcon from '@mui/icons-material/Search';

const ROLE_COLORS = {
  system: 'primary',
  user: 'secondary',
};

const PromptConfigPage = () => {
  const [prompts, setPrompts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [activeCategory, setActiveCategory] = useState('All');
  const [savingId, setSavingId] = useState('');
  const [resettingId, setResettingId] = useState('');
  const [resetAllOpen, setResetAllOpen] = useState(false);
  const [resettingAll, setResettingAll] = useState(false);
  const [expanded, setExpanded] = useState({});
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'success' });

  const applyPayload = useCallback((items) => {
    setPrompts(items);
    const nextDrafts = {};
    items.forEach((item) => {
      nextDrafts[item.id] = item.text;
    });
    setDrafts(nextDrafts);
  }, []);

  const loadPrompts = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await axios.get('/api/config/prompts');
      const items = response.data?.prompts || [];
      applyPayload(items);
      setCategories(response.data?.categories || []);
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || 'Failed to load prompts';
      setError(typeof detail === 'string' ? detail : 'Failed to load prompts');
    } finally {
      setLoading(false);
    }
  }, [applyPayload]);

  useEffect(() => {
    loadPrompts();
  }, [loadPrompts]);

  const dirtyIds = useMemo(() => {
    const dirty = new Set();
    prompts.forEach((item) => {
      if ((drafts[item.id] ?? '') !== item.text) {
        dirty.add(item.id);
      }
    });
    return dirty;
  }, [drafts, prompts]);

  const filteredPrompts = useMemo(() => {
    const query = search.trim().toLowerCase();
    return prompts.filter((item) => {
      if (activeCategory !== 'All' && item.category !== activeCategory) {
        return false;
      }
      if (!query) {
        return true;
      }
      const haystack = [
        item.name,
        item.id,
        item.description,
        item.category,
        item.role,
        ...(item.placeholders || []),
      ]
        .join(' ')
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [prompts, search, activeCategory]);

  const showMessage = (message, severity = 'success') => {
    setSnackbar({ open: true, message, severity });
  };

  const handleSave = async (promptId) => {
    setSavingId(promptId);
    try {
      const response = await axios.put(`/api/config/prompts/${encodeURIComponent(promptId)}`, {
        text: drafts[promptId] ?? '',
      });
      const saved = response.data?.prompt;
      if (saved) {
        setPrompts((current) => current.map((item) => (item.id === promptId ? saved : item)));
        setDrafts((current) => ({ ...current, [promptId]: saved.text }));
      }
      showMessage('Prompt saved. New GPT runs will use this text.');
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || 'Failed to save prompt';
      showMessage(typeof detail === 'string' ? detail : 'Failed to save prompt', 'error');
    } finally {
      setSavingId('');
    }
  };

  const handleReset = async (promptId) => {
    setResettingId(promptId);
    try {
      const response = await axios.post(`/api/config/prompts/${encodeURIComponent(promptId)}/reset`);
      const restored = response.data?.prompt;
      if (restored) {
        setPrompts((current) => current.map((item) => (item.id === promptId ? restored : item)));
        setDrafts((current) => ({ ...current, [promptId]: restored.text }));
      }
      showMessage('Prompt reset to the built-in default.');
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || 'Failed to reset prompt';
      showMessage(typeof detail === 'string' ? detail : 'Failed to reset prompt', 'error');
    } finally {
      setResettingId('');
    }
  };

  const handleDiscard = (promptId, originalText) => {
    setDrafts((current) => ({ ...current, [promptId]: originalText }));
  };

  const handleResetAll = async () => {
    setResettingAll(true);
    try {
      const response = await axios.post('/api/config/prompts/reset-all');
      const items = response.data?.prompts || [];
      applyPayload(items);
      setResetAllOpen(false);
      showMessage('All prompts reset to built-in defaults.');
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || 'Failed to reset prompts';
      showMessage(typeof detail === 'string' ? detail : 'Failed to reset prompts', 'error');
    } finally {
      setResettingAll(false);
    }
  };

  const customizedCount = prompts.filter((item) => item.is_customized).length;

  return (
    <Box>
      <Stack
        direction={{ xs: 'column', md: 'row' }}
        spacing={2}
        alignItems={{ xs: 'flex-start', md: 'center' }}
        justifyContent="space-between"
        sx={{ mb: 2 }}
      >
        <Box>
          <Typography variant="h5" component="h1" sx={{ fontWeight: 700 }}>
            GPT Prompt Config
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, maxWidth: 720 }}>
            View and edit every system and user prompt sent to Gemini and Perplexity.
            Placeholders such as {'{ticker}'} are filled in at runtime. Saved changes apply to the next analysis run.
          </Typography>
        </Box>
        <Button
          variant="outlined"
          color="warning"
          startIcon={<RestartAltIcon />}
          onClick={() => setResetAllOpen(true)}
          disabled={loading || prompts.length === 0}
          sx={{ cursor: 'pointer' }}
        >
          Reset all to defaults
        </Button>
      </Stack>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }} alignItems={{ md: 'center' }}>
        <TextField
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search by name, id, or category"
          size="small"
          fullWidth
          inputProps={{ 'aria-label': 'Search prompts' }}
          InputProps={{
            startAdornment: <SearchIcon fontSize="small" sx={{ mr: 1, color: 'text.secondary' }} />,
          }}
        />
        <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
          {customizedCount} customized · {dirtyIds.size} unsaved
        </Typography>
      </Stack>

      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 2 }}>
        {['All', ...categories].map((category) => (
          <Chip
            key={category}
            label={category}
            clickable
            color={activeCategory === category ? 'primary' : 'default'}
            variant={activeCategory === category ? 'filled' : 'outlined'}
            onClick={() => setActiveCategory(category)}
            sx={{ cursor: 'pointer' }}
          />
        ))}
      </Stack>

      {loading && (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
          <CircularProgress aria-label="Loading prompts" />
        </Box>
      )}

      {!loading && error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {!loading && !error && filteredPrompts.length === 0 && (
        <Alert severity="info">No prompts match the current filters.</Alert>
      )}

      {!loading &&
        filteredPrompts.map((item) => {
          const draft = drafts[item.id] ?? item.text;
          const isDirty = dirtyIds.has(item.id);
          const isSaving = savingId === item.id;
          const isResetting = resettingId === item.id;
          return (
            <Accordion
              key={item.id}
              expanded={Boolean(expanded[item.id])}
              onChange={() =>
                setExpanded((current) => ({ ...current, [item.id]: !current[item.id] }))
              }
              disableGutters
              data-testid={`prompt-card-${item.id}`}
              sx={{
                mb: 1,
                border: '1px solid',
                borderColor: isDirty ? 'primary.light' : 'divider',
                '&:before': { display: 'none' },
              }}
            >
              <AccordionSummary
                expandIcon={<ExpandMoreIcon />}
                sx={{ cursor: 'pointer' }}
                data-testid={`prompt-header-${item.id}`}
              >
                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  spacing={1}
                  alignItems={{ sm: 'center' }}
                  sx={{ width: '100%', pr: 2 }}
                >
                  <Typography sx={{ fontWeight: 600, flexGrow: 1 }}>{item.name}</Typography>
                  <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                    <Chip size="small" label={item.category} variant="outlined" />
                    <Chip
                      size="small"
                      label={item.role}
                      color={ROLE_COLORS[item.role] || 'default'}
                      variant="outlined"
                    />
                    {item.is_customized && <Chip size="small" label="Customized" color="warning" />}
                    {isDirty && <Chip size="small" label="Unsaved" color="primary" />}
                  </Stack>
                </Stack>
              </AccordionSummary>
              <AccordionDetails>
                {expanded[item.id] && (
                  <>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                  {item.description}
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
                  ID: {item.id}
                  {item.updated_at ? ` · Last saved ${item.updated_at}` : ''}
                </Typography>
                {item.placeholders?.length > 0 && (
                  <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 1.5 }}>
                    {item.placeholders.map((placeholder) => (
                      <Chip
                        key={placeholder}
                        size="small"
                        variant="outlined"
                        label={`{${placeholder}}`}
                        sx={{ fontFamily: 'ui-monospace, Menlo, Monaco, Consolas, monospace' }}
                      />
                    ))}
                  </Stack>
                )}
                <TextField
                  value={draft}
                  onChange={(event) =>
                    setDrafts((current) => ({ ...current, [item.id]: event.target.value }))
                  }
                  multiline
                  minRows={10}
                  maxRows={28}
                  fullWidth
                  inputProps={{
                    'aria-label': `${item.name} prompt text`,
                    spellCheck: false,
                  }}
                  sx={{
                    '& textarea': {
                      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                      fontSize: 13,
                      lineHeight: 1.5,
                    },
                  }}
                />
                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  spacing={1}
                  alignItems={{ sm: 'center' }}
                  justifyContent="space-between"
                  sx={{ mt: 1.5 }}
                >
                  <Typography variant="caption" color="text.secondary">
                    {draft.length.toLocaleString()} characters
                  </Typography>
                  <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                    <Button
                      variant="text"
                      onClick={() => handleDiscard(item.id, item.text)}
                      disabled={!isDirty || isSaving}
                      sx={{ cursor: 'pointer' }}
                    >
                      Discard
                    </Button>
                    <Button
                      variant="outlined"
                      startIcon={<RestartAltIcon />}
                      onClick={() => handleReset(item.id)}
                      disabled={isSaving || isResetting}
                      sx={{ cursor: 'pointer' }}
                    >
                      {isResetting ? 'Resetting…' : 'Reset to default'}
                    </Button>
                    <Button
                      variant="contained"
                      startIcon={<SaveIcon />}
                      onClick={() => handleSave(item.id)}
                      disabled={!isDirty || isSaving}
                      sx={{ cursor: 'pointer' }}
                    >
                      {isSaving ? 'Saving…' : 'Save'}
                    </Button>
                  </Stack>
                </Stack>
                  </>
                )}
              </AccordionDetails>
            </Accordion>
          );
        })}

      <Dialog open={resetAllOpen} onClose={() => !resettingAll && setResetAllOpen(false)}>
        <DialogTitle>Reset all prompts?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This restores every prompt to the built-in default and discards saved customizations.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setResetAllOpen(false)} disabled={resettingAll} sx={{ cursor: 'pointer' }}>
            Cancel
          </Button>
          <Button
            color="warning"
            variant="contained"
            onClick={handleResetAll}
            disabled={resettingAll}
            sx={{ cursor: 'pointer' }}
          >
            {resettingAll ? 'Resetting…' : 'Reset all'}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={snackbar.open}
        autoHideDuration={4000}
        onClose={() => setSnackbar((current) => ({ ...current, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          onClose={() => setSnackbar((current) => ({ ...current, open: false }))}
          severity={snackbar.severity}
          sx={{ width: '100%' }}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default PromptConfigPage;
