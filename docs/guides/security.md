# Güvenlik Rehberi

## Güvenlik Modeli

OpenWorld 4 katmanlı güvenlik modeli kullanır:

```
┌─────────────────────────────────────────┐
│  KATMAN 1: ENGELLENEN (Forbidden)       │
│  • Finansal işlemler                    │
│  • Prompt injection                     │
│  → Her zaman reddedilir                 │
├─────────────────────────────────────────┤
│  KATMAN 2: TEHLİKELİ (Dangerous)        │
│  • Dosya silme                          │
│  • Sistem kapatma                       │
│  → Kullanıcı onayı gerekir              │
├─────────────────────────────────────────┤
│  KATMAN 3: NORMAL (Normal)              │
│  • Dosya yazma                          │
│  • Shell komutları                      │
│  → Loglanır, çalıştırılır               │
├─────────────────────────────────────────┤
│  KATMAN 4: GÜVENLİ (Safe)               │
│  • Dosya okuma                          │
│  • Screenshot                           │
│  → Hemen çalıştırılır                   │
└─────────────────────────────────────────┘
```

## Yapılandırma

### Shell Kısıtlamaları

```env
# Shell tamamen devre dışı
ENABLE_SHELL_TOOL=false

# İzin verilen prefixler
SHELL_ALLOWED_PREFIXES=git,python,node

# Timeout
SHELL_TIMEOUT_SEC=60
```

### Dosya Sistemi Kısıtlamaları

```env
# İzin verilen kök dizinler
FS_ALLOWED_ROOTS=C:\Users\Ahmet\Documents,C:\Projects

# Tam disk erişimi (tehlikeli!)
ALLOW_FULL_DISK_ACCESS=false
```

### Web Erişim Kısıtlamaları

```env
# İzin verilen domainler
WEB_ALLOWED_DOMAINS=github.com,stackoverflow.com

# Özel IP'leri engelle
WEB_BLOCK_PRIVATE_HOSTS=true
```

## Güvenlik Olayları

### Loglama

Tüm güvenlik olayları `data/logs/security.log` dosyasına kaydedilir.

### Bildirim

Kritik olaylar için:
- Konsol bildirimi
- Log kaydı
- (Opsiyonel) E-posta bildirimi

## En İyi Uygulamalar

1. **Regular Updates**: Yazılımı güncel tutun
2. **Strong Permissions**: Dosya izinlerini kısıtlayın
3. **Audit Logs**: Logları düzenli kontrol edin
4. **Backup**: Önemli verileri yedekleyin
