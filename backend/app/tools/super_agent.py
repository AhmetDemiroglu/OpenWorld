"""
SUPER AGENT TOOLS
GerÃ§ek bir ajan iÃ§in geliÅŸmiÅŸ yetenekler
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
# SCREENSHOT ARAÃ‡LARI
# =============================================================================

def tool_screenshot_desktop(output_path: str = "", region: List[int] = None) -> Dict[str, Any]:
    """MasaÃ¼stÃ¼ ekran gÃ¶rÃ¼ntÃ¼sÃ¼ al."""
    try:
        if region and len(region) == 4:
            # Belirli bÃ¶lge: [x, y, width, height]
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
    """Web sayfasÄ± ekran gÃ¶rÃ¼ntÃ¼sÃ¼ al."""
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
            time.sleep(max(1, min(wait_time, 20)))  # SayfanÄ±n yÃ¼klenmesini bekle
            
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
        return {"error": str(e), "note": "Chrome kurulu olduÄŸundan emin olun"}


def tool_find_image_on_screen(image_path: str, confidence: float = 0.9) -> Dict[str, Any]:
    """Ekranda bir gÃ¶rÃ¼ntÃ¼ ara ve konumunu bul."""
    try:
        target = Path(image_path)
        if not target.exists():
            return {"error": "GÃ¶rÃ¼ntÃ¼ dosyasÄ± bulunamadÄ±", "path": image_path}
        
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
            return {"found": False, "message": "GÃ¶rÃ¼ntÃ¼ ekranda bulunamadÄ±"}
            
    except Exception as e:
        return {"error": str(e)}


def tool_click_on_screen(x: int, y: int, clicks: int = 1, button: str = "left") -> Dict[str, Any]:
    """Ekranda belirli bir koordinata tÄ±kla."""
    try:
        pyautogui.click(x, y, clicks=clicks, button=button)
        return {"success": True, "x": x, "y": y, "clicks": clicks, "button": button}
    except Exception as e:
        return {"error": str(e)}


def tool_type_text(text: str, interval: float = 0.01) -> Dict[str, Any]:
    """Klavyeden metin yaz."""
    try:
        pyautogui.typewrite(text, interval=interval)
        return {"success": True, "typed": text, "length": len(text)}
    except Exception as e:
        return {"error": str(e)}


def tool_press_key(key: str, presses: int = 1) -> Dict[str, Any]:
    """Klavye tuÅŸuna bas."""
    try:
        pyautogui.press(key, presses=presses)
        return {"success": True, "key": key, "presses": presses}
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# SES KAYIT ARAÃ‡LARI
# =============================================================================

class AudioRecorder:
    """Ses kaydedici sÄ±nÄ±f."""
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
    """Ses kaydÄ±na baÅŸla."""
    global _audio_recorder
    try:
        _audio_recorder = AudioRecorder()
        _audio_recorder.start_recording()
        return {"success": True, "message": "Ses kaydÄ± baÅŸladÄ±", "sample_rate": 44100}
    except Exception as e:
        return {"error": str(e)}


def tool_stop_audio_recording(output_path: str = "") -> Dict[str, Any]:
    """Ses kaydÄ±nÄ± durdur ve kaydet."""
    global _audio_recorder
    try:
        if not _audio_recorder:
            return {"error": "Aktif ses kaydÄ± yok"}
        
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
            return {"error": "KayÄ±t boÅŸ veya kaydedilemedi"}
            
    except Exception as e:
        return {"error": str(e)}


def tool_play_audio(audio_path: str) -> Dict[str, Any]:
    """Ses dosyasÄ±nÄ± Ã§al."""
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
    """Metni sese Ã§evir."""
    try:
        # Windows TTS
        if platform.system() == "Windows":
            import win32com.client
            
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            
            if not output_path:
                # DoÄŸrudan konuÅŸ
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
            return {"error": "TTS ÅŸu anda sadece Windows'da destekleniyor"}
            
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# WEBCAM ARAÃ‡LARI
# =============================================================================

def tool_webcam_capture(output_path: str = "", camera_index: int = 0) -> Dict[str, Any]:
    """Webcam'den fotoÄŸraf Ã§ek."""
    try:
        cap = cv2.VideoCapture(camera_index)
        
        if not cap.isOpened():
            return {"error": f"Kamera {camera_index} aÃ§Ä±lamadÄ±"}
        
        # BirkaÃ§ kare bekle (oto focus)
        for _ in range(5):
            cap.read()
        
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            return {"error": "Kare yakalanamadÄ±"}
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"capture_{timestamp}.jpg"
        target = _resolve_generated_output_path(output_path, default_name, "media")
        target.parent.mkdir(parents=True, exist_ok=True)
        
        cv2.imwrite(str(target), frame)
        
        return {
            "success": True,
            "path": str(target),
            "size": target.stat().st_size,
            "resolution": f"{frame.shape[1]}x{frame.shape[0]}"
        }
        
    except Exception as e:
        return {"error": str(e)}


def tool_webcam_record_video(duration: int = 10, output_path: str = "", camera_index: int = 0) -> Dict[str, Any]:
    """Webcam'den video kaydet."""
    try:
        cap = cv2.VideoCapture(camera_index)
        
        if not cap.isOpened():
            return {"error": f"Kamera {camera_index} aÃ§Ä±lamadÄ±"}
        
        # Video Ã¶zellikleri
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
    """KullanÄ±labilir kameralarÄ± listele."""
    try:
        cameras = []
        
        for i in range(10):  # Ä°lk 10 kamerayÄ± dene
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
# USB CÄ°HAZ ARAÃ‡LARI
# =============================================================================

def tool_list_usb_devices() -> Dict[str, Any]:
    """BaÄŸlÄ± USB cihazlarÄ±nÄ± listele."""
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
                # BazÄ± cihazlar string alanlarÄ±nÄ± desteklemez
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
    """USB sÃ¼rÃ¼cÃ¼sÃ¼nÃ¼ gÃ¼venli Ã§Ä±kar."""
    try:
        if platform.system() == "Windows":
            # PowerShell ile Ã§Ä±kar
            ps_command = f"(New-Object -comObject Shell.Application).Namespace(17).ParseName('{drive_letter}:').InvokeVerb('Eject')"
            result = subprocess.run(["powershell", "-Command", ps_command], 
                                  capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                return {"success": True, "drive": drive_letter, "message": "SÃ¼rÃ¼cÃ¼ gÃ¼venli Ã§Ä±karÄ±ldÄ±"}
            else:
                return {"error": result.stderr or "Ã‡Ä±karma baÅŸarÄ±sÄ±z"}
        else:
            return {"error": "Bu Ã¶zellik ÅŸu anda sadece Windows'da destekleniyor"}
            
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# GELÄ°ÅMÄ°Å OTOMASYON
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
    """SÃ¼rÃ¼kle-bÄ±rak yap."""
    try:
        pyautogui.dragTo(x, y, duration=duration, button=button)
        return {"success": True, "to_x": x, "to_y": y}
    except Exception as e:
        return {"error": str(e)}


def tool_scroll(amount: int, x: int = None, y: int = None) -> Dict[str, Any]:
    """Fare tekerleÄŸi kaydÄ±r."""
    try:
        if x is not None and y is not None:
            pyautogui.scroll(amount, x=x, y=y)
        else:
            pyautogui.scroll(amount)
        return {"success": True, "amount": amount}
    except Exception as e:
        return {"error": str(e)}


def tool_hotkey(*keys: str) -> Dict[str, Any]:
    """Klavye kÄ±sayolu Ã§alÄ±ÅŸtÄ±r."""
    try:
        pyautogui.hotkey(*keys)
        return {"success": True, "keys": keys}
    except Exception as e:
        return {"error": str(e)}


def tool_alert(message: str, title: str = "OpenWorld Agent") -> Dict[str, Any]:
    """Ekranda uyarÄ± penceresi gÃ¶ster."""
    try:
        pyautogui.alert(text=message, title=title, button='Tamam')
        return {"success": True, "message": message}
    except Exception as e:
        return {"error": str(e)}


def tool_confirm(message: str, title: str = "OpenWorld Agent") -> Dict[str, Any]:
    """Onay penceresi gÃ¶ster."""
    try:
        result = pyautogui.confirm(text=message, title=title, buttons=['Evet', 'HayÄ±r'])
        return {"success": True, "result": result}
    except Exception as e:
        return {"error": str(e)}


def tool_prompt(message: str, title: str = "OpenWorld Agent", default: str = "") -> Dict[str, Any]:
    """KullanÄ±cÄ±dan giriÅŸ iste."""
    try:
        result = pyautogui.prompt(text=message, title=title, default=default)
        return {"success": True, "result": result}
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# WINDOWS Ã–ZEL ARAÃ‡LAR
# =============================================================================

def tool_get_window_list() -> Dict[str, Any]:
    """AÃ§Ä±k penceleri listele."""
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
            return {"error": "Bu Ã¶zellik ÅŸu anda sadece Windows'da destekleniyor"}
            
    except Exception as e:
        return {"error": str(e)}


def tool_activate_window(title_pattern: str) -> Dict[str, Any]:
    """Belirli bir pencereyi Ã¶ne getir."""
    try:
        if platform.system() == "Windows":
            import win32gui
            import re
            
            def callback(hwnd, extra):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if re.search(title_pattern, title, re.IGNORECASE):
                        win32gui.SetForegroundWindow(hwnd)
                        return True
                return False
            
            found = win32gui.EnumWindows(callback, None)
            return {"success": found, "pattern": title_pattern}
        else:
            return {"error": "Bu Ã¶zellik ÅŸu anda sadece Windows'da destekleniyor"}
            
    except Exception as e:
        return {"error": str(e)}


def tool_minimize_all_windows() -> Dict[str, Any]:
    """TÃ¼m pencereleri simge durumuna kÃ¼Ã§Ã¼lt."""
    try:
        if platform.system() == "Windows":
            import win32gui
            win32gui.EnumWindows(lambda hwnd, extra: win32gui.ShowWindow(hwnd, 6) if win32gui.IsWindowVisible(hwnd) else None, None)
            return {"success": True, "message": "TÃ¼m pencereler simge durumuna kÃ¼Ã§Ã¼ltÃ¼ldÃ¼"}
        else:
            return {"error": "Bu Ã¶zellik ÅŸu anda sadece Windows'da destekleniyor"}
    except Exception as e:
        return {"error": str(e)}


def tool_lock_workstation() -> Dict[str, Any]:
    """Ä°ÅŸ istasyonunu kilitle."""
    try:
        if platform.system() == "Windows":
            import ctypes
            ctypes.windll.user32.LockWorkStation()
            return {"success": True, "message": "Ä°ÅŸ istasyonu kilitlendi"}
        else:
            return {"error": "Bu Ã¶zellik ÅŸu anda sadece Windows'da destekleniyor"}
    except Exception as e:
        return {"error": str(e)}


def tool_shutdown_system(action: str = "shutdown", timeout: int = 60) -> Dict[str, Any]:
    """BilgisayarÄ± kapat/yeniden baÅŸlat."""
    try:
        if action not in ["shutdown", "restart", "logout"]:
            return {"error": "GeÃ§ersiz action. shutdown/restart/logout kullanÄ±n"}
        
        if platform.system() == "Windows":
            if action == "shutdown":
                subprocess.run(["shutdown", "/s", "/t", str(timeout), "/c", "OpenWorld Agent tarafÄ±ndan kapatÄ±lÄ±yor"])
            elif action == "restart":
                subprocess.run(["shutdown", "/r", "/t", str(timeout), "/c", "OpenWorld Agent tarafÄ±ndan yeniden baÅŸlatÄ±lÄ±yor"])
            elif action == "logout":
                subprocess.run(["shutdown", "/l"])
            
            return {"success": True, "action": action, "timeout": timeout}
        else:
            return {"error": "Bu Ã¶zellik ÅŸu anda sadece Windows'da destekleniyor"}
            
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# OCR (OPTÄ°K KARAKTER TANIMA)
# =============================================================================

def tool_ocr_screenshot(region: List[int] = None, lang: str = "tur") -> Dict[str, Any]:
    """Ekran gÃ¶rÃ¼ntÃ¼sÃ¼nden metin oku."""
    try:
        import pytesseract
        
        # Ekran gÃ¶rÃ¼ntÃ¼sÃ¼ al
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
        return {"error": str(e), "note": "Tesseract OCR kurulu olduÄŸundan emin olun"}


def tool_ocr_image(image_path: str, lang: str = "tur") -> Dict[str, Any]:
    """GÃ¶rÃ¼ntÃ¼ dosyasÄ±ndan metin oku."""
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
