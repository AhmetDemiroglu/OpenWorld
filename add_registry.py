c = open(r'backend\app\tools\registry.py', 'r', encoding='utf-8', errors='replace').read()

# The TOOLS dict entry for research_and_report - find it by key string
target_key = '    "research_and_report": ('
if target_key not in c:
    print('Could not find "research_and_report" dict key. Searching...')
    for line in c.split('\n'):
        if 'research_and_report' in line and 'def ' not in line and 'tool_research_and_report' not in line:
            print(repr(line))
else:
    entry = '''    "research_async": (
        tool_research_async,
        {
            "type": "function",
            "function": {
                "name": "research_async",
                "description": "Arastirmayi ARKA PLANDA baslatir ve ANINDA onay mesaji don. Kullanici arastirma, analiz, inceleme, rapor istediginde BU ARACI KULLAN. Bitince Telegram bildirimi ve rapor dosyasi gonderilir. research_and_report yerine bunu kullan.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "Arastirilacak konu (detayli belirtin)"},
                        "report_style": {"type": "string", "enum": ["standard", "technical", "academic", "brief"]},
                        "max_sources": {"type": "integer", "description": "Max kaynak sayisi (varsayilan: 10)"},
                        "out_path": {"type": "string", "description": "Cikti dosyasi yolu (opsiyonel)"}
                    },
                    "required": ["topic"]
                }
            }
        }
    ),
''' + target_key
    c2 = c.replace(target_key, entry, 1)
    open(r'backend\app\tools\registry.py', 'w', encoding='utf-8').write(c2)
    print('OK: dict entry added')
