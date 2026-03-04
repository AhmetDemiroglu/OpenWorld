# Yeni Araç Ekleme Rehberi

## Hızlı Başlangıç

1. `backend/app/tools/` dizininde yeni bir dosya oluşturun
2. Aracı `registry.py`'ye kaydedin
3. Test edin

## Örnek: Basit Araç

```python
# backend/app/tools/my_tool.py

from typing import Any, Dict

def tool_my_action(param1: str, param2: int = 10) -> Dict[str, Any]:
    """
    Açıklama: Bu araç ne yapar
    
    Args:
        param1: Parametre açıklaması
        param2: Opsiyonel parametre (varsayılan: 10)
    
    Returns:
        Sonuç sözlüğü
    """
    result = f"İşlem: {param1}, Sayı: {param2}"
    
    return {
        "success": True,
        "result": result,
        "param1": param1,
        "param2": param2
    }
```

## Registry'e Kaydetme

```python
# backend/app/tools/registry.py

from .my_tool import tool_my_action

# ... diğer importlar ...

_BUILTIN_TOOLS = [
    # ... diğer araçlar ...
    {
        "type": "function",
        "function": {
            "name": "my_action",
            "description": "Bu araç ne yapar",
            "parameters": {
                "type": "object",
                "properties": {
                    "param1": {
                        "type": "string",
                        "description": "Parametre açıklaması"
                    },
                    "param2": {
                        "type": "integer",
                        "description": "Opsiyonel parametre",
                        "default": 10
                    }
                },
                "required": ["param1"]
            }
        }
    },
]

# Fonksiyon haritasına ekle
_TOOL_FUNCTION_MAP = {
    # ... diğer haritalamalar ...
    "my_action": tool_my_action,
}
```

## Kategori Ekleme

Araç seçimi için kategori belirtin:

```python
_TOOL_CATEGORIES = {
    # ... diğer kategoriler ...
    "my_category": ["my_action", "other_tool"],
}
```

## Best Practices

### 1. Hata Yönetimi
```python
def tool_safe_action(param: str) -> Dict[str, Any]:
    try:
        # İşlem
        return {"success": True, "result": result}
    except Exception as e:
        return {"error": str(e), "success": False}
```

### 2. Tip Dönüşümleri
```python
def tool_with_types(value: str) -> Dict[str, Any]:
    # String'den int'e çevir
    try:
        num = int(value)
    except ValueError:
        return {"error": "Geçersiz sayı formatı"}
    
    return {"success": True, "value": num}
```

### 3. Dosya İşlemleri
```python
from pathlib import Path

def tool_save_file(content: str, filename: str) -> Dict[str, Any]:
    output_dir = Path("data/outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = output_dir / filename
    file_path.write_text(content, encoding="utf-8")
    
    return {
        "success": True,
        "path": str(file_path),
        "size": len(content)
    }
```

## Test Yazma

```python
# backend/tests/tools/test_my_tool.py

import pytest
from app.tools.my_tool import tool_my_action

def test_tool_my_action():
    result = tool_my_action("test", 5)
    assert result["success"] is True
    assert "test" in result["result"]
    assert result["param2"] == 5

def test_tool_my_action_default():
    result = tool_my_action("test")
    assert result["param2"] == 10  # default value
```
