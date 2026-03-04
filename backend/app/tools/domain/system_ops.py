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




def tool_get_system_info() -> Dict[str, Any]:
    """Sistem bilgisi al."""
    try:
        return {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "hostname": platform.node(),
            "cpu_count": psutil.cpu_count(),
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_total": psutil.virtual_memory().total,
            "memory_available": psutil.virtual_memory().available,
            "memory_percent": psutil.virtual_memory().percent,
            "disk_usage": {
                str(part.mountpoint): {
                    "total": psutil.disk_usage(part.mountpoint).total,
                    "used": psutil.disk_usage(part.mountpoint).used,
                    "free": psutil.disk_usage(part.mountpoint).free
                }
                for part in psutil.disk_partitions()[:5]
            },
            "boot_time": datetime.fromtimestamp(psutil.boot_time()).isoformat(),
            "current_time": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}

def tool_list_processes(filter_name: str = "", limit: int = 20) -> Dict[str, Any]:
    """ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¡alÃƒÆ’Ã¢â‚¬ÂÃƒâ€šÃ‚Â±ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€¦Ã‚Â¸an process'leri listele."""
    try:
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'status', 'cpu_percent', 'memory_percent', 'create_time']):
            try:
                info = proc.info
                if filter_name and filter_name.lower() not in info['name'].lower():
                    continue
                processes.append(info)
                if len(processes) >= limit:
                    break
            except:
                pass
        
        return {
            "processes": processes,
            "count": len(processes),
            "total_system_processes": len(list(psutil.process_iter()))
        }
    except Exception as e:
        return {"error": str(e)}

def tool_kill_process(pid: int, confirm: bool = False) -> Dict[str, Any]:
    """Process sonlandÃƒÆ’Ã¢â‚¬ÂÃƒâ€šÃ‚Â±r."""
    if not confirm:
        return {"error": "confirm=true gerekli", "pid": pid}
    
    try:
        proc = psutil.Process(pid)
        name = proc.name()
        proc.terminate()
        return {"pid": pid, "name": name, "status": "terminated"}
    except Exception as e:
        return {"error": str(e), "pid": pid}


# =============================================================================
# GELÃƒÆ’Ã¢â‚¬ÂÃƒâ€šÃ‚Â°ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚ÂMÃƒÆ’Ã¢â‚¬ÂÃƒâ€šÃ‚Â°ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â SHELL ARACI
# =============================================================================

def tool_execute_command(command: str, working_dir: str = "", timeout: int = 60) -> Dict[str, Any]:
    """Komut ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â§alÃƒÆ’Ã¢â‚¬ÂÃƒâ€šÃ‚Â±ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€¦Ã‚Â¸tÃƒÆ’Ã¢â‚¬ÂÃƒâ€šÃ‚Â±r - geliÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€¦Ã‚Â¸miÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€¦Ã‚Â¸ shell eriÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€¦Ã‚Â¸imi."""
    if not settings.enable_shell_tool:
        return {"error": "Shell tool devre dÃƒÆ’Ã¢â‚¬ÂÃƒâ€šÃ‚Â±ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€¦Ã‚Â¸ÃƒÆ’Ã¢â‚¬ÂÃƒâ€šÃ‚Â±. ENABLE_SHELL_TOOL=true ile etkinleÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€¦Ã‚Â¸tirin."}
    
    # Finansal komutlarÃƒÆ’Ã¢â‚¬ÂÃƒâ€šÃ‚Â± engelle
    forbidden_patterns = [
        'payment', 'purchase', 'credit card', 'bank transfer',
        'wire transfer', 'crypto', 'bitcoin', 'wallet'
    ]
    
    cmd_lower = command.lower()
    for pattern in forbidden_patterns:
        if pattern in cmd_lower:
            return {"error": f"Finansal iÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€¦Ã‚Â¸lem iÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â§eren komut engellendi: {pattern}"}
    
    try:
        cwd = _resolve_path(working_dir) if working_dir else Path.home()
        
        # PowerShell veya CMD
        if platform.system() == "Windows":
            shell = ["powershell", "-NoProfile", "-Command", command]
        else:
            shell = ["bash", "-c", command]
        
        result = subprocess.run(
            shell,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd)
        )
        
        return {
            "command": command,
            "working_dir": str(cwd),
            "exit_code": result.returncode,
            "stdout": result.stdout[:10000] if result.stdout else "",
            "stderr": result.stderr[:5000] if result.stderr else ""
        }
    except subprocess.TimeoutExpired:
        return {"error": "Komut zaman aÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€¦Ã‚Â¸ÃƒÆ’Ã¢â‚¬ÂÃƒâ€šÃ‚Â±mÃƒÆ’Ã¢â‚¬ÂÃƒâ€šÃ‚Â±na uÃƒÆ’Ã¢â‚¬ÂÃƒâ€¦Ã‚Â¸radÃƒÆ’Ã¢â‚¬ÂÃƒâ€šÃ‚Â±", "command": command}
    except Exception as e:
        return {"error": str(e), "command": command}


# =============================================================================
# AÃƒÆ’Ã¢â‚¬ÂÃƒâ€šÃ‚Â ARAÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¡LARI
# =============================================================================

def tool_network_info() -> Dict[str, Any]:
    """AÃƒÆ’Ã¢â‚¬ÂÃƒâ€¦Ã‚Â¸ bilgisi al."""
    try:
        interfaces = {}
        for name, addrs in psutil.net_if_addrs().items():
            interfaces[name] = [
                {
                    "family": str(addr.family),
                    "address": addr.address,
                    "netmask": addr.netmask,
                    "broadcast": addr.broadcast
                }
                for addr in addrs
            ]
        
        return {
            "interfaces": interfaces,
            "io_counters": dict(psutil.net_io_counters()._asdict()),
            "connections": len(psutil.net_connections())
        }
    except Exception as e:
        return {"error": str(e)}

def tool_ping_host(host: str, count: int = 4) -> Dict[str, Any]:
    """Host ping at."""
    try:
        if platform.system() == "Windows":
            cmd = ["ping", "-n", str(count), host]
        else:
            cmd = ["ping", "-c", str(count), host]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        return {
            "host": host,
            "success": result.returncode == 0,
            "output": result.stdout
        }
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# ESKÃƒÆ’Ã¢â‚¬ÂÃƒâ€šÃ‚Â° ARAÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¡LAR (Geriye uyumluluk iÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â§in)
# =============================================================================

