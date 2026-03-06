"""
agent_router.py — Gelen mesajı analiz edip en uygun sub-ajan profilini seçer.
LLM çağrısı YOK — saf keyword eşleştirmesi (hızlı, deterministik).
"""
from __future__ import annotations
from typing import Optional


# (ajan_adı, [keyword listesi]) — sıralı; ilk eşleşen kazanır
_RULES: list[tuple[str, list[str]]] = [
    (
        "desktop",
        [
            # Türkçe
            "ekran görüntüsü", "ekran al", "screenshot", "ekrana bak",
            "tıkla ", "tikla ", "mouse", "fare ", "/tikla", "/ekran",
            "yaz ve enter", "tuşuna bas", "tusuna bas",
            "ocr ", "metni oku", "ekrandaki",
            "pencere ", "window ",
            "webcam", "kamera ", "drag ", "sürükle",
            "scroll ", "kaydır ",
        ],
    ),
    (
        "code",
        [
            # Türkçe
            "git ", "commit", "branch", "merge ", "rebase",
            "kod yaz", "kod düzelt", "kodu düzelt", "kodu analiz",
            "fonksiyon ", "function ", "class ", "metod ", "method ",
            "test çalıştır", "test yaz", "unit test",
            "refactor", "yeniden adlandır", "rename",
            "vscode ", "vs code", "kimicode", "kimi code",
            "claude code", "codex ",
            ".py ", ".ts ", ".js ", ".go ", ".rs ", ".cs ",
            "import ", "hata düzelt", "bug düzelt", "debug ",
            "proje analiz", "kod ara",
        ],
    ),
    (
        "research",
        [
            # Sadece acik internet arastirmasi niyeti belirten ifadeler
            # "analiz et", "rapor yaz" gibi genel ifadeler buraya DAHIL DEGIL
            # — bunlar LLM'e gidip yerel dosya/kod analizi veya rapor olusturma olabilir
            "araştır ", "/araştır", "araştırma yap",
            "haber tara", "haber ara", "son haberler",
            "web'de ara", "internette ara",
            "makale bul", "kaynak bul",
            "araştırma raporu",
            "arastir ",
        ],
    ),
    (
        "file",
        [
            # Türkçe
            "dosyayı oku", "dosyayı yaz", "dosya oluştur", "dosya sil",
            "klasör ", "dizin ", "directory ",
            "pdf oluştur", "pdf yaz", "pdf oku", "pdf'i",
            "word belgesi", "word dosyası", "docx ",
            "excel ", "xlsx ",
            "zip oluştur", "zip aç", "sıkıştır",
            "dosya kopyala", "dosya taşı",
            "belge oluştur", "rapor dosyası",
        ],
    ),
    (
        "system",
        [
            # Türkçe
            "sistem bilgi", "sistemin durumu", "cpu ", "ram ",
            "bellek kullanımı", "disk kullanımı",
            "process listesi", "çalışan programlar", "process sonlandır",
            "ağ bilgisi", "network ", "ip adres", "ping ",
            "usb ", "usb aygıt",
            "bilgisayarı kapat", "shutdown", "yeniden başlat", "restart",
            "ekranı kilitle", "lock screen",
        ],
    ),
]


def route(user_message: str) -> Optional[str]:
    """Mesajı analiz et, en uygun ajan profilini döndür.

    Returns:
        Profil adı ("research", "desktop", "code", "file", "system")
        veya None (genel ajan — semantic router tüm 100+ aracı kullanır).
    """
    if not user_message:
        return None

    msg = user_message.lower()

    scores: dict[str, int] = {}
    for agent_name, keywords in _RULES:
        for kw in keywords:
            if kw in msg:
                scores[agent_name] = scores.get(agent_name, 0) + 1

    if not scores:
        return None

    best = max(scores, key=lambda k: scores[k])
    return best


def route_with_info(user_message: str) -> dict:
    """Debug için: hem profil adını hem skorları döndür."""
    if not user_message:
        return {"profile": None, "scores": {}}
    msg = user_message.lower()
    scores: dict[str, int] = {}
    for agent_name, keywords in _RULES:
        for kw in keywords:
            if kw in msg:
                scores[agent_name] = scores.get(agent_name, 0) + 1
    profile = max(scores, key=lambda k: scores[k]) if scores else None
    return {"profile": profile, "scores": scores}
