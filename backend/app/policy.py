from __future__ import annotations

from typing import Any


# Sadece finansal işlemleri engelle - gerisi serbest
FINANCIAL_BLOCK_TERMS = [
    # Türkçe
    "kredi kart",
    "kart numara",
    "cvv",
    "son kullanma",
    "iban",
    "havale",
    "eft",
    "odeme yap",
    "odeme al",
    "para gonder",
    "para transfer",
    "banka transfer",
    "wire transfer tl",
    "swift",
    "bitcoin gonder",
    "crypto gonder",
    "kripto gonder",
    "wallet transfer",
    "cuzdan gonder",
    # İngilizce
    "credit card",
    "card number",
    "cvv code",
    "expiry date",
    "make payment",
    "send payment",
    "wire transfer",
    "bank transfer",
    "send money",
    "transfer money",
    "payment processing",
    "purchase order",
    "buy now pay",
    "crypto transfer",
    "bitcoin transfer",
    "ethereum send",
    "wallet send",
    "paypal send",
    "venmo pay",
]


def contains_forbidden_financial_intent(text: str) -> bool:
    """Kullanıcı mesajında finansal işlem niyeti var mı kontrol et."""
    if not text:
        return False
    t = text.lower()
    return any(term in t for term in FINANCIAL_BLOCK_TERMS)


def is_forbidden_tool_payload(payload: Any) -> bool:
    """Tool payload'ında finansal içerik var mı kontrol et."""
    return contains_forbidden_financial_intent(str(payload))


def check_command_safety(command: str) -> tuple[bool, str]:
    """Komut güvenli mi kontrol et. Sadece finansal komutları engelle."""
    cmd_lower = command.lower()
    
    # Finansal komutları engelle
    financial_patterns = [
        'payment', 'purchase', 'credit card', 'bank transfer',
        'wire transfer', 'crypto', 'bitcoin', 'wallet send',
        'paypal', 'venmo', 'payment gateway'
    ]
    
    for pattern in financial_patterns:
        if pattern in cmd_lower:
            return False, f"Finansal işlem içeren komut engellendi: {pattern}"
    
    # Tüm diğer komutlara izin ver (silme, format vb. dahil)
    # Kullanıcı kendi bilgisayarında ne yapmak isterse yapsın
    return True, ""
