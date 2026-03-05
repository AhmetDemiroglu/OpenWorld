from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import hashlib
import http.server
import json
import os
import re
import secrets
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

try:
    import winreg
except Exception:  # pragma: no cover - Windows disi ortamlarda fallback
    winreg = None

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
BROKEN_VENV_PYTHON = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
VENV_PYTHON = BROKEN_VENV_PYTHON
ENV_PATH = BACKEND_DIR / ".env"
QWEN_INSTALL_SCRIPT = ROOT / "scripts" / "install-qwen35-9b.ps1"
LOG_DIR = ROOT / "data" / "logs"
DEFAULT_TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob_from_bytes(data: bytes) -> DATA_BLOB:
    buf = (ctypes.c_byte * len(data))(*data)
    return DATA_BLOB(len(data), buf)


def _bytes_from_blob(blob: DATA_BLOB) -> bytes:
    size = int(blob.cbData)
    ptr = ctypes.cast(blob.pbData, ctypes.POINTER(ctypes.c_ubyte))
    return bytes(ptr[:size]) if size > 0 else b""


def encrypt_text(text: str) -> str:
    raw = text.encode("utf-8")
    if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "crypt32"):
        in_blob = _blob_from_bytes(raw)
        out_blob = DATA_BLOB()
        ok = ctypes.windll.crypt32.CryptProtectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob))
        if not ok:
            raise RuntimeError("CryptProtectData failed")
        try:
            encrypted = _bytes_from_blob(out_blob)
            return "dpapi:" + base64.b64encode(encrypted).decode("ascii")
        finally:
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)
    return "b64:" + base64.b64encode(raw).decode("ascii")


def decrypt_text(value: str) -> str:
    if not value:
        return ""
    if value.startswith("dpapi:"):
        payload = base64.b64decode(value.split(":", 1)[1])
        in_blob = _blob_from_bytes(payload)
        out_blob = DATA_BLOB()
        ok = ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob))
        if not ok:
            raise RuntimeError("CryptUnprotectData failed")
        try:
            return _bytes_from_blob(out_blob).decode("utf-8")
        finally:
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)
    if value.startswith("b64:"):
        return base64.b64decode(value.split(":", 1)[1]).decode("utf-8")
    return value


GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")


def _looks_like_google_client_id(value: str) -> bool:
    return value.endswith(".apps.googleusercontent.com") and "." in value


def _looks_like_guid(value: str) -> bool:
    return bool(GUID_RE.match(value))


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def _post_form(url: str, payload: dict[str, str]) -> dict:
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
        return json.loads(body)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        detail = raw
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                detail = (
                    parsed.get("error_description")
                    or parsed.get("error")
                    or parsed.get("message")
                    or raw
                )
        except Exception:
            pass
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def _run_loopback_oauth(
    auth_url: str,
    expected_state: str,
    timeout_sec: int = 180,
    redirect_host: str = "127.0.0.1",
    redirect_path: str = "/callback",
) -> tuple[str, str]:
    result: dict[str, str] = {}

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            state = params.get("state", [""])[0]
            if state != expected_state:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid state")
                return
            if "error" in params:
                result["error"] = params.get("error", ["unknown_error"])[0]
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OAuth cancelled or denied.")
                return
            code = params.get("code", [""])[0]
            if code:
                result["code"] = code
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OpenWorld OAuth complete. You can close this tab.")
                return
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing code")

        def log_message(self, format, *args):  # noqa: A003
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), CallbackHandler)
    server.timeout = 1
    path = redirect_path if redirect_path.startswith("/") else f"/{redirect_path}"
    redirect_uri = f"http://{redirect_host}:{server.server_port}{path}"
    webbrowser.open(auth_url.replace("__REDIRECT_URI__", urllib.parse.quote(redirect_uri, safe="")))
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        server.handle_request()
        if "code" in result or "error" in result:
            break
    server.server_close()
    if "error" in result:
        raise RuntimeError(f"OAuth error: {result['error']}")
    if "code" not in result:
        raise RuntimeError("OAuth timeout. Browser approval not completed.")
    return result["code"], redirect_uri

# ---------------------------------------------------------------------------
#  TOOLTIP HELPER
# ---------------------------------------------------------------------------
class ToolTip:
    """Tkinter widget'lar\u0131 i\u00e7in g\u00f6rsel tooltip (ba\u015fl\u0131k + a\u00e7\u0131klama)."""
    def __init__(self, widget: tk.Widget, text: str, title: str = "", delay: int = 350):
        self.widget = widget
        self.title = title
        self.text = text
        self.delay = delay
        self._tip_window: tk.Toplevel | None = None
        self._after_id: str | None = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._hide)

    def _schedule(self, _event=None):
        self._after_id = self.widget.after(self.delay, self._show)

    def _show(self):
        if self._tip_window:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)
        outer = tk.Frame(tw, bg="#334155", bd=0)
        outer.pack()
        inner = tk.Frame(outer, bg="#0f172a", bd=0)
        inner.pack(padx=1, pady=1)
        if self.title:
            tk.Label(
                inner, text=self.title, justify="left",
                bg="#1e293b", fg="#60a5fa", font=("Segoe UI", 9, "bold"),
                anchor="w", padx=10, pady=5,
            ).pack(fill="x")
            tk.Frame(inner, bg="#334155", height=1).pack(fill="x")
        tk.Label(
            inner, text=self.text, justify="left", wraplength=340,
            bg="#0f172a", fg="#cbd5e1", font=("Segoe UI", 9),
            anchor="w", padx=10, pady=7,
        ).pack(fill="x")
        self._tip_window = tw

    def _hide(self, _event=None):
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None
        if self._tip_window:
            self._tip_window.destroy()
            self._tip_window = None


# ---------------------------------------------------------------------------
#  HELP GUIDE CONTENT
# ---------------------------------------------------------------------------
SETUP_GUIDE = """\
\u2501\u2501\u2501\u2501\u2501\u2501  OPENWORLD KURULUM REHBER\u0130  \u2501\u2501\u2501\u2501\u2501\u2501

  Bu rehber sizi s\u0131f\u0131rdan \u00e7al\u0131\u015fan bir sisteme
  ad\u0131m ad\u0131m g\u00f6t\u00fcrecektir.


\u24ea  \u00d6N GEREKL\u0130L\u0130KLER  (Bir Kere Yap)
\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
   Python 3.11 veya \u00fcst\u00fc:
   \u2022 https://python.org/downloads adresinden
     indirin ve kurun
   \u2022 Kurulumda \u201cAdd Python to PATH\u201d
     kutusunu MUTLAKA i\u015faretleyin!

   Node.js 20 veya \u00fcst\u00fc:
   \u2022 https://nodejs.org adresinden LTS
     s\u00fcr\u00fcm\u00fcn\u00fc indirin ve kurun

   Tesseract OCR (\u00f6nerilir):
   \u2022 \u0130ndirme: https://github.com/UB-Mannheim/tesseract/wiki
   \u2022 Kurulum dosyas\u0131:
     C:\\Program Files\\Tesseract-OCR\\tesseract.exe
   \u2022 PATH'e eklenecek klas\u00f6r:
     C:\\Program Files\\Tesseract-OCR
   \u2022 Launcher ayar\u0131:
     OCR / Tesseract b\u00f6l\u00fcm\u00fcn\u00fc a\u00e7\u0131n
     Tesseract Yolu alan\u0131na tam yolu yaz\u0131n
     OCR b\u00f6l\u00fcm\u00fcndeki \u201cKaydet\u201d butonuna bas\u0131n
   \u2022 Do\u011frulama:
     tesseract --version
   \u2022 Vision \u00f6zelli\u011fi olmayan modellerde OCR zorunludur:
     - G\u00f6rselden metin okuma
     - IDE onay penceresi izleme / kabul etme
     - Ekran \u00fcst\u00fc metin alg\u0131lama

   NOT: Bu iki program zaten kuruluysa
   bu ad\u0131m\u0131 atlayabilirsiniz.


\u2460  OLLAMA Y\u00dcKLE  (Yapay Zek\u00e2 Motoru)
\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
   \u2022 https://ollama.com adresine gidin
   \u2022 \u0130\u015fletim sisteminize uygun versiyonu indirin
   \u2022 Kurulumu tamamlay\u0131n (Next > Next > Finish)
   \u2022 Kurulum sonras\u0131 Ollama otomatik ba\u015flar


\u2461  MODEL \u0130ND\u0130R  (Yapay Zek\u00e2 Beyni)
\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
   Varsay\u0131lan model: qwen3.5:9b-q4_K_M (~5 GB)
   Bu model t\u00fcm kullan\u0131c\u0131larda haz\u0131r gelir.

   H\u0131zl\u0131 y\u00f6ntem:
   \u2022 \u201cQwen3.5\u201d butonuna t\u0131klay\u0131n (tek t\u0131k)
   \u2022 Model otomatik indirilir ve ayarlan\u0131r

   Manuel y\u00f6ntem:
   \u2022 \u201cModel \u00c7ek\u201d butonuna t\u0131klay\u0131n
   \u2022 \u201cModel Ad\u0131\u201d alan\u0131ndaki modeli \u00e7eker
   \u2022 ~5 GB, internet h\u0131z\u0131na g\u00f6re 10-30 dk

   Farkl\u0131 model kullanmak isterseniz:
   \u2022 \u201cModel Ad\u0131\u201d alan\u0131n\u0131 de\u011fi\u015ftirin
     (\u00f6rn: llama3:8b, mistral, gemma2 vb.)
   \u2022 \u201cModel \u00c7ek\u201d ile yeni modeli indirin
   \u2022 Desteklenen modeller: ollama.com/library

   GGUF (ileri d\u00fczey):
   \u2022 \u201cMotor\u201d alan\u0131n\u0131 \u201cllama_cpp\u201d yap\u0131n
   \u2022 \u201cGGUF Yolu\u201d veya \u201cGGUF URL\u201d ile
     kendi model dosyan\u0131z\u0131 kullanabilirsiniz


\u2462  KURULUM  (Ba\u011f\u0131ml\u0131l\u0131klar\u0131 Y\u00fckle)
\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
   \u201cKurulum\u201d butonuna bas\u0131n. Bu i\u015flem:
   \u2022 Python sanal ortam\u0131 (venv) olu\u015fturur
   \u2022 Backend Python paketlerini y\u00fckler
     (FastAPI, LangChain, Ollama vb.)
   \u2022 Frontend ba\u011f\u0131ml\u0131l\u0131klar\u0131n\u0131 y\u00fckler
     (npm install)
   \u2022 \u0130lk seferde 5-10 dk s\u00fcrebilir


\u2463  BA\u015eLAT  (Servisleri \u00c7al\u0131\u015ft\u0131r)
\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
   \u2022 \u201cBa\u015flat\u201d butonuna t\u0131klay\u0131n
   \u2022 Backend API sunucusu ba\u015flar
   \u2022 Telegram botu ba\u015flar (ayarl\u0131ysa)
   \u2022 \u201cAray\u00fcz\u201d butonuyla web panelini a\u00e7\u0131n
   \u2022 Adres: http://127.0.0.1:8000
   \u2022 \u0130lk a\u00e7\u0131l\u0131\u015f biraz yava\u015f olabilir
     (model belle\u011fe y\u00fckleniyor)


\u2501\u2501\u2501\u2501\u2501\u2501  ENTEGRASYONLAR (\u0130ste\u011fe Ba\u011fl\u0131)  \u2501\u2501\u2501\u2501\u2501\u2501


\u2464  TELEGRAM BOTU BA\u011eLAMA
\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
   Bot Token alma:
   \u2022 Telegram'\u0131 a\u00e7\u0131n, @BotFather'\u0131 aray\u0131n
   \u2022 /newbot komutu g\u00f6nderin
   \u2022 Bot i\u00e7in bir isim ve kullan\u0131c\u0131 ad\u0131 girin
   \u2022 BotFather size token verecek
     (\u00f6rn: 123456:ABC-DEF1234ghIkl-zyx57W2v)
   \u2022 Token'\u0131 Launcher'da \u201cBot Token\u201d alan\u0131na
     yap\u0131\u015ft\u0131r\u0131n

   Kullan\u0131c\u0131 ID alma:
   \u2022 Telegram'da @userinfobot'\u0131 aray\u0131n
   \u2022 /start komutu g\u00f6nderin
   \u2022 Size ID numaran\u0131z\u0131 s\u00f6yleyecek
     (\u00f6rn: 857792648)
   \u2022 Bu ID'yi \u201cKullan\u0131c\u0131 ID\u201d alan\u0131na yaz\u0131n
   \u2022 \u201cKaydet\u201d butonuna bas\u0131n


\u2465  GMA\u0130L ENTEGRASYONU
\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
   \u2022 Google Cloud Console'\u0131 a\u00e7\u0131n
     console.cloud.google.com/apis/credentials
   \u2022 \u201c+ CREATE CREDENTIALS\u201d > OAuth client ID
   \u2022 Application type: Desktop App
   \u2022 Client ID'\u0131 kopyalay\u0131p Launcher'a
     yap\u0131\u015ft\u0131r\u0131n
   \u2022 \u201cOAuth Ba\u011flan\u201d butonuna t\u0131klay\u0131n
   \u2022 A\u00e7\u0131lan taray\u0131c\u0131da Google hesab\u0131n\u0131zla
     izin verin
   \u2022 Token otomatik kaydedilir


\u2466  OUTLOOK ENTEGRASYONU
\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
   \u2022 Azure Portal > App registrations
     portal.azure.com
   \u2022 \u201cNew registration\u201d ile uygulama
     kay\u0131t edin
   \u2022 Application (client) ID de\u011ferini
     Launcher'\u0131n \u201cClient ID\u201d alan\u0131na yaz\u0131n
   \u2022 Tenant ID: genellikle \u201ccommon\u201d b\u0131rak\u0131n
   \u2022 \u201cOAuth Ba\u011flan\u201d butonuyla Microsoft
     hesab\u0131n\u0131za izin verin
   \u2022 Token otomatik kaydedilir


\u2501\u2501\u2501\u2501\u2501\u2501  SORUN G\u0130DERME  \u2501\u2501\u2501\u2501\u2501\u2501

   \u2716 Backend ba\u015flat\u0131lam\u0131yor
     \u2192 Ollama'\u0131n \u00e7al\u0131\u015ft\u0131\u011f\u0131ndan emin olun
     \u2192 \u201cKurulum\u201d butonuna tekrar bas\u0131n

   \u2716 Model bulunamad\u0131
     \u2192 \u201cModel \u00c7ek\u201d / \u201cQwen3.5\u201d butonuna bas\u0131n

   \u2716 \u0130lk a\u00e7\u0131l\u0131\u015f yava\u015f
     \u2192 Model belle\u011fe y\u00fckleniyor, 1-2 dk bekleyin

   \u2716 ChromaDB hatas\u0131
     \u2192 \u201cKurulum\u201d butonuna tekrar bas\u0131n

   \u2716 \u201cVenv bulunamad\u0131\u201d hatas\u0131
     \u2192 \u201cKurulum\u201d butonuna bas\u0131n

   \u2716 \u201cTesseract is not installed\u201d hatas\u0131
     \u2192 Tesseract'\u0131 C:\\Program Files\\Tesseract-OCR klas\u00f6r\u00fcne kurun
     \u2192 Launcher > OCR / Tesseract b\u00f6l\u00fcm\u00fcn\u00fc a\u00e7\u0131n
     \u2192 Tesseract Yolu alan\u0131na tam yolu yaz\u0131n:
       C:\\Program Files\\Tesseract-OCR\\tesseract.exe
     \u2192 OCR b\u00f6l\u00fcm\u00fcndeki \u201cKaydet\u201d butonuna bas\u0131n
     \u2192 Yeni terminal a\u00e7\u0131p tesseract --version ile kontrol edin


\u2501\u2501\u2501\u2501\u2501\u2501  \u0130LET\u0130\u015e\u0130M  \u2501\u2501\u2501\u2501\u2501\u2501

   Geli\u015ftirici : Ahmet Demiro\u011flu
   E-posta   : ahmetdemiroglu89@gmail.com
   GitHub    : github.com/AhmetDemiroglu
"""

APP_VERSION = "1.0.0"


class LauncherApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("OpenWorld Launcher")
        self.root.configure(bg="#1e293b")
        self.root.minsize(700, 500)
        # Center on screen, 80% of screen size
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = min(int(sw * 0.55), 900), min(int(sh * 0.8), 750)
        self.root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        self.backend_proc: subprocess.Popen | None = None
        self.telegram_proc: subprocess.Popen | None = None

        self.status_var = tk.StringVar(value="Haz\u0131r")
        self.token_var = tk.StringVar()
        self.user_id_var = tk.StringVar()
        self.gmail_token_var = tk.StringVar()
        self.gmail_refresh_var = tk.StringVar()
        self.gmail_client_id_var = tk.StringVar()
        self.gmail_client_secret_var = tk.StringVar()
        self.gmail_conn_var = tk.StringVar(value="Durum: Bağlı değil")
        self.outlook_token_var = tk.StringVar()
        self.outlook_refresh_var = tk.StringVar()
        self.outlook_client_id_var = tk.StringVar()
        self.outlook_tenant_var = tk.StringVar(value="common")
        self.outlook_conn_var = tk.StringVar(value="Durum: Bağlı değil")
        self.backend_var = tk.StringVar(value="ollama")
        self.model_var = tk.StringVar(value="qwen3.5:9b-q4_K_M")
        self.gguf_var = tk.StringVar(value="../models/Qwen3.5-9B-Q4_K_M.gguf")
        self.gguf_url_var = tk.StringVar(
            value="https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/Qwen3.5-9B-Q4_K_M.gguf?download=true"
        )
        self.owner_name_var = tk.StringVar(value="Ahmet")
        self.owner_profile_var = tk.StringVar(value="Teknoloji, otomasyon, urun gelistirme")
        self.web_domains_var = tk.StringVar(value="")
        self.tesseract_cmd_var = tk.StringVar(value=DEFAULT_TESSERACT_CMD)
        self.web_allow_internet_var = tk.BooleanVar(value=True)  # Internet baglantisi acik/kapali
        self.web_block_private_var = tk.BooleanVar(value=False)  # Yerel ağ erişimine izin ver
        self.enable_shell_var = tk.BooleanVar(value=True)  # Shell tool varsayılan açık

        self._load_env()
        self._build_ui()
        self._tick_status()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        BG = "#1e293b"
        CARD_BG = "#263347"
        LABEL_FG = "#cbd5e1"
        TEXT_FG = "#f1f5f9"
        HINT_FG = "#94a3b8"
        ACCENT = "#3b82f6"
        GREEN = "#22c55e"
        RED = "#ef4444"
        SECTION_FG = "#67e8f9"
        TOGGLE_FG = "#93c5fd"

        pad = {"padx": 8, "pady": 3}
        entry_opts = {"bg": "#1a2332", "fg": TEXT_FG, "insertbackground": TEXT_FG,
                      "relief": "flat", "highlightthickness": 1, "highlightbackground": "#475569",
                      "highlightcolor": ACCENT, "font": ("Segoe UI", 9)}

        # --- Baslik ---
        title_bar = tk.Frame(self.root, bg=BG)
        title_bar.pack(fill="x", padx=14, pady=(10, 0))
        tk.Label(title_bar, text="\u25c6 OpenWorld Launcher", fg="#f9fafb", bg=BG,
                 font=("Segoe UI", 13, "bold")).pack(side="left")
        tk.Label(title_bar, text=f"v{APP_VERSION}", fg=HINT_FG, bg=BG,
                 font=("Segoe UI", 9)).pack(side="left", padx=(6, 0))

        # --- Kaydirilabilir alan ---
        container = tk.Frame(self.root, bg=BG)
        container.pack(fill="both", expand=True, padx=0, pady=0)

        canvas = tk.Canvas(container, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self._scroll_frame = tk.Frame(canvas, bg=BG)

        self._scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        self._canvas_win = canvas.create_window((0, 0), window=self._scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def _sync_width(event):
            canvas.itemconfigure(self._canvas_win, width=event.width)
        canvas.bind("<Configure>", _sync_width)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        sf = self._scroll_frame  # shorthand

        # --- Collapsible section helper ---
        def _collapsible(parent, title, expanded=True):
            outer = tk.Frame(parent, bg=BG)
            outer.pack(fill="x", padx=12, pady=(6, 2))

            header = tk.Frame(outer, bg=CARD_BG, cursor="hand2")
            header.pack(fill="x")
            header.configure(padx=0, pady=0)

            arrow_var = tk.StringVar(value="\u25bc" if expanded else "\u25b6")
            arrow = tk.Label(header, textvariable=arrow_var, fg=TOGGLE_FG, bg=CARD_BG,
                             font=("Segoe UI", 9), cursor="hand2")
            arrow.pack(side="left", padx=(10, 4), pady=6)

            lbl = tk.Label(header, text=title, fg=SECTION_FG, bg=CARD_BG,
                           font=("Segoe UI", 10, "bold"), cursor="hand2")
            lbl.pack(side="left", pady=6)

            body = tk.Frame(outer, bg=CARD_BG)
            if expanded:
                body.pack(fill="x")

            def _toggle(e=None):
                if body.winfo_manager():
                    body.pack_forget()
                    arrow_var.set("\u25b6")
                else:
                    body.pack(fill="x")
                    arrow_var.set("\u25bc")

            for w in (header, arrow, lbl):
                w.bind("<Button-1>", _toggle)

            inner = tk.Frame(body, bg=CARD_BG)
            inner.pack(fill="x", padx=10, pady=(2, 8))
            inner.columnconfigure(1, weight=1)
            return inner

        # --- Field helper with optional hint below entry ---
        def _field(parent, row, label, var, hint="", show=""):
            r = row * 2  # double rows: even=field, odd=hint
            tk.Label(parent, text=label, fg=LABEL_FG, bg=CARD_BG,
                     font=("Segoe UI", 9), anchor="w").grid(row=r, column=0, sticky="w", **pad)
            opts = {**entry_opts}
            if show:
                opts["show"] = show
            tk.Entry(parent, textvariable=var, **opts).grid(row=r, column=1, sticky="ew", **pad)
            if hint:
                tk.Label(parent, text=hint, fg=HINT_FG, bg=CARD_BG,
                         font=("Segoe UI", 8), anchor="w").grid(row=r + 1, column=1, sticky="w", padx=8, pady=(0, 2))

        # === ILKKARSILAMA BANNER ===
        self._banner_frame = tk.Frame(sf, bg="#1e3a5f")
        self._banner_frame.pack(fill="x", padx=14, pady=(8, 2))
        tk.Label(
            self._banner_frame, text="\u0130lk kez mi kullan\u0131yorsunuz A\u015fa\u011f\u0131daki Yard\u0131m butonuna t\u0131klay\u0131n.",
            fg="#93c5fd", bg="#1e3a5f", font=("Segoe UI", 9), anchor="w",
        ).pack(side="left", padx=8, pady=6)
        tk.Button(
            self._banner_frame, text="\u2715", command=self._dismiss_banner,
            bg="#1e3a5f", fg="#64748b", bd=0, font=("Segoe UI", 9, "bold"),
            cursor="hand2", activebackground="#1e3a5f", activeforeground="white",
        ).pack(side="right", padx=4)

        # === HIZLI ISLEMLER ===
        quick = tk.Frame(sf, bg=BG)
        quick.pack(fill="x", padx=14, pady=(8, 2))

        btn_start = self._btn(quick, "Ba\u015flat", self.start_all, bg=GREEN)
        btn_start.pack(side="left", padx=(0, 4))
        ToolTip(btn_start, "Backend API ve Telegram botunu başlatır.\nOllama'ın açık olduğundan emin olun.", title="▶  Başlat")

        btn_stop = self._btn(quick, "Durdur", self.stop_all, bg=RED)
        btn_stop.pack(side="left", padx=(0, 4))
        ToolTip(btn_stop, "Backend ve Telegram servislerini kapatır.", title="■  Durdur")

        btn_ui = self._btn(quick, "Aray\u00fcz", self.open_ui, bg=ACCENT)
        btn_ui.pack(side="left", padx=(0, 4))
        ToolTip(btn_ui, "Web arayüzünü tarayıcıda açar.\nÖnce Başlat butonuna basmalısınız.", title="🌐  Arayüz")

        btn_setup = self._btn(quick, "Kurulum", self.setup_all, bg="#64748b")
        btn_setup.pack(side="left", padx=(0, 4))
        ToolTip(btn_setup, "Python sanal ortamı, backend paketleri\nve frontend bağımlılıklarını yükler.\nİlk kullanımda zorunludur.", title="⚙  Kurulum")

        btn_help = self._btn(quick, "Yard\u0131m", self._show_help, bg="#475569")
        btn_help.pack(side="right", padx=(4, 0))
        ToolTip(btn_help, "Adım adım kurulum rehberi, Telegram\nbot oluşturma, Gmail/Outlook bağlama\nve sorun giderme bilgileri.", title="❓  Yardım")

        btn_save = self._btn(quick, "Kaydet", self.save_env, bg="#7c3aed")
        btn_save.pack(side="right")
        ToolTip(btn_save, "Ekrandaki tüm ayarları .env dosyasına\nkaydeder. Tokenlar şifreli saklanır.", title="💾  Kaydet")

        # ═══ DURUM (Loglar en üste taşındı) ═══
        status_frame = tk.Frame(sf, bg=BG)
        status_frame.pack(fill="x", padx=14, pady=(6, 10))
        tk.Label(status_frame, textvariable=self.status_var, fg="#93c5fd", bg=CARD_BG,
                 font=("Consolas", 9), anchor="w", padx=10, pady=8).pack(fill="x")
        self._update_connection_badges()

        # === KULLANICI PROFILI ===
        prof = _collapsible(sf, "Kullan\u0131c\u0131 Profili", expanded=True)
        _field(prof, 0, "Ad\u0131n\u0131z", self.owner_name_var)
        _field(prof, 1, "\u0130lgi Alanlar\u0131", self.owner_profile_var)

        # === YAPAY ZEKA MODELI ===
        llm = _collapsible(sf, "Yapay Zek\u00e2 Modeli", expanded=True)
        tk.Label(llm, text="Motor", fg=LABEL_FG, bg=CARD_BG,
                 font=("Segoe UI", 9), anchor="w").grid(row=0, column=0, sticky="w", **pad)
        tk.OptionMenu(llm, self.backend_var, "ollama", "llama_cpp").grid(row=0, column=1, sticky="w", **pad)
        _field(llm, 1, "Model Ad\u0131", self.model_var)
        _field(llm, 2, "GGUF Yolu", self.gguf_var)
        _field(llm, 3, "GGUF URL", self.gguf_url_var)

        llm_btns = tk.Frame(llm, bg=CARD_BG)
        llm_btns.grid(row=8, column=0, columnspan=2, sticky="w", padx=6, pady=4)
        self._btn(llm_btns, "Model \u00c7ek", self.pull_ollama_model, bg="#2563eb").pack(side="left", padx=(0, 4))
        self._btn(llm_btns, "GGUF \u0130ndir", self.download_gguf, bg="#2563eb").pack(side="left", padx=(0, 4))
        self._btn(llm_btns, "Qwen3.5", self.install_qwen35, bg="#2563eb").pack(side="left", padx=(0, 4))
        self._btn(llm_btns, "Eski Sil", self.remove_old_model, bg="#7c3aed").pack(side="left")

        # === TELEGRAM ===
        tg = _collapsible(sf, "Telegram Botu", expanded=True)
        _field(tg, 0, "Bot Token", self.token_var, show="*")
        _field(tg, 1, "Kullan\u0131c\u0131 ID", self.user_id_var)

        # === WEB GUVENLIGI ===
        sec = _collapsible(sf, "Web G\u00fcvenli\u011fi", expanded=True)
        _field(sec, 0, "\u0130zin Verilen Domainler", self.web_domains_var, hint="Bo\u015f: T\u00fcm internet serbest. K\u0131s\u0131tlamak i\u00e7in: github.com, python.org (https:// eklemeyin)")
        cb_internet = tk.Checkbutton(
            sec,
            text="\u0130nternete Ba\u011flan (\u0130\u015faretli de\u011filse ajan tamamen \u00c7evrimd\u0131\u015f\u0131 / \u0130nternetsiz \u00e7al\u0131\u015f\u0131r)",
            variable=self.web_allow_internet_var,
            fg=TEXT_FG, bg=CARD_BG, selectcolor=BG,
            activebackground=CARD_BG, activeforeground=TEXT_FG,
            font=("Segoe UI", 9, "bold"),
        )
        cb_internet.grid(row=2, column=0, columnspan=2, sticky="w", **pad)
        ToolTip(cb_internet, "İşaretli: Ajan web'e erişebilir (arama, sayfa okuma vb.)\nİşaretsiz: Tüm ağ erişimi engellenir, tamamen offline.", title="🌐  İnternet Erişimi")

        cb_private = tk.Checkbutton(
            sec,
            text="Yerel A\u011f / Modem Korumas\u0131 (Ajan\u0131n 192.168.x.x gibi yerel cihazlara eri\u015fmesini engeller)",
            variable=self.web_block_private_var,
            fg=TEXT_FG, bg=CARD_BG, selectcolor=BG,
            activebackground=CARD_BG, activeforeground=TEXT_FG,
            font=("Segoe UI", 9),
        )
        cb_private.grid(row=3, column=0, columnspan=2, sticky="w", **pad)
        ToolTip(cb_private, "İşaretli: 192.168.x.x, 10.x.x.x gibi yerel\nadresler engellenir (modem, NAS, yazıcı vb.)\nİşaretsiz: Yerel ağ tamamen serbest.", title="🛡  Yerel Ağ Koruması")

        cb_shell = tk.Checkbutton(
            sec,
            text="Shell/Terminal Komut Arac\u0131 (\u0130\u015faretli de\u011filse ajan powershell/cmd \u00e7al\u0131\u015ft\u0131ramaz)",
            variable=self.enable_shell_var,
            fg=TEXT_FG, bg=CARD_BG, selectcolor=BG,
            activebackground=CARD_BG, activeforeground=TEXT_FG,
            font=("Segoe UI", 9),
        )
        cb_shell.grid(row=4, column=0, columnspan=2, sticky="w", **pad)
        ToolTip(cb_shell, "İşaretli: Ajan PowerShell/CMD komutları\nçalıştırabilir (dosya, program vb.)\nİşaretsiz: Sisteme doğrudan erişemez.", title="🖥  Shell Erişimi")

        # === OCR / TESSERACT ===
        ocr = _collapsible(sf, "OCR / Tesseract", expanded=False)
        _field(
            ocr,
            0,
            "Tesseract Yolu",
            self.tesseract_cmd_var,
            hint="Örnek: C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
        )
        ocr_btns = tk.Frame(ocr, bg=CARD_BG)
        ocr_btns.grid(row=2, column=0, columnspan=2, sticky="w", padx=6, pady=4)
        self._btn(ocr_btns, "Varsayılan Doldur", self._fill_default_tesseract_path, bg="#2563eb").pack(side="left", padx=(0, 4))
        self._btn(ocr_btns, "Doğrula", self._validate_tesseract_path, bg="#475569").pack(side="left", padx=(0, 4))
        self._btn(ocr_btns, "Kaydet", self._save_tesseract_settings, bg="#7c3aed").pack(side="left")

        # === GMAIL ===
        gm = _collapsible(sf, "Gmail Entegrasyonu  (\u0130ste\u011fe Ba\u011fl\u0131)", expanded=False)
        _field(gm, 0, "Client ID", self.gmail_client_id_var, hint="xxx.apps.googleusercontent.com")
        _field(gm, 1, "Client Secret", self.gmail_client_secret_var, show="*")
        _field(gm, 2, "Access Token", self.gmail_token_var, show="*")
        _field(gm, 3, "Refresh Token", self.gmail_refresh_var, show="*")
        gm_btns = tk.Frame(gm, bg=CARD_BG)
        gm_btns.grid(row=8, column=0, columnspan=2, sticky="w", padx=6, pady=4)
        self._btn(gm_btns, "OAuth Ba\u011flan", self.connect_gmail_oauth, bg="#2563eb").pack(side="left", padx=(0, 4))
        self._btn(gm_btns, "Client ID Nereden?", self.open_google_console_help, bg="#475569").pack(side="left")
        self.gmail_conn_label = tk.Label(gm, textvariable=self.gmail_conn_var, fg="#f59e0b", bg=CARD_BG, font=("Segoe UI", 9, "bold"))
        self.gmail_conn_label.grid(row=9, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 4))

        # === OUTLOOK ===
        ol = _collapsible(sf, "Outlook Entegrasyonu  (\u0130ste\u011fe Ba\u011fl\u0131)", expanded=False)
        _field(ol, 0, "Client ID", self.outlook_client_id_var, hint="Application (client) ID GUID")
        _field(ol, 1, "Tenant ID", self.outlook_tenant_var, hint="common|organizations|consumers|tenant GUID")
        _field(ol, 2, "Access Token", self.outlook_token_var, show="*")
        _field(ol, 3, "Refresh Token", self.outlook_refresh_var, show="*")
        ol_btns = tk.Frame(ol, bg=CARD_BG)
        ol_btns.grid(row=8, column=0, columnspan=2, sticky="w", padx=6, pady=4)
        self._btn(ol_btns, "OAuth Ba\u011flan", self.connect_outlook_oauth, bg="#2563eb").pack(side="left", padx=(0, 4))
        self._btn(ol_btns, "Client ID Nereden?", self.open_azure_help, bg="#475569").pack(side="left")
        self.outlook_conn_label = tk.Label(ol, textvariable=self.outlook_conn_var, fg="#f59e0b", bg=CARD_BG, font=("Segoe UI", 9, "bold"))
        self.outlook_conn_label.grid(row=9, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 4))

        # === FOOTER ===
        footer = tk.Frame(self.root, bg="#0f172a")
        footer.pack(fill="x", side="bottom")
        tk.Label(
            footer,
            text=f"OpenWorld v{APP_VERSION}  |  Geliştirici: Ahmet Demiroğlu  |  ahmetdemiroglu89@gmail.com",
            fg="#64748b", bg="#0f172a", font=("Segoe UI", 8), anchor="center",
        ).pack(pady=4)

    def _btn(self, parent: tk.Widget, text: str, command, bg: str = "#2563eb") -> tk.Button:
        return tk.Button(parent, text=text, command=command, bg=bg, fg="white", bd=0, padx=10, pady=6,
                         font=("Segoe UI", 9), cursor="hand2", activebackground=bg, activeforeground="white")

    def _show_help(self) -> None:
        """Kurulum Rehberi popup penceresi."""
        win = tk.Toplevel(self.root)
        win.title("OpenWorld - Kurulum Rehberi")
        win.configure(bg="#1e293b")
        win.geometry("560x720")
        win.resizable(False, True)
        win.transient(self.root)
        win.grab_set()
        # Center
        win.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 560) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 720) // 2
        win.geometry(f"+{x}+{y}")
        txt = tk.Text(
            win, bg="#0f172a", fg="#e2e8f0", font=("Consolas", 10),
            wrap="word", relief="flat", padx=16, pady=16,
            insertbackground="#e2e8f0",
        )
        txt.pack(fill="both", expand=True, padx=8, pady=8)
        txt.insert("1.0", SETUP_GUIDE.strip())
        txt.configure(state="disabled")
        tk.Button(
            win, text="Kapat", command=win.destroy,
            bg="#3b82f6", fg="white", bd=0, padx=20, pady=8,
            font=("Segoe UI", 10, "bold"), cursor="hand2",
        ).pack(pady=(0, 12))

    def _dismiss_banner(self) -> None:
        """Ilk karsilama bandini gizle."""
        if hasattr(self, "_banner_frame"):
            self._banner_frame.pack_forget()



    def _append_status(self, text: str) -> None:
        def _set() -> None:
            self.status_var.set(f"{time.strftime('%H:%M:%S')} - {text}")

        self.root.after(0, _set)

    def _update_connection_badges(self) -> None:
        gmail_connected = bool(self.gmail_token_var.get().strip() or self.gmail_refresh_var.get().strip())
        outlook_connected = bool(self.outlook_token_var.get().strip() or self.outlook_refresh_var.get().strip())

        self.gmail_conn_var.set("Durum: Bağlı" if gmail_connected else "Durum: Bağlı değil")
        self.outlook_conn_var.set("Durum: Bağlı" if outlook_connected else "Durum: Bağlı değil")

        if hasattr(self, "gmail_conn_label"):
            self.gmail_conn_label.configure(fg="#22c55e" if gmail_connected else "#f59e0b")
        if hasattr(self, "outlook_conn_label"):
            self.outlook_conn_label.configure(fg="#22c55e" if outlook_connected else "#f59e0b")

    def _run_bg(self, fn) -> None:
        threading.Thread(target=fn, daemon=True).start()

    def _build_runtime_env(self) -> dict[str, str]:
        env = os.environ.copy()
        data_root = (ROOT / "data").resolve()
        sessions_root = (data_root / "sessions").resolve()
        env["WORKSPACE_ROOT"] = str(data_root)
        env["SESSIONS_DIR"] = str(sessions_root)
        env["DATA_DIR"] = str(data_root)
        env["TESSERACT_CMD"] = self.tesseract_cmd_var.get().strip()
        # Unicode path/icerik bozulmalarini azalt.
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    @staticmethod
    def _normalize_path_token(path_value: str) -> str:
        clean = (path_value or "").strip().strip('"').strip("'")
        if not clean:
            return ""
        try:
            return os.path.normcase(os.path.normpath(clean))
        except Exception:
            return clean.lower()

    def _resolve_tesseract_cmd(self) -> tuple[Path | None, str]:
        raw = os.path.expandvars((self.tesseract_cmd_var.get() or "").strip().strip('"').strip("'"))
        if not raw:
            return None, "Geçersiz yol: Tesseract yolu boş."

        candidate = Path(raw).expanduser()
        if candidate.is_dir():
            exe_path = (candidate / "tesseract.exe").resolve()
        else:
            exe_path = candidate.resolve()

        if exe_path.exists() and exe_path.is_file():
            if exe_path.name.lower() != "tesseract.exe":
                return None, f"Geçersiz yol: {exe_path} bir tesseract.exe dosyası değil."
            return exe_path, ""

        if candidate.is_dir():
            return None, f"Geçersiz yol: {candidate} klasörü içinde tesseract.exe bulunamadı."
        return None, f"Geçersiz yol: {candidate} bulunamadı."

    def _update_user_path_for_tesseract(self, tesseract_exe: Path) -> str:
        tesseract_dir = str(tesseract_exe.parent)
        if os.name != "nt" or winreg is None:
            return "Bilgi: PATH güncellemesi sadece Windows kullanıcı PATH'i için destekleniyor."

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ) as key:
                current_path, value_type = winreg.QueryValueEx(key, "Path")
        except (FileNotFoundError, OSError):
            current_path = ""
            value_type = winreg.REG_EXPAND_SZ

        existing_parts = [p.strip() for p in str(current_path).split(";") if p.strip()]
        existing_norm = {self._normalize_path_token(p) for p in existing_parts}
        target_norm = self._normalize_path_token(tesseract_dir)

        process_path = os.environ.get("PATH", "")
        process_parts = [p.strip() for p in process_path.split(";") if p.strip()]
        process_norm = {self._normalize_path_token(p) for p in process_parts}

        if target_norm in existing_norm:
            if target_norm not in process_norm:
                os.environ["PATH"] = f"{process_path};{tesseract_dir}" if process_path else tesseract_dir
            return f"Tesseract PATH zaten mevcut: {tesseract_dir}"

        updated_parts = existing_parts + [tesseract_dir]
        updated_path = ";".join(updated_parts)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            winreg.SetValueEx(key, "Path", 0, value_type, updated_path)

        if target_norm not in process_norm:
            os.environ["PATH"] = f"{process_path};{tesseract_dir}" if process_path else tesseract_dir

        try:
            HWND_BROADCAST = 0xFFFF
            WM_SETTINGCHANGE = 0x001A
            SMTO_ABORTIFHUNG = 0x0002
            ctypes.windll.user32.SendMessageTimeoutW(
                HWND_BROADCAST,
                WM_SETTINGCHANGE,
                0,
                "Environment",
                SMTO_ABORTIFHUNG,
                1000,
                None,
            )
        except Exception:
            pass

        return f"Tesseract PATH eklendi: {tesseract_dir}"

    def _fill_default_tesseract_path(self) -> None:
        self.tesseract_cmd_var.set(DEFAULT_TESSERACT_CMD)
        self._append_status(f"Tesseract yolu varsayılana alındı: {DEFAULT_TESSERACT_CMD}")

    def _validate_tesseract_path(self) -> None:
        exe_path, err = self._resolve_tesseract_cmd()
        if exe_path is None:
            self._append_status(err)
            messagebox.showerror("Tesseract Doğrulama", err)
            return
        self._append_status(f"Tesseract yolu doğrulandı: {exe_path}")
        messagebox.showinfo("Tesseract Doğrulama", f"Doğrulandı:\n{exe_path}")

    def _save_tesseract_settings(self) -> None:
        self.save_env()
        exe_path, err = self._resolve_tesseract_cmd()
        if exe_path is None:
            messagebox.showerror("OCR / Tesseract", err)
            return

        path_state = "Bilinmiyor"
        target_dir = str(exe_path.parent)
        try:
            if os.name == "nt" and winreg is not None:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ) as key:
                    user_path, _ = winreg.QueryValueEx(key, "Path")
                parts = [p.strip() for p in str(user_path).split(";") if p.strip()]
                normalized_parts = {self._normalize_path_token(p) for p in parts}
                if self._normalize_path_token(target_dir) in normalized_parts:
                    path_state = "Kullanıcı PATH'inde mevcut"
                else:
                    path_state = "Kullanıcı PATH'inde bulunamadı"
            else:
                path_state = "Windows registry okunamadı"
        except Exception:
            path_state = "Kullanıcı PATH doğrulanamadı"

        messagebox.showinfo(
            "OCR / Tesseract",
            "Tesseract ayarları kaydedildi.\n\n"
            f"TESSERACT_CMD:\n{exe_path}\n\n"
            f"PATH durumu: {path_state}",
        )

    def _check_python_env_health(self) -> tuple[bool, str]:
        py = VENV_PYTHON
        if not py.exists():
            return False, "Python sanal ortam bulunamadi."
        cfg = py.parent.parent / "pyvenv.cfg"
        if not cfg.exists():
            return False, "Python ortami bozuk (pyvenv.cfg eksik)."
        try:
            probe = subprocess.run(
                [str(py), "-c", "import sys; print(sys.executable)"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception as exc:
            return False, f"Python ortami dogrulanamadi: {exc}"
        if probe.returncode != 0:
            detail = (probe.stderr or probe.stdout or "").strip()
            if detail:
                detail = detail[:180]
            return False, f"Python ortami calismiyor: {detail or 'bilinmeyen hata'}"
        return True, ""

    def _kill_existing_openworld_processes(self) -> None:
        cmd = (
            "$procs = Get-CimInstance Win32_Process | Where-Object { "
            "$cl = ($_.CommandLine | Out-String); "
            "$isOpenWorldTool = ($cl -like '*app.main_v2:app*' -or $cl -like '*app.main:app*' -or $cl -like '*app.telegram_bridge*'); "
            "$isOurRuntime = ($cl -like '*OpenWorld*' -or $cl -like '*OpenWorldRuntime*'); "
            "$isOpenWorldTool -and $isOurRuntime }; "
            "foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True)

    def _load_env(self) -> None:
        if not ENV_PATH.exists():
            return
        env_map = {}
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env_map[k.strip()] = v.strip()

        enc = env_map.get("TELEGRAM_BOT_TOKEN_ENC", "")
        plain = env_map.get("TELEGRAM_BOT_TOKEN", "")
        token = plain
        if not token and enc:
            try:
                token = decrypt_text(enc)
            except Exception:
                token = ""

        gmail = env_map.get("GMAIL_ACCESS_TOKEN", "")
        gmail_enc = env_map.get("GMAIL_ACCESS_TOKEN_ENC", "")
        if not gmail and gmail_enc:
            try:
                gmail = decrypt_text(gmail_enc)
            except Exception:
                gmail = ""
        gmail_refresh = env_map.get("GMAIL_REFRESH_TOKEN", "")
        gmail_refresh_enc = env_map.get("GMAIL_REFRESH_TOKEN_ENC", "")
        if not gmail_refresh and gmail_refresh_enc:
            try:
                gmail_refresh = decrypt_text(gmail_refresh_enc)
            except Exception:
                gmail_refresh = ""
        gmail_client_secret = env_map.get("GMAIL_CLIENT_SECRET", "")
        gmail_client_secret_enc = env_map.get("GMAIL_CLIENT_SECRET_ENC", "")
        if not gmail_client_secret and gmail_client_secret_enc:
            try:
                gmail_client_secret = decrypt_text(gmail_client_secret_enc)
            except Exception:
                gmail_client_secret = ""

        outlook = env_map.get("OUTLOOK_ACCESS_TOKEN", "")
        outlook_enc = env_map.get("OUTLOOK_ACCESS_TOKEN_ENC", "")
        if not outlook and outlook_enc:
            try:
                outlook = decrypt_text(outlook_enc)
            except Exception:
                outlook = ""
        outlook_refresh = env_map.get("OUTLOOK_REFRESH_TOKEN", "")
        outlook_refresh_enc = env_map.get("OUTLOOK_REFRESH_TOKEN_ENC", "")
        if not outlook_refresh and outlook_refresh_enc:
            try:
                outlook_refresh = decrypt_text(outlook_refresh_enc)
            except Exception:
                outlook_refresh = ""

        self.token_var.set(token)
        self.user_id_var.set(env_map.get("TELEGRAM_ALLOWED_USER_ID", ""))
        self.gmail_token_var.set(gmail)
        self.gmail_refresh_var.set(gmail_refresh)
        self.gmail_client_id_var.set(env_map.get("GMAIL_CLIENT_ID", ""))
        self.gmail_client_secret_var.set(gmail_client_secret)
        self.outlook_token_var.set(outlook)
        self.outlook_refresh_var.set(outlook_refresh)
        self.outlook_client_id_var.set(env_map.get("OUTLOOK_CLIENT_ID", ""))
        self.outlook_tenant_var.set(env_map.get("OUTLOOK_TENANT_ID", "common"))
        self.backend_var.set(env_map.get("LLM_BACKEND", "ollama"))
        self.model_var.set(env_map.get("OLLAMA_MODEL", "qwen3.5:9b-q4_K_M"))
        self.gguf_var.set(env_map.get("LLAMA_MODEL_PATH", "../models/Qwen3.5-9B-Q4_K_M.gguf"))
        self.tesseract_cmd_var.set(env_map.get("TESSERACT_CMD", DEFAULT_TESSERACT_CMD))
        self.web_domains_var.set(env_map.get("WEB_ALLOWED_DOMAINS", ""))
        self.web_block_private_var.set(env_map.get("WEB_BLOCK_PRIVATE_HOSTS", "true").strip().lower() == "true")
        self.web_allow_internet_var.set(env_map.get("WEB_ALLOW_INTERNET", "true").strip().lower() == "true")
        self.enable_shell_var.set(env_map.get("ENABLE_SHELL_TOOL", "true").strip().lower() == "true")
        self.owner_name_var.set(env_map.get("OWNER_NAME", "Ahmet"))
        self.owner_profile_var.set(env_map.get("OWNER_PROFILE", "Teknoloji, otomasyon, urun gelistirme"))
        self._update_connection_badges()

    def save_env(self) -> None:
        if not ENV_PATH.exists():
            messagebox.showerror("Hata", "backend/.env bulunamad\u0131")
            return

        token = self.token_var.get().strip()
        token_enc = encrypt_text(token) if token else ""
        gmail_token = self.gmail_token_var.get().strip()
        gmail_token_enc = encrypt_text(gmail_token) if gmail_token else ""
        gmail_refresh = self.gmail_refresh_var.get().strip()
        gmail_refresh_enc = encrypt_text(gmail_refresh) if gmail_refresh else ""
        gmail_client_secret = self.gmail_client_secret_var.get().strip()
        gmail_client_secret_enc = encrypt_text(gmail_client_secret) if gmail_client_secret else ""
        outlook_token = self.outlook_token_var.get().strip()
        outlook_token_enc = encrypt_text(outlook_token) if outlook_token else ""
        outlook_refresh = self.outlook_refresh_var.get().strip()
        outlook_refresh_enc = encrypt_text(outlook_refresh) if outlook_refresh else ""

        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
        out = []
        seen = set()
        kv = {
            "TELEGRAM_BOT_TOKEN": "",
            "TELEGRAM_BOT_TOKEN_ENC": token_enc,
            "TELEGRAM_ALLOWED_USER_ID": self.user_id_var.get().strip(),
            "GMAIL_ACCESS_TOKEN": "",
            "GMAIL_ACCESS_TOKEN_ENC": gmail_token_enc,
            "GMAIL_REFRESH_TOKEN": "",
            "GMAIL_REFRESH_TOKEN_ENC": gmail_refresh_enc,
            "GMAIL_CLIENT_ID": self.gmail_client_id_var.get().strip(),
            "GMAIL_CLIENT_SECRET": "",
            "GMAIL_CLIENT_SECRET_ENC": gmail_client_secret_enc,
            "OUTLOOK_ACCESS_TOKEN": "",
            "OUTLOOK_ACCESS_TOKEN_ENC": outlook_token_enc,
            "OUTLOOK_REFRESH_TOKEN": "",
            "OUTLOOK_REFRESH_TOKEN_ENC": outlook_refresh_enc,
            "OUTLOOK_CLIENT_ID": self.outlook_client_id_var.get().strip(),
            "OUTLOOK_TENANT_ID": self.outlook_tenant_var.get().strip() or "common",
            "LLM_BACKEND": self.backend_var.get().strip() or "ollama",
            "OLLAMA_MODEL": self.model_var.get().strip() or "qwen3.5:9b-q4_K_M",
            "LLAMA_MODEL_PATH": self.gguf_var.get().strip() or "../models/Qwen3.5-9B-Q4_K_M.gguf",
            "TESSERACT_CMD": self.tesseract_cmd_var.get().strip() or DEFAULT_TESSERACT_CMD,
            "WEB_ALLOWED_DOMAINS": self.web_domains_var.get().strip(),
            "WEB_BLOCK_PRIVATE_HOSTS": "true" if self.web_block_private_var.get() else "false",
            "WEB_ALLOW_INTERNET": "true" if self.web_allow_internet_var.get() else "false",
            "ENABLE_SHELL_TOOL": "true" if self.enable_shell_var.get() else "false",
            "OWNER_NAME": self.owner_name_var.get().strip() or "Ahmet",
            "OWNER_PROFILE": self.owner_profile_var.get().strip() or "Teknoloji, otomasyon, urun gelistirme",
        }

        for line in lines:
            if "=" in line and not line.strip().startswith("#"):
                key = line.split("=", 1)[0].strip()
                if key in kv:
                    out.append(f"{key}={kv[key]}")
                    seen.add(key)
                else:
                    out.append(line)
            else:
                out.append(line)

        for k, v in kv.items():
            if k not in seen:
                out.append(f"{k}={v}")

        ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")
        self._update_connection_badges()
        tesseract_exe, tesseract_error = self._resolve_tesseract_cmd()
        if tesseract_exe is None:
            self._append_status(tesseract_error)
        else:
            try:
                path_status = self._update_user_path_for_tesseract(tesseract_exe)
                self._append_status(path_status)
            except Exception as exc:
                self._append_status(f"Tesseract PATH güncellenemedi: {exc}")
        self._append_status("Ayarlar kaydedildi. Token \u015fifreli sakland\u0131.")

    def _validate_gmail_inputs(self, client_id: str) -> str:
        if not client_id:
            return "Gmail OAuth için Client ID gerekli."
        if not _looks_like_google_client_id(client_id):
            return "Gmail Client ID formatı hatalı. `...apps.googleusercontent.com` olmalı."
        return ""

    def _validate_outlook_inputs(self, client_id: str, tenant: str) -> str:
        if not client_id:
            return "Outlook OAuth için Client ID gerekli."
        if not _looks_like_guid(client_id):
            return "Outlook Client ID, Azure'daki `Application (client) ID` GUID değeri olmalı (kullanıcı adı değil)."
        if "@" in tenant:
            return "Tenant ID alanına e-posta/kullanıcı adı yazmayın. `common` veya tenant GUID/domain kullanın."
        return ""

    def _friendly_google_error(self, message: str) -> str:
        m = (message or "").lower()
        if "invalid_client" in m or "missing a project id" in m:
            return "Google Client ID hatalı. Google Cloud'daki OAuth Client ID değerini aynen girin."
        if "client_secret is missing" in m:
            return "Bu OAuth istemcisi Client Secret istiyor. `Client Secret` alanını doldurun veya Google'da `Desktop app` türünde yeni client oluşturun."
        if "redirect_uri_mismatch" in m:
            return "Redirect URI uyumsuz. OAuth akışını launcher içinden başlatın ve aynı Client ID kullanın."
        return message

    def _friendly_outlook_error(self, message: str) -> str:
        m = (message or "").lower()
        if "aadsts700016" in m or "application with identifier" in m:
            return "Outlook Client ID/Tenant hatalı. Application (client) ID GUID değerini girin, tenant olarak `common` deneyin."
        if "aadsts50020" in m or "tenant" in m and "not found" in m:
            return "Tenant uyumsuz. `common` veya uygulamanızın tenant id/domain değerini kullanın."
        return message

    def open_google_console_help(self) -> None:
        webbrowser.open("https://console.cloud.google.com/apis/credentials")
        self._append_status("Google Console açıldı. OAuth Client ID oluşturup `...apps.googleusercontent.com` değerini kopyalayın.")

    def open_azure_help(self) -> None:
        webbrowser.open("https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade")
        self._append_status("Azure App registrations açıldı. `Application (client) ID` GUID değerini kopyalayın.")

    def connect_gmail_oauth(self) -> None:
        def _job() -> None:
            client_id = self.gmail_client_id_var.get().strip()
            err = self._validate_gmail_inputs(client_id)
            if err:
                self._append_status(err)
                return
            self._append_status("Gmail OAuth başladı. Tarayıcıda izin verin.")
            try:
                code_verifier, code_challenge = _pkce_pair()
                state = secrets.token_urlsafe(24)
                params = {
                    "client_id": client_id,
                    "redirect_uri": "__REDIRECT_URI__",
                    "response_type": "code",
                    "scope": "https://www.googleapis.com/auth/gmail.readonly",
                    "state": state,
                    "access_type": "offline",
                    "prompt": "consent",
                    "code_challenge": code_challenge,
                    "code_challenge_method": "S256",
                }
                auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
                code, redirect_uri = _run_loopback_oauth(auth_url=auth_url, expected_state=state, timeout_sec=240)
                token_payload = {
                    "code": code,
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": code_verifier,
                }
                client_secret = self.gmail_client_secret_var.get().strip()
                if client_secret:
                    token_payload["client_secret"] = client_secret
                token_data = _post_form("https://oauth2.googleapis.com/token", token_payload)
                access_token = token_data.get("access_token", "")
                refresh_token = token_data.get("refresh_token", "")
                if not access_token:
                    raise RuntimeError("Google token endpoint access_token dönmedi.")
                def _apply_tokens() -> None:
                    self.gmail_token_var.set(access_token)
                    if refresh_token:
                        self.gmail_refresh_var.set(refresh_token)
                    self.save_env()
                    self._append_status("Gmail OAuth tamamlandı ve tokenlar kaydedildi.")

                self.root.after(0, _apply_tokens)
            except Exception as exc:  # noqa: BLE001
                self._append_status(f"Gmail OAuth hatası: {self._friendly_google_error(str(exc))}")

        self._run_bg(_job)

    def connect_outlook_oauth(self) -> None:
        def _job() -> None:
            client_id = self.outlook_client_id_var.get().strip()
            tenant = self.outlook_tenant_var.get().strip() or "common"
            err = self._validate_outlook_inputs(client_id, tenant)
            if err:
                self._append_status(err)
                return
            self._append_status("Outlook OAuth başladı. Tarayıcıda izin verin.")
            try:
                code_verifier, code_challenge = _pkce_pair()
                state = secrets.token_urlsafe(24)
                scope = "offline_access https://graph.microsoft.com/Mail.Read"
                params = {
                    "client_id": client_id,
                    "redirect_uri": "__REDIRECT_URI__",
                    "response_type": "code",
                    "response_mode": "query",
                    "scope": scope,
                    "state": state,
                    "code_challenge": code_challenge,
                    "code_challenge_method": "S256",
                }
                auth_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?" + urllib.parse.urlencode(params)
                code, redirect_uri = _run_loopback_oauth(
                    auth_url=auth_url,
                    expected_state=state,
                    timeout_sec=240,
                    redirect_host="localhost",
                    redirect_path="/",
                )
                token_payload = {
                    "client_id": client_id,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": code_verifier,
                    "scope": scope,
                }
                token_data = _post_form(
                    f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
                    token_payload,
                )
                access_token = token_data.get("access_token", "")
                refresh_token = token_data.get("refresh_token", "")
                if not access_token:
                    raise RuntimeError("Microsoft token endpoint access_token dönmedi.")
                def _apply_tokens() -> None:
                    self.outlook_token_var.set(access_token)
                    if refresh_token:
                        self.outlook_refresh_var.set(refresh_token)
                    self.save_env()
                    self._append_status("Outlook OAuth tamamlandı ve tokenlar kaydedildi.")

                self.root.after(0, _apply_tokens)
            except Exception as exc:  # noqa: BLE001
                self._append_status(f"Outlook OAuth hatası: {self._friendly_outlook_error(str(exc))}")

        self._run_bg(_job)

    def _refresh_gmail_access_token(self) -> str:
        client_id = self.gmail_client_id_var.get().strip()
        refresh_token = self.gmail_refresh_var.get().strip()
        if self._validate_gmail_inputs(client_id) or not refresh_token:
            return ""
        payload = {
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        client_secret = self.gmail_client_secret_var.get().strip()
        if client_secret:
            payload["client_secret"] = client_secret
        token_data = _post_form("https://oauth2.googleapis.com/token", payload)
        return token_data.get("access_token", "")

    def _refresh_outlook_access_token(self) -> str:
        client_id = self.outlook_client_id_var.get().strip()
        refresh_token = self.outlook_refresh_var.get().strip()
        tenant = self.outlook_tenant_var.get().strip() or "common"
        if self._validate_outlook_inputs(client_id, tenant) or not refresh_token:
            return ""
        payload = {
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": "offline_access https://graph.microsoft.com/Mail.Read",
        }
        token_data = _post_form(f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token", payload)
        return token_data.get("access_token", "")

    def setup_all(self) -> None:
        def _job() -> None:
            self._append_status("Kurulum ba\u015fl\u0131yor...")
            ps = ROOT / "scripts" / "setup.ps1"
            proc = subprocess.Popen(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ps)],
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    self._append_status(line)
            proc.wait()
            if proc.returncode == 0:
                self._append_status("\u2705 Kurulum ba\u015far\u0131yla tamamland\u0131!")
            else:
                self._append_status(f"\u274c Kurulum hatas\u0131 (kod: {proc.returncode})")

        self._run_bg(_job)

    def pull_ollama_model(self) -> None:
        def _job() -> None:
            model = self.model_var.get().strip()
            if not model:
                self._append_status("Model adı boş olamaz.")
                return
            self._append_status(f"Ollama modeli indiriliyor: {model}")
            proc = subprocess.Popen(
                ["ollama", "pull", model],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    self._append_status(line)
            proc.wait()
            if proc.returncode == 0:
                self._append_status("✅ Model başarıyla indirildi.")
            else:
                self._append_status("❌ Model indirilemedi.")

        self._run_bg(_job)

    def download_gguf(self) -> None:
        def _job() -> None:
            ok, reason = self._check_python_env_health()
            if not ok:
                self._append_status(f"\u00d6nce Kurulum \u00e7al\u0131\u015ft\u0131r\u0131n. ({reason})")
                return
            url = self.gguf_url_var.get().strip()
            path = Path(self.gguf_var.get().strip())
            if not url:
                self._append_status("GGUF URL bo\u015f olamaz.")
                return
            target = (ROOT / path).resolve() if not path.is_absolute() else path
            target.parent.mkdir(parents=True, exist_ok=True)
            self._append_status(f"GGUF indiriliyor: {target.name}")
            script = f"""
import httpx
from pathlib import Path
import sys

url = {url!r}
out = Path(r"{str(target)}")

try:
    with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
        response.raise_for_status()
        total_size = int(response.headers.get("content-length", 0))
        downloaded_size = 0
        
        with out.open("wb") as file_obj:
            for chunk in response.iter_bytes(chunk_size=8192):
                if chunk:
                    file_obj.write(chunk)
                    downloaded_size += len(chunk)
                    if total_size > 0:
                        progress = (downloaded_size / total_size) * 100
                        sys.stdout.write(f"\\r{{progress:.1f}}% indirildi...")
                    else:
                        sys.stdout.write(f"\\r{{downloaded_size / (1024*1024):.1f}} MB indirildi...")
                    sys.stdout.flush()
    sys.stdout.write("\\n") # Newline after progress
    print("ok")
except Exception as e:
    print(f"error: {{e}}", file=sys.stderr)
    sys.exit(1)
"""
            proc = subprocess.Popen([str(VENV_PYTHON), "-c", script], cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
            
            output_lines = []
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    self._append_status(line)
                output_lines.append(line)
            proc.wait()

            if proc.returncode == 0:
                self._append_status("✅ GGUF indirildi.")
            else:
                error_msg = "GGUF indirme hatası."
                # Try to find a more specific error from the script's output
                for line in output_lines:
                    if line.startswith("error:"):
                        error_msg = f"GGUF indirme hatası: {line[6:].strip()}"
                        break
                self._append_status(f"❌ {error_msg}")

        self._run_bg(_job)

    def install_qwen35(self) -> None:
        def _job() -> None:
            self._append_status("Qwen3.5-9B GGUF kuruluyor...")
            proc = subprocess.Popen(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(QWEN_INSTALL_SCRIPT)],
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    self._append_status(line)
            proc.wait()
            if proc.returncode == 0:
                self.model_var.set("qwen3.5:9b-q4_K_M")
                self.backend_var.set("ollama")
                self.gguf_var.set("../models/Qwen3.5-9B-Q4_K_M.gguf")
                self.save_env()
                self._append_status("✅ Qwen3.5-9B kuruldu ve seçildi.")
            else:
                self._append_status("❌ Model kurulumu başarısız.")

        self._run_bg(_job)

    def remove_old_model(self) -> None:
        def _job() -> None:
            self._append_status("Eski model siliniyor: qwen2.5:7b-instruct")
            subprocess.run(["ollama", "rm", "qwen2.5:7b-instruct"], text=True, capture_output=True)
            self._append_status("Silme komutu tamamland\u0131.")

        self._run_bg(_job)

    def start_all(self) -> None:
        def _job() -> None:
            self.save_env()
            ok, reason = self._check_python_env_health()
            if not ok:
                self._append_status(f"HATA: {reason}")
                self._append_status("L\u00fctfen [Kurulum] butonuna t\u0131klay\u0131n")
                return

            LOG_DIR.mkdir(parents=True, exist_ok=True)
            self.stop_all(silent=True)
            self._kill_existing_openworld_processes()
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            runtime_env = self._build_runtime_env()

            self._append_status("Backend ba\u015flat\u0131l\u0131yor...")
            backend_out = open(LOG_DIR / "backend.out.log", "w", encoding="utf-8")
            backend_err = open(LOG_DIR / "backend.err.log", "w", encoding="utf-8")
            self.backend_proc = subprocess.Popen(
                [str(VENV_PYTHON), "-m", "uvicorn", "app.main_v2:app", "--host", "127.0.0.1", "--port", "8000"],
                cwd=str(BACKEND_DIR),
                env=runtime_env,
                stdout=backend_out,
                stderr=backend_err,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
                startupinfo=startupinfo,
            )
            backend_out.close()
            backend_err.close()
            telegram_out = open(LOG_DIR / "telegram.out.log", "a", encoding="utf-8")
            telegram_err = open(LOG_DIR / "telegram.err.log", "a", encoding="utf-8")
            self.telegram_proc = subprocess.Popen(
                [str(VENV_PYTHON), "-m", "app.telegram_bridge"],
                cwd=str(BACKEND_DIR),
                env=runtime_env,
                stdout=telegram_out,
                stderr=telegram_err,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
                startupinfo=startupinfo,
            )
            telegram_out.close()
            telegram_err.close()
            time.sleep(3)
            if self._is_port_open(8000):
                self._append_status("Servisler ba\u015flat\u0131ld\u0131. UI: http://127.0.0.1:8000")
            else:
                self._append_status("HATA: Backend ba\u015flat\u0131lamad\u0131!")
                # Log dosyas\u0131n\u0131 oku ve g\u00f6ster
                try:
                    err_log = LOG_DIR / "backend.err.log"
                    if err_log.exists():
                        log_content = err_log.read_text(encoding="utf-8", errors="ignore")
                        if log_content:
                            # Son 500 karakteri g\u00f6ster
                            last_error = log_content[-500:]
                            self._append_status("Son hata:")
                            for line in last_error.split("\n"):
                                if line.strip():
                                    self._append_status("  > " + line.strip()[:100])
                        else:
                            out_log = LOG_DIR / "backend.out.log"
                            out_content = ""
                            if out_log.exists():
                                out_content = out_log.read_text(encoding="utf-8", errors="ignore").strip()

                            rc = self.backend_proc.poll() if self.backend_proc else None
                            if out_content:
                                self._append_status("backend.err.log bos. backend.out.log son satirlari:")
                                for line in out_content[-500:].split("\n"):
                                    if line.strip():
                                        self._append_status("  > " + line.strip()[:100])
                            elif rc is None:
                                self._append_status(
                                    "Loglar henuz olusmamis olabilir. Backend gec aciliyor olabilir, "
                                    "biraz bekleyip tekrar deneyin."
                                )
                            else:
                                self._append_status(
                                    f"Backend erken sonlandi (cikis kodu: {rc}). "
                                    "Loglar bos; Python/venv yolunu kontrol edin."
                                )
                    else:
                        self._append_status("Log dosyas\u0131 bulunamad\u0131.")
                except Exception as e:
                    self._append_status(f"Log okuma hatas\u0131: {e}")

        self._run_bg(_job)

    def stop_all(self, silent: bool = False) -> None:
        for proc in [self.backend_proc, self.telegram_proc]:
            if proc and proc.poll() is None:
                proc.terminate()
        self._kill_existing_openworld_processes()
        self.backend_proc = None
        self.telegram_proc = None
        if not silent:
            self._append_status("Servisler durduruldu")

    def open_ui(self) -> None:
        webbrowser.open("http://127.0.0.1:8000")
        self._append_status("Aray\u00fcz a\u00e7\u0131ld\u0131")

    def _is_port_open(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            return s.connect_ex(("127.0.0.1", port)) == 0

    def _tick_status(self) -> None:
        backend = self._is_port_open(8000)
        ollama = self._is_port_open(11434)
        self.root.title(
            f"OpenWorld Launcher  \u2502  Ollama: {'\u2705 Aktif' if ollama else '\u274c Kapal\u0131'}  \u2502  Backend: {'\u2705 Aktif' if backend else '\u274c Kapal\u0131'}"
        )

        self.root.after(2000, self._tick_status)

    def _on_close(self) -> None:
        self.stop_all(silent=True)
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    os.chdir(ROOT)
    LauncherApp().run()


