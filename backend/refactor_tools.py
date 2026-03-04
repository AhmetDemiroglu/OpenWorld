import os
import re
from typing import List, Dict

REGISTRY_PATH = "C:/Users/Ahmet Demiroğlu/Desktop/OpenWorld/backend/app/tools/registry.py"
DOMAIN_DIR = "C:/Users/Ahmet Demiroğlu/Desktop/OpenWorld/backend/app/tools/domain"

os.makedirs(DOMAIN_DIR, exist_ok=True)

with open(REGISTRY_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# Map categories to the list of tool functions they should contain
tool_mappings = {
    "file_ops": [
        "tool_list_directory", "tool_read_file", "tool_write_file", 
        "tool_delete_file", "tool_copy_file", "tool_move_file", "tool_search_files"
    ],
    "code_analysis": [
        "tool_analyze_code", "tool_find_code_patterns"
    ],
    "reports": [
        "tool_create_word_document", "tool_create_markdown_report"
    ],
    "system_ops": [
        "tool_get_system_info", "tool_list_processes", "tool_kill_process", 
        "tool_execute_command", "tool_network_info", "tool_ping_host"
    ],
    "planner": [
        "tool_add_task", "tool_list_tasks", "tool_complete_task", 
        "tool_add_calendar_event", "tool_list_calendar_events"
    ],
    "email_ops": [
        "tool_create_email_draft", "tool_check_gmail_messages", "tool_check_outlook_messages"
    ],
    "web_research": [
        "tool_search_news", "tool_fetch_web_page", "tool_research_and_report", 
        "tool_compare_topics", "tool_research_note"
    ],
    "memory_ops": [
        "tool_memory_store", "tool_memory_recall", "tool_memory_stats"
    ]
}

def extract_function(name: str, text: str) -> str:
    # Basic regex to extract function (assuming no nested defs with same indent at level 0)
    # This matches 'def func_name(' and all following lines that are indented, plus trailing empty lines
    pattern = r"^(def " + name + r"\b.*?)(?=^def |\Z)"
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    if match:
        return match.group(1).strip() + "\n\n"
    return ""

def remove_function(name: str, text: str) -> str:
    pattern = r"^(def " + name + r"\b.*?)(?=^def |\Z)"
    return re.sub(pattern, "", text, flags=re.MULTILINE | re.DOTALL)

# Default imports for domain files
IMPORTS = '''from typing import Any, Dict, List, Optional
import os
import re
import json
import logging
import asyncio
from datetime import datetime
from app.config import settings

logger = logging.getLogger(__name__)

'''

new_registry_content = content
extracted_funcs: Dict[str, str] = {}

for module, func_names in tool_mappings.items():
    module_code = IMPORTS
    imports_for_registry = f"from .domain.{module} import (\n"
    
    found_any = False
    for func_name in func_names:
        func_code = extract_function(func_name, new_registry_content)
        if func_code:
            module_code += func_code
            new_registry_content = remove_function(func_name, new_registry_content)
            imports_for_registry += f"    {func_name},\n"
            found_any = True
            
    imports_for_registry += ")\n"
    
    if found_any:
        # Write domain file
        domain_file_path = os.path.join(DOMAIN_DIR, f"{module}.py")
        with open(domain_file_path, 'w', encoding='utf-8') as f:
            f.write(module_code)
        
        # We need to prepend imports_for_registry to the new registry content
        # We'll put it after the initial docstring/imports
        extracted_funcs[module] = imports_for_registry

# Now we need to insert the imports into the registry
# Find the end of the existing imports (roughly before the tool dictionary starts)
import_insert_pos = new_registry_content.find("from .code_tools import")
if import_insert_pos == -1:
    import_insert_pos = new_registry_content.find("\n# =============================================================================")

if import_insert_pos != -1:
    all_new_imports = "\n".join(extracted_funcs.values()) + "\n"
    new_registry_content = new_registry_content[:import_insert_pos] + all_new_imports + new_registry_content[import_insert_pos:]

# Add an __init__.py
with open(os.path.join(DOMAIN_DIR, "__init__.py"), 'w') as f:
    f.write("")

with open(REGISTRY_PATH, 'w', encoding='utf-8') as f:
    f.write(new_registry_content)

print("Extraction completed.")
