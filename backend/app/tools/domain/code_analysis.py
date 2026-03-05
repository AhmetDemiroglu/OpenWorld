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




def tool_analyze_code(path: str) -> Dict[str, Any]:
    """Kod dosyasını analiz et."""
    target = _resolve_path(path)
    
    if not target.exists() or not target.is_file():
        return {"error": "Dosya bulunamadı", "path": str(target)}
    
    try:
        content = target.read_text(encoding='utf-8', errors='ignore')
        lines = content.split('\n')
        
        # Basic metrics
        analysis = {
            "path": str(target),
            "filename": target.name,
            "extension": target.suffix,
            "total_lines": len(lines),
            "code_lines": len([l for l in lines if l.strip() and not l.strip().startswith('#')]),
            "comment_lines": len([l for l in lines if l.strip().startswith('#') or l.strip().startswith('//')]),
            "blank_lines": len([l for l in lines if not l.strip()]),
            "file_size": target.stat().st_size
        }
        
        # Language-specific analysis
        if target.suffix in ['.py', '.js', '.ts', '.java', '.cpp', '.c', '.h']:
            analysis["functions"] = len(re.findall(r'\bdef\s+\w+|\bfunction\s+\w+|\b\w+\s*\([^)]*\)\s*\{', content))
            analysis["classes"] = len(re.findall(r'\bclass\s+\w+', content))
            analysis["imports"] = len(re.findall(r'^(import|from|require|include|using)\s+', content, re.MULTILINE))
        
        return analysis
    except Exception as e:
        return {"error": str(e)}

def tool_find_code_patterns(path: str, pattern: str, language: str = "") -> Dict[str, Any]:
    """Kodda pattern ara."""
    target = _resolve_path(path)
    matches = []
    
    try:
        files_to_search = []
        
        if target.is_file():
            files_to_search = [target]
        elif target.is_dir():
            for ext in ['.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h', '.go', '.rs']:
                files_to_search.extend(target.rglob(f'*{ext}'))
        
        for file_path in files_to_search[:50]:  # Limit files
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                lines = content.split('\n')
                
                for i, line in enumerate(lines, 1):
                    if re.search(pattern, line, re.IGNORECASE):
                        matches.append({
                            "file": str(file_path),
                            "line": i,
                            "content": line.strip()[:100]
                        })
            except:
                continue
        
        return {
            "pattern": pattern,
            "matches": matches[:50],
            "count": len(matches)
        }
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# OFİS/RAPOR ARAÇLARI
# =============================================================================

