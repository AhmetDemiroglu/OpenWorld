import re

with open('backend/app/tools/registry.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find all tool names in TOOLS dict
tools = re.findall(r'^\s+"(\w+)"\s*:\s*\(', content, re.MULTILINE)

print(f'Toplam tool sayisi: {len(tools)}')
print()

categories = {
    'Dosya Sistemi': ['list_directory', 'read_file', 'write_file', 'delete_file', 'copy_file', 'move_file', 'search_files'],
    'Kod Analiz': ['analyze_code', 'find_code_patterns'],
    'Ofis/Rapor': ['create_word_document', 'create_markdown_report'],
    'Sistem': ['get_system_info', 'list_processes', 'kill_process'],
    'Ağ': ['network_info', 'ping_host'],
    'Shell': ['execute_command'],
    'Görev/Takvim': ['add_task', 'list_tasks', 'complete_task', 'add_calendar_event', 'list_calendar_events'],
    'E-posta': ['create_email_draft', 'check_gmail_messages', 'check_outlook_messages'],
    'Web/Araştırma': ['search_news', 'fetch_web_page', 'research_and_report', 'compare_topics', 'research_note'],
    'Ekran': ['screenshot_desktop', 'screenshot_webpage', 'find_image_on_screen', 'click_on_screen', 'type_text', 'press_key', 'mouse_position', 'mouse_move', 'drag_to', 'scroll', 'hotkey'],
    'Ses': ['start_audio_recording', 'stop_audio_recording', 'play_audio', 'text_to_speech'],
    'Webcam': ['list_cameras', 'webcam_capture', 'webcam_record_video'],
    'USB': ['list_usb_devices', 'eject_usb_drive'],
    'Dialog': ['alert', 'confirm', 'prompt'],
    'Windows': ['get_window_list', 'activate_window', 'minimize_all_windows', 'lock_workstation', 'shutdown_system'],
    'OCR': ['ocr_screenshot', 'ocr_image'],
    'ZIP': ['create_zip', 'extract_zip', 'list_zip_contents', 'create_tar'],
    'PDF': ['read_pdf', 'create_pdf', 'merge_pdfs', 'split_pdf'],
    'Word': ['create_docx', 'read_docx', 'add_to_docx'],
    'Excel': ['create_excel', 'read_excel', 'add_to_excel'],
    'Git/Kod': ['git_status', 'git_diff', 'git_log', 'git_commit', 'git_branch', 'find_symbols', 'code_search', 'refactor_rename', 'run_tests', 'vscode_command', 'claude_code_ask'],
    'Not Defteri': ['notebook_create', 'notebook_add_note', 'notebook_complete_step', 'notebook_status', 'notebook_list', 'notebook_add_step'],
    'Hafıza': ['memory_store', 'memory_recall', 'memory_stats'],
    'Diğer': ['open_in_vscode', 'open_folder', 'create_folder', 'analyze_project_code']
}

total_by_category = {}
for cat, items in categories.items():
    count = sum(1 for t in items if t in tools)
    total_by_category[cat] = count
    if count > 0:
        print(f'{cat}: {count}')

print()
print('Tum tools:')
for i, tool in enumerate(tools, 1):
    print(f'{i:2}. {tool}')

# Find missing tools
all_listed = set()
for items in categories.values():
    all_listed.update(items)

missing = set(tools) - all_listed
if missing:
    print()
    print('Kategorize edilmemis tools:', missing)

extra = all_listed - set(tools)
if extra:
    print()
    print('README\'de var ama registry\'de yok:', extra)
