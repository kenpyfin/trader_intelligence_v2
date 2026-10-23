import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional


TaskRunner = Callable[[], Awaitable[Any]]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class InMemoryTaskManager:
    """
    Lightweight in-process task tracking for async submit + polling flows.
    Tasks are not durable across process restarts.
    """

    def __init__(self, max_tasks: int = 500, retention_seconds: int = 3600) -> None:
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._max_tasks = max_tasks
        self._retention_seconds = retention_seconds
        self._lock = threading.Lock()

    def submit(self, name: str, runner: TaskRunner) -> str:
        task_id = str(uuid.uuid4())
        created_at = _utc_now_iso()
        task_record = {
            "id": task_id,
            "name": name,
            "state": "PENDING",
            "progress": 0,
            "message": "Queued",
            "created_at": created_at,
            "updated_at": created_at,
            "completed_at": None,
            "error": None,
            "result": None,
        }
        with self._lock:
            self._tasks[task_id] = task_record
            self._cleanup_locked()

        async def _execute() -> None:
            self._update(task_id, state="STARTED", progress=10, message="Running")
            try:
                result = await runner()
                self._update(
                    task_id,
                    state="SUCCESS",
                    progress=100,
                    message="Completed",
                    result=result,
                    completed_at=_utc_now_iso(),
                )
            except Exception as exc:
                self._update(
                    task_id,
                    state="FAILURE",
                    progress=100,
                    message="Failed",
                    error=str(exc),
                    completed_at=_utc_now_iso(),
                )

        import asyncio

        asyncio.create_task(_execute())
        return task_id

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            self._cleanup_locked()
            task = self._tasks.get(task_id)
            if not task:
                return None
            return dict(task)

    def get_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        task = self.get(task_id)
        if task is None:
            return None
        task.pop("result", None)
        return task

    def get_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        task = self.get(task_id)
        if task is None:
            return None
        return {
            "id": task["id"],
            "name": task["name"],
            "state": task["state"],
            "result": task.get("result"),
            "error": task.get("error"),
            "completed_at": task.get("completed_at"),
        }

    def _update(
        self,
        task_id: str,
        *,
        state: Optional[str] = None,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        error: Optional[str] = None,
        result: Any = None,
        completed_at: Optional[str] = None,
    ) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            if state is not None:
                task["state"] = state
            if progress is not None:
                task["progress"] = progress
            if message is not None:
                task["message"] = message
            if error is not None:
                task["error"] = error
            if result is not None:
                task["result"] = result
            if completed_at is not None:
                task["completed_at"] = completed_at
            task["updated_at"] = _utc_now_iso()
            self._cleanup_locked()

    def _cleanup_locked(self) -> None:
        retention_seconds = int(os.getenv("INMEM_TASK_RETENTION_SECONDS", str(self._retention_seconds)))
        max_tasks = int(os.getenv("INMEM_TASK_MAX_ITEMS", str(self._max_tasks)))

        if retention_seconds > 0:
            now = datetime.now(timezone.utc)
            stale_ids = []
            for task_id, task in self._tasks.items():
                completed_at = task.get("completed_at")
                if not completed_at:
                    continue
                try:
                    completed_dt = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
                except Exception:
                    continue
                age = (now - completed_dt).total_seconds()
                if age > retention_seconds:
                    stale_ids.append(task_id)
            for task_id in stale_ids:
                self._tasks.pop(task_id, None)

        if len(self._tasks) > max_tasks:
            ordered = sorted(self._tasks.values(), key=lambda t: t.get("updated_at") or t.get("created_at") or "")
            overflow = len(self._tasks) - max_tasks
            for task in ordered[:overflow]:
                self._tasks.pop(task["id"], None)


task_manager = InMemoryTaskManager()
