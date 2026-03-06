"""
PROFESYONEL KOD YARDIMCISI ARAÇLARI
Git işlemleri, test çalıştırma, sembol arama, refactoring
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import settings
from .vscode_automation import (
    find_code_executable,
    resolve_workspace_path,
    run_vscode_agent_prompt,
)


def _run_git(args: List[str], cwd: str) -> Dict[str, Any]:
    """Git komutunu çalıştır ve sonucu döndür."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
        )
        output = result.stdout.strip()
        error = result.stderr.strip()
        if result.returncode != 0 and error:
            return {"error": f"Git hatasi: {error[:500]}"}
        return {"output": output, "returncode": result.returncode}
    except FileNotFoundError:
        return {"error": "Git bulunamadi. Git kurulu oldugundan emin ol."}
    except subprocess.TimeoutExpired:
        return {"error": "Git komutu zaman asimina ugradi (30sn)."}
    except Exception as e:
        return {"error": str(e)[:300]}


def _resolve_project_path(path: str) -> str:
    """Proje yolunu çözümle."""
    return resolve_workspace_path(path)


# =============================================================================
# GIT ARAÇLARI
# =============================================================================


def tool_git_status(path: str = ".") -> Dict[str, Any]:
    """Git durumunu göster - değişmiş, eklenmemiş ve staged dosyalar."""
    cwd = _resolve_project_path(path)
    result = _run_git(["status", "--porcelain", "-b"], cwd)
    if "error" in result:
        return result

    output = result["output"]
    lines = output.split("\n")

    branch = ""
    staged = []
    modified = []
    untracked = []

    for line in lines:
        if line.startswith("## "):
            branch = line[3:].split("...")[0]
            continue
        if len(line) < 3:
            continue
        x, y = line[0], line[1]
        filename = line[3:].strip()

        if x in ("M", "A", "D", "R"):
            staged.append({"status": x, "file": filename})
        if y == "M":
            modified.append(filename)
        elif y == "?":
            untracked.append(filename)

    return {
        "branch": branch,
        "staged": staged,
        "modified": modified,
        "untracked": untracked,
        "clean": not staged and not modified and not untracked,
        "summary": f"Branch: {branch} | Staged: {len(staged)} | Modified: {len(modified)} | Untracked: {len(untracked)}",
    }


def tool_git_diff(path: str = ".", staged: bool = False, file_path: str = "") -> Dict[str, Any]:
    """Git diff - değişiklikleri göster.

    Args:
        path: Proje dizini
        staged: True ise staged değişiklikleri göster
        file_path: Belirli bir dosyanın diff'i (opsiyonel)
    """
    cwd = _resolve_project_path(path)
    args = ["diff", "--stat"]
    if staged:
        args.append("--cached")
    if file_path:
        args.append("--")
        args.append(file_path)

    stat_result = _run_git(args, cwd)

    # Detaylı diff
    detail_args = ["diff"]
    if staged:
        detail_args.append("--cached")
    if file_path:
        detail_args.append("--")
        detail_args.append(file_path)

    detail_result = _run_git(detail_args, cwd)

    if "error" in stat_result:
        return stat_result

    diff_text = detail_result.get("output", "")
    if len(diff_text) > 5000:
        diff_text = diff_text[:5000] + "\n... (kesildi, cok uzun)"

    return {
        "stats": stat_result.get("output", ""),
        "diff": diff_text,
        "has_changes": bool(diff_text.strip()),
    }


def tool_git_log(path: str = ".", count: int = 10) -> Dict[str, Any]:
    """Git commit geçmişi.

    Args:
        path: Proje dizini
        count: Kaç commit gösterilsin (maks 50)
    """
    cwd = _resolve_project_path(path)
    count = min(max(1, count), 50)
    result = _run_git(
        ["log", f"-{count}", "--oneline", "--decorate", "--graph"],
        cwd,
    )
    if "error" in result:
        return result

    # Detaylı format
    detail = _run_git(
        ["log", f"-{count}", "--format=%H|%an|%ai|%s"],
        cwd,
    )
    commits = []
    if "output" in detail:
        for line in detail["output"].split("\n"):
            parts = line.split("|", 3)
            if len(parts) == 4:
                commits.append({
                    "hash": parts[0][:8],
                    "author": parts[1],
                    "date": parts[2][:10],
                    "message": parts[3],
                })

    return {
        "graph": result.get("output", ""),
        "commits": commits,
        "count": len(commits),
    }


def tool_git_commit(path: str = ".", message: str = "", add_all: bool = False) -> Dict[str, Any]:
    """Git commit yap.

    Args:
        path: Proje dizini
        message: Commit mesajı
        add_all: True ise önce tüm değişiklikleri stage'e al
    """
    if not message.strip():
        return {"error": "Commit mesaji zorunlu."}

    cwd = _resolve_project_path(path)

    if add_all:
        add_result = _run_git(["add", "-A"], cwd)
        if "error" in add_result:
            return add_result

    result = _run_git(["commit", "-m", message.strip()], cwd)
    if "error" in result:
        return result

    return {
        "success": True,
        "message": message.strip(),
        "output": result.get("output", "")[:500],
    }


def tool_git_branch(path: str = ".", action: str = "list", name: str = "") -> Dict[str, Any]:
    """Git branch işlemleri.

    Args:
        path: Proje dizini
        action: list, create, switch, delete
        name: Branch adı (create/switch/delete için)
    """
    cwd = _resolve_project_path(path)

    if action == "list":
        result = _run_git(["branch", "-a", "--sort=-committerdate"], cwd)
        if "error" in result:
            return result
        branches = [b.strip() for b in result["output"].split("\n") if b.strip()]
        current = ""
        for b in branches:
            if b.startswith("* "):
                current = b[2:]
                break
        return {"branches": branches, "current": current, "count": len(branches)}

    if not name.strip():
        return {"error": "Branch adi gerekli."}

    if action == "create":
        result = _run_git(["checkout", "-b", name.strip()], cwd)
    elif action == "switch":
        result = _run_git(["checkout", name.strip()], cwd)
    elif action == "delete":
        result = _run_git(["branch", "-d", name.strip()], cwd)
    else:
        return {"error": f"Bilinmeyen action: {action}. Kullan: list, create, switch, delete"}

    if "error" in result:
        return result
    return {"success": True, "action": action, "branch": name.strip(), "output": result.get("output", "")}


# =============================================================================
# KOD ARAMA VE ANALİZ
# =============================================================================


def tool_find_symbols(path: str, symbol: str = "", symbol_type: str = "all") -> Dict[str, Any]:
    """Projede sembol ara (fonksiyon, class, değişken tanımları).

    Args:
        path: Proje dizini
        symbol: Aranacak sembol adı (regex destekli)
        symbol_type: all, function, class, variable
    """
    cwd = _resolve_project_path(path)
    project = Path(cwd)

    if not project.exists():
        return {"error": f"Dizin bulunamadi: {cwd}"}

    patterns = {
        "function": [
            r'^\s*(?:async\s+)?def\s+(\w+)',           # Python
            r'^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)',  # JS
            r'^\s*(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(',  # Arrow fn
        ],
        "class": [
            r'^\s*class\s+(\w+)',                        # Python/JS
            r'^\s*(?:export\s+)?class\s+(\w+)',          # JS export
        ],
        "variable": [
            r'^\s*(\w+)\s*=\s*[^=]',                    # Python
            r'^\s*(?:const|let|var)\s+(\w+)\s*=',        # JS
        ],
    }

    if symbol_type == "all":
        active_patterns = []
        for pats in patterns.values():
            active_patterns.extend(pats)
    else:
        active_patterns = patterns.get(symbol_type, [])

    if not active_patterns:
        return {"error": f"Bilinmeyen symbol_type: {symbol_type}"}

    extensions = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".c", ".cpp", ".h"}
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next"}

    results: List[Dict[str, Any]] = []
    symbol_re = re.compile(symbol, re.IGNORECASE) if symbol else None

    for root, dirs, files in os.walk(cwd):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            if Path(fname).suffix not in extensions:
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, 1):
                        for pat in active_patterns:
                            m = re.match(pat, line)
                            if m:
                                name = m.group(1)
                                if symbol_re and not symbol_re.search(name):
                                    continue
                                rel = os.path.relpath(fpath, cwd)
                                results.append({
                                    "name": name,
                                    "file": rel,
                                    "line": lineno,
                                    "preview": line.strip()[:120],
                                })
            except Exception:
                continue

        if len(results) >= 200:
            break

    return {
        "symbols": results[:200],
        "count": len(results),
        "path": cwd,
        "filter": symbol or "(tumu)",
    }


def tool_code_search(path: str, pattern: str, file_types: str = "") -> Dict[str, Any]:
    """Projede regex tabanlı kod arama.

    Args:
        path: Proje dizini
        pattern: Aranacak regex pattern
        file_types: Dosya uzantıları virgülle (ör: "py,js,ts") - boş ise tümü
    """
    cwd = _resolve_project_path(path)

    if not pattern.strip():
        return {"error": "Pattern gerekli."}

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return {"error": f"Gecersiz regex: {e}"}

    extensions = None
    if file_types.strip():
        extensions = {f".{ext.strip().lstrip('.')}" for ext in file_types.split(",")}

    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
    matches: List[Dict[str, Any]] = []

    for root, dirs, files in os.walk(cwd):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            if extensions and Path(fname).suffix not in extensions:
                continue
            # Binary dosyaları atla
            if Path(fname).suffix in {".exe", ".dll", ".so", ".pyc", ".class", ".gguf", ".bin", ".png", ".jpg", ".pdf"}:
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, 1):
                        if regex.search(line):
                            rel = os.path.relpath(fpath, cwd)
                            matches.append({
                                "file": rel,
                                "line": lineno,
                                "text": line.strip()[:200],
                            })
                            if len(matches) >= 100:
                                break
            except Exception:
                continue
            if len(matches) >= 100:
                break
        if len(matches) >= 100:
            break

    return {
        "matches": matches,
        "count": len(matches),
        "pattern": pattern,
        "path": cwd,
        "truncated": len(matches) >= 100,
    }


def tool_refactor_rename(
    path: str,
    old_name: str,
    new_name: str,
    file_types: str = "py,js,jsx,ts,tsx",
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Projedeki bir ismi toplu olarak değiştir (fonksiyon, değişken, class).

    Args:
        path: Proje dizini
        old_name: Eski isim
        new_name: Yeni isim
        file_types: Hangi dosya türlerinde aranacak
        dry_run: True ise sadece nelerin değişeceğini göster, değiştirme
    """
    cwd = _resolve_project_path(path)

    if not old_name.strip() or not new_name.strip():
        return {"error": "Eski ve yeni isim gerekli."}

    extensions = {f".{ext.strip().lstrip('.')}" for ext in file_types.split(",")}
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}

    # word boundary ile eşleşme
    pattern = re.compile(r'\b' + re.escape(old_name) + r'\b')

    affected_files: List[Dict[str, Any]] = []
    total_replacements = 0

    for root, dirs, files in os.walk(cwd):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            if Path(fname).suffix not in extensions:
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    content = f.read()

                matches = list(pattern.finditer(content))
                if not matches:
                    continue

                rel = os.path.relpath(fpath, cwd)
                count = len(matches)
                total_replacements += count

                affected_files.append({
                    "file": rel,
                    "occurrences": count,
                })

                if not dry_run:
                    new_content = pattern.sub(new_name, content)
                    with open(fpath, "w", encoding="utf-8") as f:
                        f.write(new_content)

            except Exception:
                continue

    result: Dict[str, Any] = {
        "old_name": old_name,
        "new_name": new_name,
        "affected_files": affected_files,
        "total_files": len(affected_files),
        "total_replacements": total_replacements,
        "dry_run": dry_run,
    }

    if dry_run:
        result["message"] = f"{total_replacements} degisiklik yapilacak ({len(affected_files)} dosya). dry_run=false ile uygula."
    else:
        result["message"] = f"{total_replacements} degisiklik uyguland ({len(affected_files)} dosya)."

    return result


# =============================================================================
# TEST ÇALIŞTIRMA
# =============================================================================


def tool_run_tests(path: str = ".", command: str = "", timeout: int = 120) -> Dict[str, Any]:
    """Test çalıştır (otomatik algılama veya özel komut).

    Args:
        path: Proje dizini
        command: Özel test komutu (boş ise otomatik algıla)
        timeout: Timeout saniye (maks 300)
    """
    cwd = _resolve_project_path(path)
    timeout = min(max(10, timeout), 300)

    if not command.strip():
        # Otomatik algıla
        project = Path(cwd)
        if (project / "pytest.ini").exists() or (project / "pyproject.toml").exists() or (project / "setup.py").exists():
            command = "python -m pytest -v --tb=short"
        elif (project / "package.json").exists():
            command = "npm test"
        elif (project / "Cargo.toml").exists():
            command = "cargo test"
        elif (project / "go.mod").exists():
            command = "go test ./..."
        else:
            return {"error": "Test framework algilanamadi. 'command' parametresini belirt."}

    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=True,
            encoding="utf-8",
            errors="replace",
        )

        output = result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout
        error = result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr

        passed = result.returncode == 0

        return {
            "success": passed,
            "command": command,
            "returncode": result.returncode,
            "output": output,
            "errors": error if error else None,
            "summary": "Testler GECTI" if passed else "Testler BASARISIZ",
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Test zaman asimina ugradi ({timeout}sn)."}
    except Exception as e:
        return {"error": str(e)[:300]}


# =============================================================================
# VS CODE & AI KOD ASİSTANI ENTEGRASYONU
# =============================================================================


def tool_vscode_command(
    path: str,
    command: str = "",
    goto_line: int = 0,
    action: str = "open",
    extension: str = "",
    message: str = "",
) -> Dict[str, Any]:
    """VS Code'da gelişmiş işlemler: dosya aç, satıra git, terminal komutu çalıştır, AI extension chat aç.

    Args:
        path: Dosya veya klasör yolu
        command: Terminal komutu (action=terminal) veya diff dosyası.
        goto_line: Belirli satıra git (opsiyonel)
        action: open (dosya aç), terminal (komut çalıştır), diff (diff görüntüle), chat (AI extension'a mesaj gönder)
        extension: AI extension adı (action=chat için): kimicode, copilot, claudecode, codex
        message: action=chat ise, SADECE gönderilecek mesajın tam içeriği. (Örn: "sorun var mı?")
    """
    cwd = _resolve_project_path(path)
    p = Path(cwd)
    code_exe = find_code_executable()
    if not code_exe:
        return {"error": "VS Code bulunamadi. Kurulumu veya PATH ayarini kontrol edin."}

    try:
        if action == "open":
            cmd = [code_exe]
            if goto_line > 0 and p.is_file():
                cmd.extend(["--goto", f"{cwd}:{goto_line}"])
            else:
                cmd.append(cwd)
            subprocess.Popen(cmd, shell=False)
            return {
                "success": True,
                "action": "open",
                "path": cwd,
                "line": goto_line if goto_line > 0 else None,
            }

        elif action == "terminal":
            if not command.strip():
                return {"error": "Terminal action icin 'command' parametresi gerekli."}
            # VS Code entegre terminal'de komut çalıştır
            # --command sendSequence ile terminal'e yazı gönder
            subprocess.Popen([code_exe, cwd], shell=False)
            # Kısa bekleme sonra terminal komutu
            import time
            time.sleep(1)
            result = subprocess.run(
                command,
                cwd=cwd if p.is_dir() else str(p.parent),
                capture_output=True,
                text=True,
                timeout=60,
                shell=True,
                encoding="utf-8",
                errors="replace",
            )
            return {
                "success": result.returncode == 0,
                "action": "terminal",
                "command": command,
                "output": result.stdout[-2000:] if result.stdout else "",
                "errors": result.stderr[-500:] if result.stderr else None,
            }

        elif action == "diff":
            # İki dosya arasında diff
            if not command.strip():
                return {"error": "Diff action icin ikinci dosya yolunu 'command' parametresinde belirt."}
            subprocess.Popen([code_exe, "--diff", cwd, command.strip()], shell=False)
            return {
                "success": True,
                "action": "diff",
                "file1": cwd,
                "file2": command.strip(),
            }

        elif action == "chat":
            ext = (extension or "copilot").lower().strip()
            msg = message.strip() if message else (command.strip() if command else "")
            if ext == "copilot":
                return {"error": "Copilot için ortaklaştırılmış otomasyon henüz bu dalgada desteklenmiyor."}
            result = run_vscode_agent_prompt(
                path=cwd,
                agent=ext,
                prompt=msg,
                press_enter=True,
            )
            if not result.get("success"):
                return {
                    "error": str(result.get("error", "VS Code ajan otomasyonu başarısız.")),
                    "detail": str(result.get("detail", "")),
                    "agent": result.get("agent", ext),
                    "ocr_text": result.get("ocr_text", ""),
                }
            return {
                "success": True,
                "action": "chat",
                "extension": result.get("display_name", ext),
                "message": msg if msg else "(panel açıldı, mesaj yok)",
                "path": cwd,
                "note": f"{result.get('display_name', ext)} için mesaj güvenli akışla gönderildi.",
                "injection_method": result.get("injection_method", ""),
            }

        else:
            return {"error": f"Bilinmeyen action: {action}. Kullan: open, terminal, diff, chat"}

    except FileNotFoundError:
        return {"error": "VS Code ('code' komutu) bulunamadi. PATH'e ekli mi?"}
    except Exception as e:
        return {"error": str(e)[:300]}


def _type_unicode(text: str) -> None:
    """Unicode metin yaz (clipboard paste ile)."""
    import subprocess as _sp
    import platform
    import time
    try:
        import pyautogui
    except ImportError:
        return

    if text.isascii():
        pyautogui.typewrite(text, interval=0.02)
        return

    _sys = platform.system()
    if _sys == "Windows":
        p = _sp.Popen(["clip.exe"], stdin=_sp.PIPE)
        p.communicate(text.encode("utf-16-le"))
    elif _sys == "Darwin":
        p = _sp.Popen(["pbcopy"], stdin=_sp.PIPE)
        p.communicate(text.encode("utf-8"))
    else:
        p = _sp.Popen(["xclip", "-selection", "clipboard"], stdin=_sp.PIPE)
        p.communicate(text.encode("utf-8"))

    time.sleep(0.05)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.05)


def tool_claude_code_ask(
    project_path: str,
    instruction: str,
    timeout: int = 120,
) -> Dict[str, Any]:
    """Claude Code CLI'ya talimat gönder ve sonucu al.

    Args:
        project_path: Proje dizini
        instruction: Claude Code'a verilecek talimat
        timeout: Timeout saniye (maks 600)
    """
    cwd = _resolve_project_path(project_path)
    timeout = min(max(10, timeout), 600)

    if not instruction.strip():
        return {"error": "Instruction (talimat) gerekli."}

    # Claude Code CLI mevcut mu kontrol et
    try:
        check = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if check.returncode != 0:
            return {"error": "Claude Code CLI bulunamadi. 'npm install -g @anthropic-ai/claude-code' ile kur."}
    except FileNotFoundError:
        return {"error": "Claude Code CLI bulunamadi. 'npm install -g @anthropic-ai/claude-code' ile kur."}
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["claude", "-p", instruction.strip()],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )

        output = result.stdout
        if len(output) > 8000:
            output = output[:8000] + "\n... (kesildi)"

        return {
            "success": result.returncode == 0,
            "instruction": instruction.strip()[:200],
            "project": cwd,
            "output": output,
            "errors": result.stderr[-500:] if result.stderr else None,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Claude Code zaman asimina ugradi ({timeout}sn). Daha kisa bir talimat dene."}
    except Exception as e:
        return {"error": str(e)[:300]}
