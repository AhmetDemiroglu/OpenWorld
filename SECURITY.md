# Security Policy

## Desteklenen Sürümler

| Sürüm | Destekleniyor |
|-------|--------------|
| 0.1.x | :white_check_mark: |

## Güvenlik Özellikleri

OpenWorld, yerel çalışan bir yapay zeka asistanı olarak aşağıdaki güvenlik özelliklerini içerir:

### 4 Katmanlı Güvenlik Modeli

| Katman | Davranış | Örnekler |
|--------|----------|----------|
| **ENGELLENEN** | Her zaman reddedilir | Finansal işlemler, prompt injection |
| **TEHLİKELİ** | Kullanıcıdan onay ister | Dosya silme, process sonlandırma |
| **NORMAL** | Loglanır, çalıştırılır | Dosya yazma, shell komutları |
| **GÜVENLİ** | Hemen çalıştırılır | Dosya okuma, screenshot, OCR |

### Güvenlik Önlemleri

1. **Prompt Injection Koruması**: Harici içerikten gelen talimatlar reddedilir
2. **Finansal İşlem Engeli**: Ödeme, transfer gibi işlemler engellenir
3. **Onay Mekanizması**: Tehlikeli işlemler için kullanıcı onayı gerekir
4. **Loglama**: Tüm işlemler loglanır

## Güvenlik Açığı Bildirimi

Güvenlik açığı bulduysanız lütfen şu adımları izleyin:

1. **Doğrudan Bildirim**: security@openworld.local adresine e-posta gönderin
2. **GitHub Issues**: Hassas olmayan konular için GitHub Issues kullanabilirsiniz
3. **Detaylı Bilgi**: Açığı nasıl tetikleyeceğinizi adım adım açıklayın

## Sorumluluk Reddi

OpenWorld yerel olarak çalışan bir uygulamadır. Kullanıcı:

- Kendi bilgisayarında çalıştırır
- Kendi sorumluluğunda kullanır
- Üçüncü taraflara karşı sorumludur

## İletişim

- Güvenlik: security@openworld.local
- Genel: contact@openworld.local
