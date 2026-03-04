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




def tool_list_directory(path: str = ".", recursive: bool = False, pattern: str = "") -> Dict[str, Any]:
    """Dizin iÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â§eriÃƒÆ’Ã¢â‚¬ÂÃƒâ€¦Ã‚Â¸ini listele - tÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¼m disk eriÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€¦Ã‚Â¸imi."""
    target = _resolve_path(path)
    
    if not target.exists():
        return {"error": f"Dizin bulunamadÃƒÆ’Ã¢â‚¬ÂÃƒâ€šÃ‚Â±: {path}", "path": str(target)}
    
    if not target.is_dir():
        return {"error": f"Bu bir dizin deÃƒÆ’Ã¢â‚¬ÂÃƒâ€¦Ã‚Â¸il: {path}", "path": str(target)}
    
    try:
        items = []
        
        if recursive:
            for root, dirs, files in os.walk(target):
                root_path = Path(root)
                for file in files[:50]:  # Limit to prevent huge responses
                    file_path = root_path / file
                    try:
                        items.append({
                            "name": file,
                            "path": str(file_path),
                            "type": "file",
                            "size": file_path.stat().st_size,
                            "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                        })
                    except:
                        pass
                if len(items) >= 200:
                    break
        else:
            for child in target.iterdir():
                try:
                    stat = child.stat()
                    item = {
                        "name": child.name,
                        "path": str(child),
                        "type": "dir" if child.is_dir() else "file",
                        "size": stat.st_size if child.is_file() else None,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                    }
                    if pattern and not re.search(pattern, child.name, re.IGNORECASE):
                        continue
                    items.append(item)
                except:
                    pass
        
        return {
            "path": str(target),
            "item_count": len(items),
            "items": items[:200]
        }
    except Exception as e:
        return {"error": str(e), "path": str(target)}

def tool_read_file(path: str, offset: int = 0, limit: int = 50000) -> Dict[str, Any]:
    """Dosya oku - tÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¼m disk eriÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€¦Ã‚Â¸imi (metin ve binary)."""
    target = _resolve_path(path)
    
    if not target.exists():
        return {"error": f"Dosya bulunamadÃƒÆ’Ã¢â‚¬ÂÃƒâ€šÃ‚Â±: {path}", "path": str(target)}
    
    if not target.is_file():
        return {"error": f"Bu bir dosya deÃƒÆ’Ã¢â‚¬ÂÃƒâ€¦Ã‚Â¸il: {path}", "path": str(target)}
    
    try:
        # Text file detection
        is_text = False
        try:
            with open(target, 'r', encoding='utf-8') as f:
                f.read(1024)
                is_text = True
        except:
            pass
        
        if is_text:
            with open(target, 'r', encoding='utf-8', errors='ignore') as f:
                if offset > 0:
                    f.seek(offset)
                content = f.read(limit)
            
            return {
                "path": str(target),
                "type": "text",
                "size": target.stat().st_size,
                "encoding": "utf-8",
                "offset": offset,
                "content": content
            }
        else:
            # Binary file - return metadata
            stat = target.stat()
            return {
                "path": str(target),
                "type": "binary",
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "note": "Binary dosya - icerik gosterilemiyor",
            }
    except Exception as e:
        return {"error": str(e), "path": str(target)}

def tool_write_file(path: str, content: str, append: bool = False) -> Dict[str, Any]:
    """Dosya yaz - tÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¼m disk eriÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€¦Ã‚Â¸imi."""
    target = _resolve_path(path)
    
    if not _is_safe_path(target):
        return {"error": "Kritik sistem dosyasÃƒÆ’Ã¢â‚¬ÂÃƒâ€šÃ‚Â± - yazma engellendi", "path": str(target)}
    
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        
        mode = 'a' if append else 'w'
        with open(target, mode, encoding='utf-8') as f:
            f.write(content)
        
        return {
            "path": str(target),
            "written_chars": len(content),
            "operation": "append" if append else "write"
        }
    except Exception as e:
        return {"error": str(e), "path": str(target)}

def tool_delete_file(path: str, confirm: bool = False) -> Dict[str, Any]:
    """Dosya sil - dikkatli kullan."""
    if not confirm:
        return {"error": "confirm=true gerekli", "path": path}
    
    target = _resolve_path(path)
    
    if not _is_safe_path(target):
        return {"error": "Kritik sistem dosyasÃƒÆ’Ã¢â‚¬ÂÃƒâ€šÃ‚Â± - silme engellendi", "path": str(target)}
    
    try:
        if target.is_file():
            target.unlink()
            return {"deleted": str(target), "type": "file"}
        elif target.is_dir():
            shutil.rmtree(target)
            return {"deleted": str(target), "type": "directory"}
        else:
            return {"error": "Dosya bulunamadÃƒÆ’Ã¢â‚¬ÂÃƒâ€šÃ‚Â±", "path": str(target)}
    except Exception as e:
        return {"error": str(e), "path": str(target)}

def tool_copy_file(source: str, destination: str) -> Dict[str, Any]:
    """Dosya kopyala."""
    src = _resolve_path(source)
    dst = _resolve_path(destination)
    
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        
        if src.is_file():
            shutil.copy2(src, dst)
        elif src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        
        return {"source": str(src), "destination": str(dst), "success": True}
    except Exception as e:
        return {"error": str(e), "source": source, "destination": destination}

def tool_move_file(source: str, destination: str) -> Dict[str, Any]:
    """Dosya taÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€¦Ã‚Â¸ÃƒÆ’Ã¢â‚¬ÂÃƒâ€šÃ‚Â±."""
    src = _resolve_path(source)
    dst = _resolve_path(destination)
    
    if not _is_safe_path(src) or not _is_safe_path(dst):
        return {"error": "Kritik sistem dosyasÃƒÆ’Ã¢â‚¬ÂÃƒâ€šÃ‚Â± - taÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€¦Ã‚Â¸ÃƒÆ’Ã¢â‚¬ÂÃƒâ€šÃ‚Â±ma engellendi"}
    
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return {"source": str(src), "destination": str(dst), "success": True}
    except Exception as e:
        return {"error": str(e)}

def tool_search_files(path: str, pattern: str, file_type: str = "") -> Dict[str, Any]:
    """Dosya ara - tÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¼m diskte."""
    target = _resolve_path(path)
    results = []
    
    try:
        for root, dirs, files in os.walk(target):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for file in files:
                if pattern.lower() in file.lower():
                    file_path = Path(root) / file
                    
                    # File type filter
                    if file_type and not file.endswith(file_type):
                        continue
                    
                    try:
                        stat = file_path.stat()
                        results.append({
                            "name": file,
                            "path": str(file_path),
                            "size": stat.st_size,
                            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                        })
                    except:
                        pass
                    
                    if len(results) >= 100:
                        break
            
            if len(results) >= 100:
                break
        
        return {
            "search_path": str(target),
            "pattern": pattern,
            "matches": results,
            "count": len(results)
        }
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# KOD ANALÃƒÆ’Ã¢â‚¬ÂÃƒâ€šÃ‚Â°Z ARAÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¡LARI
# =============================================================================

