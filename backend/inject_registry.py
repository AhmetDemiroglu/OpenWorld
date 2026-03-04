import os

REGISTRY_PATH = r"C:\Users\Ahmet Demiroğlu\Desktop\OpenWorld\backend\app\tools\registry.py"

with open(REGISTRY_PATH, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
in_get_relevant_tools = False

for line in lines:
    if line.startswith("def get_relevant_tools(user_message: str) -> List[Dict[str, Any]]:"):
        in_get_relevant_tools = True
        new_lines.append(line)
        new_lines.append('    """Kullanici mesaji icin alan adindaki semantik analizi kullanarak ilgili tool spec\'lerini dondur."""\n')
        new_lines.append('    try:\n')
        new_lines.append('        from app.semantic_router import get_semantic_tools\n')
        new_lines.append('        return get_semantic_tools(user_message, top_k=MAX_TOOLS_PER_REQUEST)\n')
        new_lines.append('    except Exception as e:\n')
        new_lines.append('        import logging\n')
        new_lines.append('        logging.getLogger(__name__).warning(f"Semantic router failed: {e}")\n')
        new_lines.append('        return [TOOLS[name][1] for name in DEFAULT_TOOL_NAMES if name in TOOLS][:MAX_TOOLS_PER_REQUEST]\n')
        continue
    
    if in_get_relevant_tools:
        if line.startswith("def get_tool_specs() -> List[Dict[str, Any]]:"):
            in_get_relevant_tools = False
            new_lines.append("\n")
            new_lines.append(line)
    else:
        new_lines.append(line)

with open(REGISTRY_PATH, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Registry get_relevant_tools injected successfully.")
