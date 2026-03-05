"""
SUPER AGENT TOOLS
Gercek bir ajan icin gelismis yetenekler
"""
from __future__ import annotations

import base64
import io
import json
import os
import platform
import re
import subprocess
import tempfile
import time
import socket
import ipaddress
import unicodedata
import usb.core
import usb.util
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import cv2
import numpy as np
import pyautogui
import sounddevice as sd
import scipy.io.wavfile as wav
from PIL import Image, ImageGrab

from ..config import settings

_WORKSPACE_ROOT = settings.workspace_path.resolve()
_VIRTUAL_DESKTOP = (_WORKSPACE_ROOT / "desktop").resolve()
_USER_DESKTOP_RE = re.compile(r"^(?P<drive>[a-zA-Z]):\\users\\[^\\]+\\desktop(?:\\(?P<tail>.*))?$", re.IGNORECASE)
_PUBLIC_DESKTOP_RE = re.compile(r"^(?P<drive>[a-zA-Z]):\\users\\public\\desktop(?:\\(?P<tail>.*))?$", re.IGNORECASE)

_TR_TRANSLATION = str.maketrans({
    "ç": "c",
    "ğ": "g",
    "ı": "i",
    "ö": "o",
    "ş": "s",
    "ü": "u",
    "Ç": "c",
    "Ğ": "g",
    "İ": "i",
    "Ö": "o",
    "Ş": "s",
    "Ü": "u",
})

_DEFAULT_APPROVAL_CONTEXT_TERMS = {
    "permission", "permissions", "approve", "allow", "authorize", "access",
    "trust", "secure", "safety", "agent", "extension", "run", "execute",
    "onay", "izin", "guven", "yetki", "erisim", "calistir",
}

_DEFAULT_APPROVAL_BUTTON_TERMS = {
    "approve", "allow", "accept", "authorize", "grant", "continue", "yes", "ok",
    "onayla", "onay", "izinver", "kabulet", "kabul", "devam", "evet",
    "run", "proceed",
}

_DEFAULT_APPROVAL_BUTTON_TERMS_MULTI = {
    "allow access",
    "run anyway",
    "allow anyway",
    "yes continue",
    "izin ver",
    "kabul et",
    "devam et",
    "onay ver",
}


def _map_desktop_tail_to_workspace(tail: str) -> Optional[Path]:
    normalized = tail.replace("/", "\\").lstrip("\\/")
    if not normalized:
        return None
    lowered = normalized.lower()
    if lowered.startswith("data\\"):
        return (_WORKSPACE_ROOT / normalized[len("data\\"):]).resolve()
    project_prefix = f"{_WORKSPACE_ROOT.parent.name.lower()}\\data\\"
    if lowered.startswith(project_prefix):
        return (_WORKSPACE_ROOT / normalized[len(project_prefix):]).resolve()
    return None


def _resolve_generated_output_path(output_path: str, default_filename: str, category: str = "media") -> Path:
    raw = (output_path or "").strip().strip('"').strip("'")
    if not raw:
        return (_WORKSPACE_ROOT / category / default_filename).resolve()

    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve()
        try:
            resolved.relative_to(_WORKSPACE_ROOT)
            return resolved
        except ValueError:
            normalized = raw.replace("/", "\\")
            for pattern in (_PUBLIC_DESKTOP_RE, _USER_DESKTOP_RE):
                match = pattern.match(normalized)
                if not match:
                    continue
                tail = (match.group("tail") or "").lstrip("\\/")
                mapped_workspace = _map_desktop_tail_to_workspace(tail)
                if mapped_workspace is not None:
                    return mapped_workspace
                if not tail:
                    return (_VIRTUAL_DESKTOP / default_filename).resolve()
                return (_VIRTUAL_DESKTOP / tail).resolve()
            return (_WORKSPACE_ROOT / category / resolved.name).resolve()

    lowered = raw.lower().replace("/", "\\")
    if lowered in {"desktop", "masaustu"}:
        return (_VIRTUAL_DESKTOP / default_filename).resolve()

    for prefix in ("desktop\\", "masaustu\\"):
        if lowered.startswith(prefix):
            tail = raw[len(prefix):].lstrip("\\/")
            if not tail:
                return (_VIRTUAL_DESKTOP / default_filename).resolve()
            return (_VIRTUAL_DESKTOP / tail).resolve()

    return (_WORKSPACE_ROOT / candidate).resolve()

def _host_resolves_to_private(hostname: str) -> bool:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return True
    for info in infos:
        ip = info[4][0]
        try:
            obj = ipaddress.ip_address(ip)
        except ValueError:
            return True
        if obj.is_private or obj.is_loopback or obj.is_link_local or obj.is_reserved or obj.is_multicast:
            return True
    return False


def _validate_web_url(url: str) -> None:
    if not settings.web_allow_internet:
        raise ValueError("Agent offline modda calisiyor. Internet istekleri engellendi.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http/https URLs are allowed.")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("Invalid URL host.")
    if settings.web_allowed_domains_list:
        allowed = settings.web_allowed_domains_list
        if not any(host == d or host.endswith("." + d) for d in allowed):
            raise ValueError("Host not in WEB_ALLOWED_DOMAINS policy.")
    if settings.web_block_private_hosts and _host_resolves_to_private(host):
        raise ValueError("Private/local network hosts are blocked.")


# =============================================================================
# SCREENSHOT ARACLARI
# =============================================================================

def tool_screenshot_desktop(output_path: str = "", region: List[int] = None) -> Dict[str, Any]:
    """Masaustu ekran goruntusu al."""
    try:
        if region and len(region) == 4:
            # Belirli bolge: [x, y, width, height]
            x, y, w, h = region
            screenshot = pyautogui.screenshot(region=(x, y, w, h))
        else:
            # Tam ekran
            screenshot = pyautogui.screenshot()
        
        # Kaydet
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"desktop_{timestamp}.png"
        target = _resolve_generated_output_path(output_path, default_name, "media")
        target.parent.mkdir(parents=True, exist_ok=True)
        screenshot.save(target)
        
        return {
            "path": str(target),
            "size": target.stat().st_size,
            "resolution": screenshot.size,
            "region": region or "full"
        }
    except Exception as e:
        return {"error": str(e)}


def tool_screenshot_webpage(url: str, output_path: str = "", wait_time: int = 3) -> Dict[str, Any]:
    """Web sayfasi ekran goruntusu al."""
    try:
        _validate_web_url(url)
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        
        # Chrome options
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Driver
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )
        
        try:
            driver.get(url)
            time.sleep(max(1, min(wait_time, 20)))  # Sayfanin yuklenmesini bekle
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            domain = url.replace("https://", "").replace("http://", "").replace("/", "_")[:30]
            default_name = f"web_{domain}_{timestamp}.png"
            target = _resolve_generated_output_path(output_path, default_name, "media")
            target.parent.mkdir(parents=True, exist_ok=True)
            
            driver.save_screenshot(str(target))
            
            return {
                "path": str(target),
                "url": url,
                "size": target.stat().st_size if target.exists() else 0
            }
        finally:
            driver.quit()
            
    except Exception as e:
        return {"error": str(e), "note": "Chrome kurulu oldugundan emin olun"}


def tool_find_image_on_screen(image_path: str, confidence: float = 0.9) -> Dict[str, Any]:
    """Ekranda bir goruntu ara ve konumunu bul."""
    try:
        target = Path(image_path)
        if not target.exists():
            return {"error": "Goruntu dosyasi bulunamadi", "path": image_path}
        
        location = pyautogui.locateOnScreen(str(target), confidence=confidence)
        
        if location:
            center = pyautogui.center(location)
            return {
                "found": True,
                "location": {"left": location.left, "top": location.top, 
                           "width": location.width, "height": location.height},
                "center": {"x": center.x, "y": center.y}
            }
        else:
            return {"found": False, "message": "Goruntu ekranda bulunamadi"}
            
    except Exception as e:
        return {"error": str(e)}


def tool_click_on_screen(x: int, y: int, clicks: int = 1, button: str = "left") -> Dict[str, Any]:
    """Ekranda belirli bir koordinata tikla."""
    try:
        pyautogui.click(x, y, clicks=clicks, button=button)
        return {"success": True, "x": x, "y": y, "clicks": clicks, "button": button}
    except Exception as e:
        return {"error": str(e)}


def tool_type_text(text: str, interval: float = 0.01) -> Dict[str, Any]:
    """Klavyeden metin yaz (Türkçe ve Unicode destekli)."""
    try:
        # ASCII-only text: typewrite (daha güvenilir, karakter karakter)
        if text.isascii():
            pyautogui.typewrite(text, interval=interval)
            return {"success": True, "typed": text, "length": len(text), "method": "typewrite"}

        # Non-ASCII (Türkçe, Unicode vs.): clipboard + paste
        import subprocess as _sp
        import platform
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

        import time
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.05)
        return {"success": True, "typed": text, "length": len(text), "method": "clipboard_paste"}
    except Exception as e:
        return {"error": str(e)}


def tool_press_key(key: str, presses: int = 1) -> Dict[str, Any]:
    """Klavye tusuna bas."""
    try:
        pyautogui.press(key, presses=presses)
        return {"success": True, "key": key, "presses": presses}
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# SES KAYIT ARACLARI
# =============================================================================

class AudioRecorder:
    """Ses kaydedici sinif."""
    def __init__(self):
        self.recording = False
        self.frames = []
        self.samplerate = 44100
        self.channels = 2
        
    def start_recording(self):
        self.recording = True
        self.frames = []
        
        def callback(indata, frames, time, status):
            if self.recording:
                self.frames.append(indata.copy())
        
        self.stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=self.channels,
            callback=callback
        )
        self.stream.start()
        
    def stop_recording(self):
        self.recording = False
        self.stream.stop()
        self.stream.close()
        
    def save(self, path: str):
        if not self.frames:
            return False
        
        audio_data = np.concatenate(self.frames, axis=0)
        wav.write(path, self.samplerate, audio_data)
        return True


# Global kaydedici
_audio_recorder = None


def tool_start_audio_recording() -> Dict[str, Any]:
    """Ses kaydina basla."""
    global _audio_recorder
    try:
        _audio_recorder = AudioRecorder()
        _audio_recorder.start_recording()
        return {"success": True, "message": "Ses kaydi basladi", "sample_rate": 44100}
    except Exception as e:
        return {"error": str(e)}


def tool_stop_audio_recording(output_path: str = "") -> Dict[str, Any]:
    """Ses kaydini durdur ve kaydet."""
    global _audio_recorder
    try:
        if not _audio_recorder:
            return {"error": "Aktif ses kaydi yok"}
        
        _audio_recorder.stop_recording()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"recording_{timestamp}.wav"
        target = _resolve_generated_output_path(output_path, default_name, "media")
        target.parent.mkdir(parents=True, exist_ok=True)
        
        if _audio_recorder.save(str(target)):
            return {
                "success": True,
                "path": str(target),
                "size": target.stat().st_size
            }
        else:
            return {"error": "Kayit bos veya kaydedilemedi"}
            
    except Exception as e:
        return {"error": str(e)}


def tool_play_audio(audio_path: str) -> Dict[str, Any]:
    """Ses dosyasini cal."""
    try:
        from scipy.io import wavfile
        import sounddevice as sd
        
        samplerate, data = wavfile.read(audio_path)
        sd.play(data, samplerate)
        sd.wait()
        
        return {"success": True, "played": audio_path}
    except Exception as e:
        return {"error": str(e)}


def tool_text_to_speech(text: str, output_path: str = "", lang: str = "tr") -> Dict[str, Any]:
    """Metni sese cevir."""
    try:
        # Windows TTS
        if platform.system() == "Windows":
            import win32com.client
            
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            
            if not output_path:
                # Dogrudan konus
                speaker.Speak(text)
                return {"success": True, "spoken": text, "mode": "direct"}
            else:
                # Dosyaya kaydet
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                default_name = f"tts_{timestamp}.wav"
                target = _resolve_generated_output_path(output_path, default_name, "media")
                target.parent.mkdir(parents=True, exist_ok=True)
                
                # WAV olarak kaydet
                stream = win32com.client.Dispatch("SAPI.SpFileStream")
                stream.Open(str(target), 3)  # 3 = SSFMCreateForWrite
                speaker.AudioOutputStream = stream
                speaker.Speak(text)
                stream.Close()
                
                return {
                    "success": True,
                    "path": str(target),
                    "text": text,
                    "size": target.stat().st_size if target.exists() else 0
                }
        else:
            return {"error": "TTS su anda sadece Windows'da destekleniyor"}
            
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# WEBCAM ARACLARI
# =============================================================================

def tool_webcam_capture(output_path: str = "", camera_index: int = 0) -> Dict[str, Any]:
    """Webcam'den fotograf cek."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"[WEBCAM] Opening camera {camera_index}")
        cap = cv2.VideoCapture(camera_index)
        
        if not cap.isOpened():
            logger.error(f"[WEBCAM] Camera {camera_index} could not be opened")
            return {"error": f"Kamera {camera_index} acilamadi. Kamera baska bir uygulama tarafindan kullaniliyor olabilir."}
        
        # Birkac kare bekle (oto focus)
        logger.info("[WEBCAM] Warming up camera...")
        for i in range(10):
            ret, _ = cap.read()
            if not ret:
                logger.warning(f"[WEBCAM] Warmup frame {i} failed")
        
        # Gercek kareyi yakala
        ret, frame = cap.read()
        cap.release()
        
        if not ret or frame is None or frame.size == 0:
            logger.error(f"[WEBCAM] Frame capture failed")
            return {"error": "Kare yakalanamadi. Kamera baska bir uygulama tarafindan kullaniliyor olabilir."}
        
        logger.info(f"[WEBCAM] Frame captured: shape={frame.shape}")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"capture_{timestamp}.jpg"
        target = _resolve_generated_output_path(output_path, default_name, "media")
        
        logger.info(f"[WEBCAM] Target: {target}")
        
        # Klasoru olustur
        target.parent.mkdir(parents=True, exist_ok=True)
        
        # BGR -> RGB cevir (PIL icin)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(frame_rgb)
        
        # PIL ile kaydet (cv2.imwrite yerine)
        try:
            image.save(str(target), "JPEG", quality=95)
            logger.info(f"[WEBCAM] PIL save success")
        except Exception as pil_err:
            logger.error(f"[WEBCAM] PIL save failed: {pil_err}")
            # PIL basarisiz olursa cv2 dene
            write_success = cv2.imwrite(str(target), frame)
            if not write_success:
                return {"error": f"Fotograf kaydedilemedi: {pil_err}"}
        
        # Dosya kontrol
        if not target.exists():
            return {"error": "Dosya olusturulamadi"}
        
        file_size = target.stat().st_size
        if file_size == 0:
            target.unlink()
            return {"error": "Fotograf bos (0 byte)"}
        
        logger.info(f"[WEBCAM] Success! {file_size} bytes")
        
        return {
            "success": True,
            "path": str(target),
            "size": file_size,
            "resolution": f"{frame.shape[1]}x{frame.shape[0]}"
        }
        
    except Exception as e:
        logger.exception("[WEBCAM] Exception")
        return {"error": f"Webcam hatasi: {str(e)}"}


def tool_webcam_record_video(duration: int = 10, output_path: str = "", camera_index: int = 0) -> Dict[str, Any]:
    """Webcam'den video kaydet."""
    try:
        cap = cv2.VideoCapture(camera_index)
        
        if not cap.isOpened():
            return {"error": f"Kamera {camera_index} acilamadi"}
        
        # Video ozellikleri
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = 20.0
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"video_{timestamp}.avi"
        target = _resolve_generated_output_path(output_path, default_name, "media")
        target.parent.mkdir(parents=True, exist_ok=True)
        
        # Video writer
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        out = cv2.VideoWriter(str(target), fourcc, fps, (width, height))
        
        start_time = time.time()
        frames = 0
        
        while time.time() - start_time < duration:
            ret, frame = cap.read()
            if ret:
                out.write(frame)
                frames += 1
        
        cap.release()
        out.release()
        
        return {
            "success": True,
            "path": str(target),
            "duration": duration,
            "frames": frames,
            "fps": fps,
            "size": target.stat().st_size
        }
        
    except Exception as e:
        return {"error": str(e)}


def tool_list_cameras() -> Dict[str, Any]:
    """Kullanilabilir kameralari listele."""
    try:
        cameras = []
        
        for i in range(10):  # Ilk 10 kamerayi dene
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cameras.append({
                    "index": i,
                    "resolution": f"{width}x{height}",
                    "available": True
                })
                cap.release()
        
        return {"cameras": cameras, "count": len(cameras)}
        
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# USB CIHAZ ARACLARI
# =============================================================================

def tool_list_usb_devices() -> Dict[str, Any]:
    """Bagli USB cihazlarini listele."""
    try:
        devices = []
        
        # pyusb ile listele
        for device in usb.core.find(find_all=True):
            try:
                devices.append({
                    "vendor_id": hex(device.idVendor) if device.idVendor else None,
                    "product_id": hex(device.idProduct) if device.idProduct else None,
                    "manufacturer": usb.util.get_string(device, device.iManufacturer) if device.iManufacturer else None,
                    "product": usb.util.get_string(device, device.iProduct) if device.iProduct else None,
                    "serial_number": usb.util.get_string(device, device.iSerialNumber) if device.iSerialNumber else None
                })
            except:
                # Bazi cihazlar string alanlarini desteklemez
                devices.append({
                    "vendor_id": hex(device.idVendor) if device.idVendor else None,
                    "product_id": hex(device.idProduct) if device.idProduct else None,
                    "manufacturer": None,
                    "product": None,
                    "serial_number": None
                })
        
        # Windows'ta ek bilgi
        if platform.system() == "Windows":
            try:
                import wmi
                c = wmi.WMI()
                wmi_devices = []
                for usb in c.Win32_USBHub():
                    wmi_devices.append({
                        "name": usb.Name,
                        "device_id": usb.DeviceID,
                        "status": usb.Status,
                        "pnp_device_id": usb.PNPDeviceID
                    })
                return {"usb_devices": devices, "wmi_usb_info": wmi_devices, "count": len(devices)}
            except:
                pass
        
        return {"usb_devices": devices, "count": len(devices)}
        
    except Exception as e:
        return {"error": str(e)}


def tool_eject_usb_drive(drive_letter: str) -> Dict[str, Any]:
    """USB surucusunu guvenli cikar."""
    try:
        if platform.system() == "Windows":
            # PowerShell ile cikar
            ps_command = f"(New-Object -comObject Shell.Application).Namespace(17).ParseName('{drive_letter}:').InvokeVerb('Eject')"
            result = subprocess.run(["powershell", "-Command", ps_command], 
                                  capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                return {"success": True, "drive": drive_letter, "message": "Surucu guvenli cikarildi"}
            else:
                return {"error": result.stderr or "Cikarma basarisiz"}
        else:
            return {"error": "Bu ozellik su anda sadece Windows'da destekleniyor"}
            
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# GELIÅMIÅ OTOMASYON
# =============================================================================

def tool_mouse_position() -> Dict[str, Any]:
    """Fare pozisyonunu al."""
    try:
        x, y = pyautogui.position()
        screen_size = pyautogui.size()
        return {
            "x": x,
            "y": y,
            "screen_width": screen_size.width,
            "screen_height": screen_size.height
        }
    except Exception as e:
        return {"error": str(e)}


def tool_mouse_move(x: int, y: int, duration: float = 0.5) -> Dict[str, Any]:
    """Fareyi hareket ettir."""
    try:
        pyautogui.moveTo(x, y, duration=duration)
        return {"success": True, "x": x, "y": y, "duration": duration}
    except Exception as e:
        return {"error": str(e)}


def tool_drag_to(x: int, y: int, duration: float = 0.5, button: str = "left") -> Dict[str, Any]:
    """Surukle-birak yap."""
    try:
        pyautogui.dragTo(x, y, duration=duration, button=button)
        return {"success": True, "to_x": x, "to_y": y}
    except Exception as e:
        return {"error": str(e)}


def tool_scroll(amount: int, x: int = None, y: int = None) -> Dict[str, Any]:
    """Fare tekerlegi kaydir."""
    try:
        if x is not None and y is not None:
            pyautogui.scroll(amount, x=x, y=y)
        else:
            pyautogui.scroll(amount)
        return {"success": True, "amount": amount}
    except Exception as e:
        return {"error": str(e)}


def tool_hotkey(*keys: str, keys_list: Optional[List[str]] = None) -> Dict[str, Any]:
    """Klavye kisayolu calistir.
    
    Args:
        *keys: Pozisyonel tuş argümanlari (ornegin: "ctrl", "c")
        keys_list: Alternatif olarak tuş listesi (ornegin: ["ctrl", "c"])
    """
    try:
        # Eger keys_list verilmisse onu kullan, yoksa *keys'i kullan
        key_sequence = keys_list if keys_list else list(keys)
        if not key_sequence:
            return {"error": "En az bir tuş belirtilmeli. Ornek: hotkey('ctrl', 'c') veya hotkey(keys_list=['ctrl', 'c'])"}
        
        pyautogui.hotkey(*key_sequence)
        return {"success": True, "keys": key_sequence}
    except Exception as e:
        return {"error": str(e)}


def tool_alert(message: str, title: str = "OpenWorld Agent") -> Dict[str, Any]:
    """Ekranda uyari penceresi goster."""
    try:
        pyautogui.alert(text=message, title=title, button='Tamam')
        return {"success": True, "message": message}
    except Exception as e:
        return {"error": str(e)}


def tool_confirm(message: str, title: str = "OpenWorld Agent") -> Dict[str, Any]:
    """Onay penceresi goster."""
    try:
        result = pyautogui.confirm(text=message, title=title, buttons=['Evet', 'Hayir'])
        return {"success": True, "result": result}
    except Exception as e:
        return {"error": str(e)}


def tool_prompt(message: str, title: str = "OpenWorld Agent", default: str = "") -> Dict[str, Any]:
    """Kullanicidan giris iste."""
    try:
        result = pyautogui.prompt(text=message, title=title, default=default)
        return {"success": True, "result": result}
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# WINDOWS OZEL ARACLAR
# =============================================================================

def tool_get_window_list() -> Dict[str, Any]:
    """Acik penceleri listele."""
    try:
        if platform.system() == "Windows":
            import win32gui
            
            windows = []
            
            def callback(hwnd, extra):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title:
                        rect = win32gui.GetWindowRect(hwnd)
                        windows.append({
                            "handle": hwnd,
                            "title": title,
                            "rect": {
                                "left": rect[0],
                                "top": rect[1],
                                "right": rect[2],
                                "bottom": rect[3],
                                "width": rect[2] - rect[0],
                                "height": rect[3] - rect[1]
                            }
                        })
            
            win32gui.EnumWindows(callback, None)
            return {"windows": windows, "count": len(windows)}
        else:
            return {"error": "Bu ozellik su anda sadece Windows'da destekleniyor"}
            
    except Exception as e:
        return {"error": str(e)}


def tool_activate_window(title_pattern: str) -> Dict[str, Any]:
    """Belirli bir pencereyi one getir."""
    try:
        if platform.system() == "Windows":
            import re

            try:
                import win32gui

                matched: Dict[str, Any] = {"hwnd": None, "title": ""}

                def callback(hwnd, extra):
                    if matched["hwnd"] is not None:
                        return
                    if not win32gui.IsWindowVisible(hwnd):
                        return
                    title = win32gui.GetWindowText(hwnd) or ""
                    if not title:
                        return
                    if re.search(title_pattern, title, re.IGNORECASE):
                        matched["hwnd"] = hwnd
                        matched["title"] = title

                win32gui.EnumWindows(callback, None)

                hwnd = matched.get("hwnd")
                if hwnd is None:
                    return {"success": False, "pattern": title_pattern, "error": "Pencere bulunamadi"}

                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, 9)  # SW_RESTORE
                win32gui.SetForegroundWindow(hwnd)
                return {"success": True, "pattern": title_pattern, "title": matched.get("title", "")}
            except Exception:
                # pywin32 olmayan ortamlarda pygetwindow fallback'i kullan.
                import pygetwindow as gw

                windows = gw.getAllWindows()
                for win in windows:
                    title = getattr(win, "title", "") or ""
                    if not title:
                        continue
                    if re.search(title_pattern, title, re.IGNORECASE):
                        try:
                            if hasattr(win, "isMinimized") and win.isMinimized:
                                win.restore()
                            win.activate()
                            return {"success": True, "pattern": title_pattern, "title": title}
                        except Exception as exc:
                            return {"success": False, "pattern": title_pattern, "error": str(exc)}
                return {"success": False, "pattern": title_pattern, "error": "Pencere bulunamadi"}
        else:
            return {"error": "Bu ozellik su anda sadece Windows'da destekleniyor"}
            
    except Exception as e:
        return {"error": str(e)}


def tool_minimize_all_windows() -> Dict[str, Any]:
    """Tum pencereleri simge durumuna kucult."""
    try:
        if platform.system() == "Windows":
            import win32gui
            win32gui.EnumWindows(lambda hwnd, extra: win32gui.ShowWindow(hwnd, 6) if win32gui.IsWindowVisible(hwnd) else None, None)
            return {"success": True, "message": "Tum pencereler simge durumuna kucultuldu"}
        else:
            return {"error": "Bu ozellik su anda sadece Windows'da destekleniyor"}
    except Exception as e:
        return {"error": str(e)}


def tool_lock_workstation() -> Dict[str, Any]:
    """Is istasyonunu kilitle."""
    try:
        if platform.system() == "Windows":
            import ctypes
            ctypes.windll.user32.LockWorkStation()
            return {"success": True, "message": "Is istasyonu kilitlendi"}
        else:
            return {"error": "Bu ozellik su anda sadece Windows'da destekleniyor"}
    except Exception as e:
        return {"error": str(e)}


def tool_shutdown_system(action: str = "shutdown", timeout: int = 60) -> Dict[str, Any]:
    """Bilgisayari kapat/yeniden baslat."""
    try:
        if action not in ["shutdown", "restart", "logout"]:
            return {"error": "Gecersiz action. shutdown/restart/logout kullanin"}
        
        if platform.system() == "Windows":
            if action == "shutdown":
                subprocess.run(["shutdown", "/s", "/t", str(timeout), "/c", "OpenWorld Agent tarafindan kapatiliyor"])
            elif action == "restart":
                subprocess.run(["shutdown", "/r", "/t", str(timeout), "/c", "OpenWorld Agent tarafindan yeniden baslatiliyor"])
            elif action == "logout":
                subprocess.run(["shutdown", "/l"])
            
            return {"success": True, "action": action, "timeout": timeout}
        else:
            return {"error": "Bu ozellik su anda sadece Windows'da destekleniyor"}
            
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# IDE ONAY BEKLEME VE KABUL
# =============================================================================

def _normalize_for_ocr_match(text: str) -> str:
    normalized = (text or "").translate(_TR_TRANSLATION).lower()
    normalized = unicodedata.normalize("NFKD", normalized)
    normalized = "".join(ch for ch in normalized if ch.isalnum() or ch.isspace())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _get_window_region(title_pattern: str) -> Optional[Tuple[int, int, int, int]]:
    if platform.system() != "Windows" or not title_pattern:
        return None
    try:
        import win32gui

        matched: Dict[str, Tuple[int, int, int, int]] = {}

        def callback(hwnd, _):
            if matched:
                return
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd) or ""
            if not title:
                return
            if not re.search(title_pattern, title, re.IGNORECASE):
                return
            rect = win32gui.GetWindowRect(hwnd)
            left, top, right, bottom = rect
            width = max(1, right - left)
            height = max(1, bottom - top)
            if width < 200 or height < 120:
                return
            matched["region"] = (max(0, left), max(0, top), width, height)

        win32gui.EnumWindows(callback, None)
        return matched.get("region")
    except Exception:
        return None


def tool_wait_and_accept_approval(
    window_pattern: str = "Visual Studio Code|Code - Insiders",
    timeout: int = 25,
    interval: float = 0.8,
    min_confidence: float = 40.0,
    lang: str = "tur+eng",
    allow_keyboard_fallback: bool = False,
) -> Dict[str, Any]:
    """Bekleyen IDE onay penceresini OCR ile bulup kabul etmeye calis."""
    try:
        import pytesseract
        from pytesseract import Output
    except Exception as exc:
        if allow_keyboard_fallback:
            try:
                if window_pattern:
                    activation = tool_activate_window(window_pattern)
                    if isinstance(activation, dict) and not activation.get("success"):
                        return {
                            "success": False,
                            "window_pattern": window_pattern,
                            "method": "keyboard_fallback",
                            "note": "OCR yok; fallback denemesi yapilmadi cunku hedef pencere bulunamadi.",
                        }
                pyautogui.hotkey("alt", "y")
                time.sleep(0.1)
                pyautogui.press("enter")
                return {
                    "success": True,
                    "window_pattern": window_pattern,
                    "method": "keyboard_fallback",
                    "note": "OCR yoktu, Alt+Y + Enter denendi.",
                }
            except Exception as fallback_exc:
                return {"error": str(fallback_exc)}
        return {
            "error": str(exc),
            "note": "pytesseract kurulu olmadan onay otomasyonu calismaz.",
        }

    timeout = max(2, min(int(timeout), 180))
    interval = max(0.25, min(float(interval), 3.0))
    min_confidence = max(0.0, min(float(min_confidence), 100.0))

    context_terms = {_normalize_for_ocr_match(x) for x in _DEFAULT_APPROVAL_CONTEXT_TERMS}
    button_terms_single = {_normalize_for_ocr_match(x) for x in _DEFAULT_APPROVAL_BUTTON_TERMS}
    button_terms_multi = {_normalize_for_ocr_match(x) for x in _DEFAULT_APPROVAL_BUTTON_TERMS_MULTI}

    end_time = time.time() + timeout
    checks = 0
    last_blob = ""
    region = None

    while time.time() < end_time:
        checks += 1

        if window_pattern:
            tool_activate_window(window_pattern)
            region = _get_window_region(window_pattern)

        screenshot = pyautogui.screenshot(region=region) if region else pyautogui.screenshot()
        try:
            data = pytesseract.image_to_data(screenshot, lang=lang, output_type=Output.DICT)
        except Exception as exc:
            if allow_keyboard_fallback:
                try:
                    if window_pattern:
                        activation = tool_activate_window(window_pattern)
                        if isinstance(activation, dict) and not activation.get("success"):
                            return {
                                "success": False,
                                "checks": checks,
                                "window_pattern": window_pattern,
                                "method": "keyboard_fallback",
                                "note": "OCR calismadi; fallback denemesi yapilmadi cunku hedef pencere bulunamadi.",
                            }
                    pyautogui.hotkey("alt", "y")
                    time.sleep(0.1)
                    pyautogui.press("enter")
                    return {
                        "success": True,
                        "checks": checks,
                        "window_pattern": window_pattern,
                        "method": "keyboard_fallback",
                        "note": "OCR calismadigi icin klavye fallback denendi.",
                    }
                except Exception as fallback_exc:
                    return {"error": str(fallback_exc)}
            return {
                "error": str(exc),
                "note": "Tesseract OCR bulunamadi veya calismiyor. Onay otomasyonu devre disi.",
            }

        words: List[Dict[str, Any]] = []
        blob_parts: List[str] = []
        count = len(data.get("text", []))
        for i in range(count):
            raw = str(data["text"][i] or "").strip()
            if not raw:
                continue
            norm = _normalize_for_ocr_match(raw)
            if not norm:
                continue
            try:
                conf = float(data["conf"][i])
            except Exception:
                conf = -1.0
            if conf < min_confidence:
                continue
            words.append(
                {
                    "norm": norm,
                    "raw": raw,
                    "left": int(data["left"][i]),
                    "top": int(data["top"][i]),
                    "width": int(data["width"][i]),
                    "height": int(data["height"][i]),
                    "conf": conf,
                }
            )
            blob_parts.append(norm)

        blob = " ".join(blob_parts)
        last_blob = blob[:500]
        has_context = any(term in blob for term in context_terms)
        if not words:
            time.sleep(interval)
            continue

        candidates: List[Dict[str, Any]] = []
        for i, current in enumerate(words):
            token = current["norm"]
            if token in button_terms_single:
                candidates.append(current)

            if i + 1 < len(words):
                pair = f"{token} {words[i + 1]['norm']}"
                if pair in button_terms_multi:
                    left = min(current["left"], words[i + 1]["left"])
                    top = min(current["top"], words[i + 1]["top"])
                    right = max(current["left"] + current["width"], words[i + 1]["left"] + words[i + 1]["width"])
                    bottom = max(current["top"] + current["height"], words[i + 1]["top"] + words[i + 1]["height"])
                    candidates.append(
                        {
                            "norm": pair,
                            "raw": f"{current['raw']} {words[i + 1]['raw']}",
                            "left": left,
                            "top": top,
                            "width": max(1, right - left),
                            "height": max(1, bottom - top),
                            "conf": min(current["conf"], words[i + 1]["conf"]),
                        }
                    )

        if has_context and candidates:
            # Dialog buttons generally appear in the lower-right area.
            best = sorted(
                candidates,
                key=lambda c: (c["top"], c["left"], c["conf"]),
                reverse=True,
            )[0]

            click_x = int(best["left"] + (best["width"] / 2))
            click_y = int(best["top"] + (best["height"] / 2))
            if region:
                click_x += int(region[0])
                click_y += int(region[1])

            pyautogui.click(click_x, click_y)
            return {
                "success": True,
                "checks": checks,
                "window_pattern": window_pattern,
                "clicked_text": best["raw"],
                "x": click_x,
                "y": click_y,
                "method": "ocr_click",
            }

        time.sleep(interval)

    return {
        "success": False,
        "checks": checks,
        "window_pattern": window_pattern,
        "message": "Onay penceresi tespit edilmedi.",
        "last_seen_text": last_blob,
    }


# =============================================================================
# OCR (OPTIK KARAKTER TANIMA)
# =============================================================================

def tool_ocr_screenshot(region: List[int] = None, lang: str = "tur") -> Dict[str, Any]:
    """Ekran goruntusunden metin oku."""
    try:
        import pytesseract
        
        # Ekran goruntusu al
        if region and len(region) == 4:
            screenshot = pyautogui.screenshot(region=tuple(region))
        else:
            screenshot = pyautogui.screenshot()
        
        # OCR yap
        text = pytesseract.image_to_string(screenshot, lang=lang)
        
        return {
            "text": text,
            "language": lang,
            "character_count": len(text)
        }
        
    except Exception as e:
        return {"error": str(e), "note": "Tesseract OCR kurulu oldugundan emin olun"}


def tool_ocr_image(image_path: str, lang: str = "tur") -> Dict[str, Any]:
    """Goruntu dosyasindan metin oku."""
    try:
        import pytesseract
        from PIL import Image
        
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image, lang=lang)
        
        return {
            "text": text,
            "language": lang,
            "character_count": len(text)
        }
        
    except Exception as e:
        return {"error": str(e)}
