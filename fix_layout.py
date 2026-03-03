import re

with open('launcher.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. HIZLI İŞLEMLER ve Kullanıcı Profili arasına DURUM ekle
old_pattern1 = '        self._btn(quick, "Kaydet", self.save_env, bg="#7c3aed").pack(side="right")\n\n        # '

new_pattern1 = '''        self._btn(quick, "Kaydet", self.save_env, bg="#7c3aed").pack(side="right")

        # ═══ DURUM (Loglar en üste taşındı) ═══
        status_frame = tk.Frame(sf, bg=BG)
        status_frame.pack(fill="x", padx=14, pady=(6, 10))
        tk.Label(status_frame, textvariable=self.status_var, fg="#93c5fd", bg=CARD_BG,
                 font=("Consolas", 9), anchor="w", padx=10, pady=8).pack(fill="x")
        self._update_connection_badges()

        # '''

content = content.replace(old_pattern1, new_pattern1)

# 2. WEB GÜVENLİĞİ bölümünü bul
web_start_marker = 'Web G'
gmail_start_marker = 'Gmail Entegrasyonu'

web_start = content.find(web_start_marker)
gmail_start = content.find(gmail_start_marker)

if web_start != -1 and gmail_start != -1:
    # Web güvenliği bölümünün başlangıcını bul (yorum satırından başlat)
    web_sec_start = content.rfind('# ', 0, web_start)
    # Gmail bölümünün başlangıcını bul
    gmail_sec_start = content.rfind('# ', 0, gmail_start)
    
    # Web güvenliği içeriğini al
    web_sec_end = gmail_sec_start
    web_sec_content = content[web_sec_start:web_sec_end]
    
    # Web güvenliği bölümünü kaldır
    content = content[:web_sec_start] + content[web_sec_end:]
    
    # Şimdi Telegram'dan sonra, Gmail'den önce ekle
    # Telegram bölümünü bul
    tg_field = '_field(tg, 1, "Kullanıcı ID", self.user_id_var)'
    tg_pos = content.find(tg_field)
    
    if tg_pos != -1:
        # Telegram bölümünün sonunu bul
        tg_end = content.find('\n\n', tg_pos)
        if tg_end == -1:
            tg_end = content.find('\n        #', tg_pos)
        tg_end += 1
        
        # Gmail bölümünü bul
        gmail_marker = 'Gmail Entegrasyonu'
        gmail_pos = content.find(gmail_marker)
        
        if gmail_pos != -1:
            gmail_sec_start = content.rfind('# ', 0, gmail_pos)
            
            # Web güvenliği içeriğini yeni konumuna ekle (yorumu değiştir)
            new_web_sec = web_sec_content.replace('Web Güvenliği', "Web Güvenliği (Gmail'in üzerine taşındı)")
            
            # Gmail bölümünden önce ekle
            content = content[:gmail_sec_start] + new_web_sec + content[gmail_sec_start:]

with open('launcher.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Düzenlemeler tamamlandı!')
print('1. Durum (loglar) butonların altına taşındı')
print('2. Web Güvenliği Gmail entegrasyonunun üzerine taşındı')
