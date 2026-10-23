import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';

const DEFAULT_POLL_INTERVAL_MS = 2000;
export const DEFAULT_ANALYSIS_TASK_STORAGE_KEY = 'analysis_active_task';

/**
 * @param {number} [pollIntervalMs]
 * @param {{ persistedTaskStorageKey?: string, stopOnUnmount?: boolean }} [options]
 */
export const useTaskPolling = (pollIntervalMs = DEFAULT_POLL_INTERVAL_MS, options = {}) => {
  const persistedTaskStorageKey =
    options && typeof options.persistedTaskStorageKey === 'string'
      ? options.persistedTaskStorageKey
      : DEFAULT_ANALYSIS_TASK_STORAGE_KEY;
  const stopOnUnmount = options && options.stopOnUnmount === false ? false : true;

  const storageKeyRef = useRef(persistedTaskStorageKey);
  storageKeyRef.current = persistedTaskStorageKey;
  const stopOnUnmountRef = useRef(stopOnUnmount);
  stopOnUnmountRef.current = stopOnUnmount;
  const [loading, setLoading] = useState(false);
  const [taskStatus, setTaskStatus] = useState(null);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const activeTaskIdRef = useRef(null);
  const pollTimerRef = useRef(null);

  const readPersistedTask = useCallback(() => {
    try {
      const raw = localStorage.getItem(storageKeyRef.current);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed?.taskId) return null;
      return parsed;
    } catch (_error) {
      return null;
    }
  }, []);

  const persistTask = useCallback((taskId, taskName) => {
    try {
      localStorage.setItem(
        storageKeyRef.current,
        JSON.stringify({
          taskId,
          taskName,
          updatedAt: Date.now(),
        })
      );
    } catch (_error) {
      // Local storage may be blocked; continue without persistence.
    }
  }, []);

  const clearPersistedTask = useCallback(() => {
    try {
      localStorage.removeItem(storageKeyRef.current);
    } catch (_error) {
      // Ignore storage cleanup failures.
    }
  }, []);

  const stopPolling = useCallback((clearStoredTask = false) => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    activeTaskIdRef.current = null;
    if (clearStoredTask) {
      clearPersistedTask();
    }
  }, [clearPersistedTask]);

  const fetchTaskStatus = useCallback(async (taskId) => {
    const statusResponse = await axios.get(`/api/tasks/${encodeURIComponent(taskId)}`);
    const task = statusResponse?.data?.task;
    if (!task) {
      throw new Error('Task status response was missing task data.');
    }

    setTaskStatus(task);

    if (task.state === 'SUCCESS') {
      const resultResponse = await axios.get(`/api/tasks/${encodeURIComponent(taskId)}/result`);
      setResult(resultResponse?.data?.result ?? null);
      setLoading(false);
      stopPolling(true);
      return task.state;
    }

    if (task.state === 'FAILURE') {
      const failureMessage = task.error || 'Background task failed.';
      setError(failureMessage);
      setLoading(false);
      stopPolling(true);
    }
    return task.state;
  }, [stopPolling]);

  const beginPollingTask = useCallback(async (taskId, taskName = 'Background Task') => {
    activeTaskIdRef.current = taskId;

    setTaskStatus((prev) => ({
      name: taskName,
      state: prev?.state || 'PENDING',
      progress: prev?.progress ?? 0,
      message: prev?.message || 'Connecting to task...',
      ...(prev || {}),
    }));

    const initialState = await fetchTaskStatus(taskId);
    if (initialState === 'SUCCESS' || initialState === 'FAILURE') {
      return;
    }

    pollTimerRef.current = setInterval(() => {
      if (!activeTaskIdRef.current) {
        stopPolling();
        return;
      }
      fetchTaskStatus(activeTaskIdRef.current).catch((pollError) => {
        const message = pollError?.response?.data?.detail || pollError?.message || 'Failed to poll task status.';
        setError(message);
        setLoading(false);
        stopPolling();
      });
    }, pollIntervalMs);
  }, [fetchTaskStatus, pollIntervalMs, stopPolling]);

  const startTask = useCallback(async (submitUrl, payload, taskName = 'Background Task') => {
    stopPolling(true);
    setLoading(true);
    setError('');
    setResult(null);
    setTaskStatus({
      name: taskName,
      state: 'PENDING',
      progress: 0,
      message: 'Submitting task...',
    });

    try {
      const submitResponse = await axios.post(submitUrl, payload);
      const taskId = submitResponse?.data?.task_id;
      if (!taskId) {
        throw new Error('Submit response did not include task_id.');
      }

      persistTask(taskId, taskName);
      await beginPollingTask(taskId, taskName);
    } catch (submitError) {
      const message = submitError?.response?.data?.detail || submitError?.message || 'Failed to start task.';
      setError(message);
      setLoading(false);
      stopPolling();
    }
  }, [beginPollingTask, persistTask, stopPolling]);

  useEffect(() => {
    const persistedTask = readPersistedTask();
    if (!persistedTask?.taskId) {
      return;
    }

    setLoading(true);
    setError('');
    setTaskStatus({
      name: persistedTask.taskName || 'Analysis',
      state: 'PENDING',
      progress: 0,
      message: 'Reconnecting to running task...',
    });

    beginPollingTask(persistedTask.taskId, persistedTask.taskName || 'Analysis').catch((resumeError) => {
      const statusCode = resumeError?.response?.status;
      if (statusCode === 404) {
        clearPersistedTask();
        setLoading(false);
        return;
      }
      const message = resumeError?.response?.data?.detail || resumeError?.message || 'Failed to resume task.';
      setError(message);
      setLoading(false);
      stopPolling();
    });
  }, [beginPollingTask, clearPersistedTask, readPersistedTask, stopPolling]);

  useEffect(
    () => () => {
      if (stopOnUnmountRef.current) {
        stopPolling();
      }
    },
    [stopPolling]
  );

  return {
    startTask,
    loading,
    taskStatus,
    error,
    result,
    setError,
    stopPolling,
  };
};
