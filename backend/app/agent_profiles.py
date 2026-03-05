"""
agent_profiles.py — Sub-ajan profilleri.
Her profil: focused tool listesi + sistem prompt eki.
Tek Ollama örneği kullanılır; sadece araç seti ve prompt değişir.
"""
from __future__ import annotations
from typing import Dict, Any

AGENT_PROFILES: Dict[str, Dict[str, Any]] = {

    # ── Araştırma ────────────────────────────────────────────────────────────
    "research": {
        "name": "Araştırma Ajanı",
        "description": "Web araştırması, haber tarama, PDF rapor oluşturma",
        "tools": [
            "search_news",
            "fetch_web_page",
            "research_and_report",
            "research_async",
            "compare_topics",
            "research_note",
            "notebook_create",
            "notebook_add_note",
            "notebook_complete_step",
            "notebook_status",
            "notebook_list",
            "read_file",
            "write_file",
            "create_markdown_report",
        ],
        "system_prompt_suffix": (
            "\n\n[ARAŞTIRMA MODU] Sen bir araştırma uzmanısın. "
            "Görevlerin: web/haber araması, kaynak okuma, sentez ve rapor. "
            "Kompleks konularda önce alt sorgular üret, birden fazla kaynak tara. "
            "Uzun araştırmalar için research_async kullan."
        ),
    },

    # ── Masaüstü ─────────────────────────────────────────────────────────────
    "desktop": {
        "name": "Masaüstü Ajanı",
        "description": "Ekran görüntüsü, fare/klavye kontrolü, OCR",
        "tools": [
            "screenshot_desktop",
            "screenshot_webpage",
            "click_on_screen",
            "type_text",
            "press_key",
            "hotkey",
            "drag_to",
            "scroll",
            "mouse_move",
            "mouse_position",
            "find_image_on_screen",
            "ocr_screenshot",
            "ocr_image",
            "get_window_list",
            "activate_window",
            "minimize_all_windows",
            "start_approval_watcher",
            "stop_approval_watcher",
            "wait_and_accept_approval",
            "approval_watcher_status",
        ],
        "system_prompt_suffix": (
            "\n\n[MASAÜSTÜ MODU] Sen bir masaüstü otomasyon uzmanısın. "
            "Her UI etkileşimi öncesi screenshot al ve konumu doğrula. "
            "Tıklama/yazma işlemlerinde önce screenshot_desktop ile ekranı gör."
        ),
    },

    # ── Kod ──────────────────────────────────────────────────────────────────
    "code": {
        "name": "Kod Ajanı",
        "description": "Git, VS Code, kod analizi, test, refactor",
        "tools": [
            "read_file",
            "write_file",
            "list_directory",
            "search_files",
            "analyze_code",
            "find_code_patterns",
            "git_status",
            "git_log",
            "git_diff",
            "git_commit",
            "git_branch",
            "code_search",
            "find_symbols",
            "refactor_rename",
            "run_tests",
            "vscode_command",
            "claude_code_ask",
            "execute_command",
            "open_in_vscode",
        ],
        "system_prompt_suffix": (
            "\n\n[KOD MODU] Sen bir yazılım geliştirme uzmanısın. "
            "Kod değişikliği yapmadan önce mevcut kodu oku ve anla. "
            "Git değişikliklerinde her zaman git_status ile başla."
        ),
    },

    # ── Dosya ────────────────────────────────────────────────────────────────
    "file": {
        "name": "Dosya Ajanı",
        "description": "Dosya yönetimi, PDF/Word/Excel oluşturma ve okuma",
        "tools": [
            "list_directory",
            "read_file",
            "write_file",
            "delete_file",
            "copy_file",
            "move_file",
            "search_files",
            "create_zip",
            "extract_zip",
            "list_zip_contents",
            "create_tar",
            "extract_tar",
            "read_pdf",
            "create_pdf",
            "merge_pdfs",
            "split_pdf",
            "create_docx",
            "read_docx",
            "add_to_docx",
            "create_excel",
            "read_excel",
            "add_to_excel",
            "create_word_document",
            "create_markdown_report",
            "create_folder",
            "open_folder",
        ],
        "system_prompt_suffix": (
            "\n\n[DOSYA MODU] Sen bir dosya yönetim uzmanısın. "
            "Silme işlemlerinde önce dosyanın varlığını doğrula. "
            "Büyük dosyalarda offset/limit kullanarak parça parça oku."
        ),
    },

    # ── Sistem ───────────────────────────────────────────────────────────────
    "system": {
        "name": "Sistem Ajanı",
        "description": "Sistem bilgisi, process yönetimi, ağ işlemleri",
        "tools": [
            "get_system_info",
            "list_processes",
            "kill_process",
            "execute_command",
            "network_info",
            "ping_host",
            "get_window_list",
            "minimize_all_windows",
            "lock_workstation",
            "shutdown_system",
            "list_usb_devices",
            "eject_usb_drive",
        ],
        "system_prompt_suffix": (
            "\n\n[SİSTEM MODU] Sen bir sistem yönetim uzmanısın. "
            "Tehlikeli komutlar (shutdown, kill, format) öncesi kullanıcıyı bildir. "
            "Process sonlandırmada önce process adını doğrula."
        ),
    },
}
