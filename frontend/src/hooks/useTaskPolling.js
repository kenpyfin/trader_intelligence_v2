import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';

const DEFAULT_POLL_INTERVAL_MS = 2000;

export const useTaskPolling = (pollIntervalMs = DEFAULT_POLL_INTERVAL_MS) => {
  const [loading, setLoading] = useState(false);
  const [taskStatus, setTaskStatus] = useState(null);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const activeTaskIdRef = useRef(null);
  const pollTimerRef = useRef(null);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    activeTaskIdRef.current = null;
  }, []);

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
      stopPolling();
      return task.state;
    }

    if (task.state === 'FAILURE') {
      const failureMessage = task.error || 'Background task failed.';
      setError(failureMessage);
      setLoading(false);
      stopPolling();
    }
    return task.state;
  }, [stopPolling]);

  const startTask = useCallback(async (submitUrl, payload, taskName = 'Background Task') => {
    stopPolling();
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

      activeTaskIdRef.current = taskId;
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
    } catch (submitError) {
      const message = submitError?.response?.data?.detail || submitError?.message || 'Failed to start task.';
      setError(message);
      setLoading(false);
      stopPolling();
    }
  }, [fetchTaskStatus, pollIntervalMs, stopPolling]);

  useEffect(() => () => stopPolling(), [stopPolling]);

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
