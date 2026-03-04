import os

DOMAIN_DIR = "C:/Users/Ahmet Demiroğlu/Desktop/OpenWorld/backend/app/tools/domain"

COMMON_IMPORTS = """from __future__ import annotations

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
"""

for fname in os.listdir(DOMAIN_DIR):
    if fname.endswith(".py") and fname != "__init__.py":
        path = os.path.join(DOMAIN_DIR, fname)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Optional: remove the basic imports added previously if they conflict,
        # but Python handles duplicate imports fine, though avoiding them is cleaner.
        # Let's just strip out the previous `IMPORTS` block manually.
        content = content.replace("from typing import Any, Dict, List, Optional", "")
        content = content.replace("import asyncio", "")
        content = content.replace("import logging", "")
        content = content.replace("logger = logging.getLogger(__name__)", "")
        content = content.replace("from app.config import settings", "")
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(COMMON_IMPORTS + "\nimport logging\nimport asyncio\nlogger = logging.getLogger(__name__)\n\n" + content)

print("Imports injected.")
