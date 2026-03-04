from __future__ import annotations

import json
import inspect
import html as html_lib
import ipaddress
import os
import platform
import psutil
import re
import shutil
import socket
import subprocess
import uuid
from urllib.parse import quote_plus, urlparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple, Optional
import xml.etree.ElementTree as ET

import httpx

from app.config import settings
from app.secrets import decrypt_text
from app.database import memory_store, memory_recall, get_tool_stats

import logging
import asyncio
logger = logging.getLogger(__name__)


import os
import re
import json


from datetime import datetime




def tool_add_task(title: str, due_date: str = "", notes: str = "") -> Dict[str, Any]:
    task_file = _resolve_inside_workspace("planner/tasks.json")
    tasks = _read_json(task_file, [])
    task = {
        "id": str(uuid.uuid4())[:8],
        "title": title,
        "due_date": due_date,
        "notes": notes,
        "status": "open",
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    tasks.append(task)
    _write_json(task_file, tasks)
    return {"task": task}

def tool_list_tasks(status: str = "all") -> Dict[str, Any]:
    task_file = _resolve_inside_workspace("planner/tasks.json")
    tasks = _read_json(task_file, [])
    if status != "all":
        tasks = [t for t in tasks if t.get("status") == status]
    return {"tasks": tasks[:200], "count": len(tasks)}

def tool_complete_task(task_id: str) -> Dict[str, Any]:
    task_file = _resolve_inside_workspace("planner/tasks.json")
    tasks = _read_json(task_file, [])
    for t in tasks:
        if t.get("id") == task_id:
            t["status"] = "done"
            t["completed_at"] = datetime.utcnow().isoformat() + "Z"
            _write_json(task_file, tasks)
            return {"updated": t}
    raise ValueError("Task not found.")

def tool_add_calendar_event(title: str, start_at: str, notes: str = "", location: str = "") -> Dict[str, Any]:
    cal_file = _resolve_inside_workspace("planner/calendar.json")
    events = _read_json(cal_file, [])
    ev = {
        "id": str(uuid.uuid4())[:8],
        "title": title,
        "start_at": start_at,
        "location": location,
        "notes": notes,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    events.append(ev)
    _write_json(cal_file, events)
    return {"event": ev}

def tool_list_calendar_events() -> Dict[str, Any]:
    cal_file = _resolve_inside_workspace("planner/calendar.json")
    events = _read_json(cal_file, [])
    events = sorted(events, key=lambda x: x.get("start_at", ""))
    return {"events": events[:300], "count": len(events)}

