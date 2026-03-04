from __future__ import annotations

from typing import Any, Dict, Iterable, Set


FINANCIAL_BLOCK_TERMS = [
    # Kesinlikle engellenecek - finansal işlem fiilleri
    ("odeme yap", True),
    ("odeme al", True),
    ("para gonder", True),
    ("para transfer", True),
    ("havale", True),
    ("eft", True),
    ("banka transfer", True),
    ("wire transfer tl", True),
    ("bitcoin gonder", True),
    ("crypto gonder", True),
    ("kripto gonder", True),
    ("wallet transfer", True),
    ("cuzdan gonder", True),
    ("make payment", True),
    ("send payment", True),
    ("send money", True),
    ("transfer money", True),
    ("payment processing", True),
    ("purchase order", True),
    ("buy now pay", True),
    ("crypto transfer", True),
    ("bitcoin transfer", True),
    ("ethereum send", True),
    ("wallet send", True),
    ("paypal send", True),
    ("venmo pay", True),
    # Hassas finansal veriler
    ("kredi kart", True),
    ("kart numara", True),
    ("cvv", True),
    ("son kullanma", True),
    ("iban", True),
    ("swift", True),
    ("credit card", True),
    ("card number", True),
    ("cvv code", True),
    ("expiry date", True),
    ("wire transfer", True),
    ("bank transfer", True),
]

# İzin verilen bağlamlar (beyaz liste)
ALLOWED_FINANCIAL_CONTEXTS = [
    "etki", "analiz", "rapor", "arastirma", "inceleme", "etkileri",
    "piyasalar", "borsa", "ekonomi", "finansal piyasa",
    "impact", "analysis", "report", "research", "effect", "markets"
]

UNTRUSTED_CONTENT_TOOLS: Set[str] = {
    "fetch_web_page",
    "search_news",
    "research_and_report",
}

HIGH_IMPACT_TOOLS: Set[str] = {
    "execute_command",
    "write_file",
    "delete_file",
    "move_file",
    "copy_file",
    "type_text",
    "press_key",
    "hotkey",
    "click_on_screen",
    "drag_to",
    "shutdown_system",
    "lock_workstation",
    "kill_process",
    "open_in_vscode",
    "open_folder",
    "webcam_capture",
    "webcam_record_video",
    "start_audio_recording",
    "stop_audio_recording",
}

TOOL_INTENT_KEYWORDS: Dict[str, Set[str]] = {
    "execute_command": {"komut", "powershell", "cmd", "calistir", "run", "terminal", "shell"},
    "write_file": {"yaz", "olustur", "kaydet", "duzenle", "write", "create", "edit"},
    "delete_file": {"sil", "kaldir", "delete", "remove"},
    "move_file": {"tas", "taşı", "move"},
    "copy_file": {"kopya", "kopyala", "copy"},
    "type_text": {"yaz", "type"},
    "press_key": {"tus", "tuş", "key", "enter", "esc", "tab"},
    "hotkey": {"kisayol", "kısayol", "shortcut", "hotkey", "ctrl", "alt", "win"},
    "click_on_screen": {"tikla", "tıkla", "click"},
    "drag_to": {"surukle", "sürükle", "drag"},
    "shutdown_system": {"kapat", "yeniden baslat", "restart", "shutdown", "logout"},
    "lock_workstation": {"kilit", "lock"},
    "kill_process": {"sonlandir", "terminate", "kill", "kapat"},
    "open_in_vscode": {"vscode", "ac", "aç", "open"},
    "open_folder": {"klasor", "klasör", "ac", "aç", "open"},
    "webcam_capture": {"kamera", "webcam", "fotograf", "fotoğraf", "capture"},
    "webcam_record_video": {"kamera", "video", "kayit", "kayıt", "record"},
    "start_audio_recording": {"ses", "mikrofon", "kayit", "kayıt", "record"},
    "stop_audio_recording": {"ses", "kayit", "kayıt", "durdur", "stop"},
}



def contains_forbidden_financial_intent(text: str) -> bool:
    """Finansal işlem niyeti içeriyor mu? Bağlam duyarlı kontrol.
    
    - Sadece finansal TERİMLER değil, İŞLEM fiilleri engellenir
    - Araştırma/analiz/rapor bağlamlarına izin verilir
    """
    if not text:
        return False
    
    t = text.lower()
    
    # Önce bağlam kontrolü - analiz/araştırma/rapor bağlamı mı?
    is_analysis_context = any(ctx in t for ctx in ALLOWED_FINANCIAL_CONTEXTS)
    
    for term, strict in FINANCIAL_BLOCK_TERMS:
        if term in t:
            # Eğer analiz/araştırma bağlamındaysa ve strict değilse, izin ver
            if is_analysis_context and not strict:
                continue
            # Aksi halde engelle
            return True
    
    return False



def is_forbidden_tool_payload(payload: Any) -> bool:
    return contains_forbidden_financial_intent(str(payload))



def check_command_safety(command: str) -> tuple[bool, str]:
    cmd_lower = command.lower()
    financial_patterns = [
        "payment",
        "purchase",
        "credit card",
        "bank transfer",
        "wire transfer",
        "crypto",
        "bitcoin",
        "wallet send",
        "paypal",
        "venmo",
        "payment gateway",
    ]
    for pattern in financial_patterns:
        if pattern in cmd_lower:
            return False, f"Finansal islem iceren komut engellendi: {pattern}"
    return True, ""



def is_untrusted_content_tool(tool_name: str) -> bool:
    return tool_name in UNTRUSTED_CONTENT_TOOLS



def is_high_impact_tool(tool_name: str) -> bool:
    return tool_name in HIGH_IMPACT_TOOLS



def user_explicitly_authorized_tool(last_user_message: str, tool_name: str) -> bool:
    text = (last_user_message or "").lower()
    if not text:
        return False
    keywords: Iterable[str] = TOOL_INTENT_KEYWORDS.get(tool_name, {tool_name.lower()})
    return any(k in text for k in keywords)
