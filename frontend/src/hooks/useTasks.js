import { useCallback, useMemo, useState } from 'react';

export const useTasks = () => {
  const [tasks, setTasks] = useState([]);

  const upsertTask = useCallback((task) => {
    if (!task?.id) return;
    setTasks((prev) => {
      const existingIndex = prev.findIndex((entry) => entry.id === task.id);
      if (existingIndex === -1) {
        return [task, ...prev].slice(0, 100);
      }
      const next = [...prev];
      next[existingIndex] = { ...next[existingIndex], ...task };
      return next;
    });
  }, []);

  const clearTasks = useCallback(() => setTasks([]), []);

  return useMemo(() => ({
    tasks,
    upsertTask,
    clearTasks,
  }), [tasks, upsertTask, clearTasks]);
};
