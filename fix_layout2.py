with open('launcher.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Satır 372-409 arasını (tekrar eden Gmail ve Outlook) kaldır
# Önce satır numaralarını bul
start_del = None
end_del = None

for i, line in enumerate(lines):
    if '# â•â•â• GMAIL (varsayÄ±lan kapalÄ±) â•â•â•' in line and i > 390:  # İkinci Gmail
        start_del = i
    if start_del and '# â•â•â• OUTLOOK (varsayÄ±lan kapalÄ±) â•â•â•' in line and i > start_del + 20:
        # İkinci Outlook'un sonunu bul
        for j in range(i+1, len(lines)):
            if 'self._update_connection_badges()' in lines[j]:
                end_del = j
                break
        break

if start_del and end_del:
    # Tekrar eden bölümü kaldır
    new_lines = lines[:start_del] + lines[end_del:]
    
    # Web güvenliği bölümünü bul ve Telegram'dan sonra, Gmail'den önce ekle
    web_sec_lines = []
    in_web_sec = False
    web_start_idx = None
    web_end_idx = None
    
    for i, line in enumerate(new_lines):
        if '# â•â•â• WEB GÃœVENLÄ°ÄÄ°' in line:
            web_start_idx = i
            in_web_sec = True
        if in_web_sec:
            web_sec_lines.append(line)
            if i > web_start_idx + 20 and ').grid(row=2,' in line:
                web_end_idx = i + 1
                break
    
    # Web güvenliği bölümünü kaldır (eski konumundan)
    if web_start_idx and web_end_idx:
        web_content = new_lines[web_start_idx:web_end_idx]
        new_lines = new_lines[:web_start_idx] + new_lines[web_end_idx:]
        
        # Telegram bölümünü bul
        for i, line in enumerate(new_lines):
            if "_field(tg, 1, \"Kullan\u0131c\u0131 ID\", self.user_id_var)" in line:
                # Telegram'dan sonra, Gmail'den önce ekle
                insert_pos = i + 1
                # Boş satır ekle
                web_content.append('\n')
                new_lines = new_lines[:insert_pos] + ['\n'] + web_content + new_lines[insert_pos:]
                break
    
    with open('launcher.py', 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    print('Düzeltme tamamlandı!')
else:
    print('Tekrar eden bölüm bulunamadı.')
