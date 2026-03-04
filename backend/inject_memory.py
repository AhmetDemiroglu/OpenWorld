import os
import re

AGENT_PATH = r"C:\Users\Ahmet Demiroğlu\Desktop\OpenWorld\backend\app\agent.py"

with open(AGENT_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# Instead of complex regex, just exactly find the line and insert
target = 'messages.append(ChatMessage(role="system", content=build_system_prompt()))'

injection = """            # Inject long-term memory context on session initialization
            try:
                from .vector_memory import memory_get_context
                mems = memory_get_context(limit=10)
                if mems:
                    mem_blocks = "\\n".join(f"- {m}" for m in mems)
                    mem_sys_msg = f"=== UZUN SURELI HAFIZAN ===\\nAsagidaki bilgiler onceki konusmalarindan ogrendiklerin:\\n{mem_blocks}\\n=========================="
                    messages.append(ChatMessage(role="system", content=mem_sys_msg))
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to load memory context: {e}")"""

if target in content and "UZUN SURELI HAFIZAN" not in content:
    new_content = content.replace(target, target + "\n" + injection)
    with open(AGENT_PATH, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Agent memory injection successful.")
else:
    print("Target not found or already injected.")
