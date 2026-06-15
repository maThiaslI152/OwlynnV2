"""
Todo/Task Tracking — Persistent task list the agent can manage.
Mirrors Cowork's Todo tool for tracking work items across sessions.
"""

import json
import time
from langchain_core.tools import tool
from src.config.settings import DATA_DIR

_TODO_PATH = DATA_DIR / "todos.json"


def _load_todos() -> list[dict]:
    try:
        return json.loads(_TODO_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_todos(todos: list[dict]):
    _TODO_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TODO_PATH.write_text(
        json.dumps(todos, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _next_id(todos: list[dict]) -> int:
    return max((t.get("id", 0) for t in todos), default=0) + 1


@tool
def todo_add(
    task: str,
    priority: str = "medium",
    due_date: str = "",
    course_id: str = "",
    tags: str = "",
) -> str:
    """
    Adds a new task to the todo list.

    Args:
        task: Description of the task.
        priority: Priority level — low, medium, or high.
        due_date: Optional due date YYYY-MM-DD.
        course_id: Optional course code (e.g. UID10667).
        tags: Comma-separated tags (e.g. exam,reading).
    """
    todos = _load_todos()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    item = {
        "id": _next_id(todos),
        "task": task.strip(),
        "priority": priority.strip().lower(),
        "status": "pending",
        "due_date": due_date.strip() or None,
        "course_id": course_id.strip() or None,
        "tags": tag_list,
        "created_at": time.strftime("%Y-%m-%d %H:%M"),
        "completed_at": None,
    }
    todos.append(item)
    _save_todos(todos)
    return f"✅ Added task #{item['id']}: {task}"


@tool
def todo_list(status: str = "all") -> str:
    """
    Lists tasks from the todo list.

    Args:
        status: Filter by status — all, pending, done.
    """
    todos = _load_todos()
    if not todos:
        return "📋 Todo list is empty."

    if status != "all":
        todos = [t for t in todos if t["status"] == status]

    if not todos:
        return f"📋 No tasks with status '{status}'."

    lines = ["📋 Todo List:"]
    for t in todos:
        icon = "✅" if t["status"] == "done" else "⬜"
        pri = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(t["priority"], "⚪")
        due = f" due:{t['due_date']}" if t.get("due_date") else ""
        course = f" [{t['course_id']}]" if t.get("course_id") else ""
        lines.append(f"  {icon} #{t['id']} [{pri}]{course}{due} {t['task']}")
    return "\n".join(lines)


@tool
def todo_complete(task_id: int) -> str:
    """
    Marks a task as completed.

    Args:
        task_id: The ID number of the task to complete.
    """
    todos = _load_todos()
    for t in todos:
        if t["id"] == task_id:
            t["status"] = "done"
            t["completed_at"] = time.strftime("%Y-%m-%d %H:%M")
            _save_todos(todos)
            return f"✅ Task #{task_id} marked as done."
    return f"Task #{task_id} not found."


@tool
def todo_remove(task_id: int) -> str:
    """
    Removes a task from the todo list.

    Args:
        task_id: The ID number of the task to remove.
    """
    todos = _load_todos()
    before = len(todos)
    todos = [t for t in todos if t["id"] != task_id]
    if len(todos) < before:
        _save_todos(todos)
        return f"🗑️ Task #{task_id} removed."
    return f"Task #{task_id} not found."


@tool
def todo_update(
    task_id: int,
    task: str = "",
    priority: str = "",
    due_date: str = "",
    course_id: str = "",
    tags: str = "",
    status: str = "",
) -> str:
    """
    Update fields on an existing todo.

    Args:
        task_id: Task id to update.
        task: New description (optional).
        priority: low, medium, high (optional).
        due_date: YYYY-MM-DD or empty to clear (optional).
        course_id: Course code (optional).
        tags: Comma-separated tags (optional).
        status: pending or done (optional).
    """
    todos = _load_todos()
    for t in todos:
        if t["id"] != task_id:
            continue
        if task:
            t["task"] = task.strip()
        if priority:
            t["priority"] = priority.strip().lower()
        if due_date is not None:
            t["due_date"] = due_date.strip() or None
        if course_id is not None:
            t["course_id"] = course_id.strip() or None
        if tags:
            t["tags"] = [x.strip() for x in tags.split(",") if x.strip()]
        if status:
            t["status"] = status.strip().lower()
            if t["status"] == "done" and not t.get("completed_at"):
                t["completed_at"] = time.strftime("%Y-%m-%d %H:%M")
        _save_todos(todos)
        return f"✅ Updated task #{task_id}."
    return f"Task #{task_id} not found."


@tool
def todo_filter(course_id: str = "", due_before: str = "", tag: str = "") -> str:
    """
    Filter todos by course, due date, or tag.

    Args:
        course_id: Match course code.
        due_before: Include tasks due on or before YYYY-MM-DD.
        tag: Match a tag substring.
    """
    todos = [t for t in _load_todos() if t.get("status") == "pending"]
    if course_id:
        todos = [t for t in todos if t.get("course_id") == course_id.strip()]
    if due_before:
        todos = [
            t
            for t in todos
            if t.get("due_date") and t["due_date"] <= due_before.strip()
        ]
    if tag:
        tg = tag.strip().lower()
        todos = [
            t
            for t in todos
            if any(tg in (x or "").lower() for x in (t.get("tags") or []))
        ]
    if not todos:
        return "No matching pending tasks."
    lines = ["📋 Filtered tasks:"]
    for t in todos:
        due = f" due:{t['due_date']}" if t.get("due_date") else ""
        lines.append(f"  ⬜ #{t['id']} [{t.get('course_id') or '-'}]{due} {t['task']}")
    return "\n".join(lines)
