"""
SUPER AGENT TOOLS
Gerçek bir ajan için gelişmiş yetenekler
"""
from __future__ import annotations

import base64
import io
import json
import os
import platform
import subprocess
import tempfile
import time
import usb.core
import usb.util
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import pyautogui
import sounddevice as sd
import scipy.io.wavfile as wav
from PIL import Image, ImageGrab

from ..config import settings

# =============================================================================
# SCREENSHOT ARAÇLARI
# =============================================================================

def tool_screenshot_desktop(output_path: str = "", region: List[int] = None) -> Dict[str, Any]:
    """Masaüstü ekran görüntüsü al."""
    try:
        if region and len(region) == 4:
            # Belirli bölge: [x, y, width, height]
            x, y, w, h = region
            screenshot = pyautogui.screenshot(region=(x, y, w, h))
        else:
            # Tam ekran
            screenshot = pyautogui.screenshot()
        
        # Kaydet
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"data/screenshots/desktop_{timestamp}.png"
        
        target = Path(output_path)
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
    """Web sayfası ekran görüntüsü al."""
    try:
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
            time.sleep(wait_time)  # Sayfanın yüklenmesini bekle
            
            if not output_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                domain = url.replace("https://", "").replace("http://", "").replace("/", "_")[:30]
                output_path = f"data/screenshots/web_{domain}_{timestamp}.png"
            
            target = Path(output_path)
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
        return {"error": str(e), "note": "Chrome kurulu olduğundan emin olun"}


def tool_find_image_on_screen(image_path: str, confidence: float = 0.9) -> Dict[str, Any]:
    """Ekranda bir görüntü ara ve konumunu bul."""
    try:
        target = Path(image_path)
        if not target.exists():
            return {"error": "Görüntü dosyası bulunamadı", "path": image_path}
        
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
            return {"found": False, "message": "Görüntü ekranda bulunamadı"}
            
    except Exception as e:
        return {"error": str(e)}


def tool_click_on_screen(x: int, y: int, clicks: int = 1, button: str = "left") -> Dict[str, Any]:
    """Ekranda belirli bir koordinata tıkla."""
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
    """Klavye tuşuna bas."""
    try:
        pyautogui.press(key, presses=presses)
        return {"success": True, "key": key, "presses": presses}
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# SES KAYIT ARAÇLARI
# =============================================================================

class AudioRecorder:
    """Ses kaydedici sınıf."""
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
    """Ses kaydına başla."""
    global _audio_recorder
    try:
        _audio_recorder = AudioRecorder()
        _audio_recorder.start_recording()
        return {"success": True, "message": "Ses kaydı başladı", "sample_rate": 44100}
    except Exception as e:
        return {"error": str(e)}


def tool_stop_audio_recording(output_path: str = "") -> Dict[str, Any]:
    """Ses kaydını durdur ve kaydet."""
    global _audio_recorder
    try:
        if not _audio_recorder:
            return {"error": "Aktif ses kaydı yok"}
        
        _audio_recorder.stop_recording()
        
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"data/audio/recording_{timestamp}.wav"
        
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        
        if _audio_recorder.save(str(target)):
            return {
                "success": True,
                "path": str(target),
                "size": target.stat().st_size
            }
        else:
            return {"error": "Kayıt boş veya kaydedilemedi"}
            
    except Exception as e:
        return {"error": str(e)}


def tool_play_audio(audio_path: str) -> Dict[str, Any]:
    """Ses dosyasını çal."""
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
    """Metni sese çevir."""
    try:
        # Windows TTS
        if platform.system() == "Windows":
            import win32com.client
            
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            
            if not output_path:
                # Doğrudan konuş
                speaker.Speak(text)
                return {"success": True, "spoken": text, "mode": "direct"}
            else:
                # Dosyaya kaydet
                target = Path(output_path)
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
            return {"error": "TTS şu anda sadece Windows'da destekleniyor"}
            
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# WEBCAM ARAÇLARI
# =============================================================================

def tool_webcam_capture(output_path: str = "", camera_index: int = 0) -> Dict[str, Any]:
    """Webcam'den fotoğraf çek."""
    try:
        cap = cv2.VideoCapture(camera_index)
        
        if not cap.isOpened():
            return {"error": f"Kamera {camera_index} açılamadı"}
        
        # Birkaç kare bekle (oto focus)
        for _ in range(5):
            cap.read()
        
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            return {"error": "Kare yakalanamadı"}
        
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"data/webcam/capture_{timestamp}.jpg"
        
        target = Path(output_path)
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
            return {"error": f"Kamera {camera_index} açılamadı"}
        
        # Video özellikleri
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = 20.0
        
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"data/webcam/video_{timestamp}.avi"
        
        target = Path(output_path)
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
    """Kullanılabilir kameraları listele."""
    try:
        cameras = []
        
        for i in range(10):  # İlk 10 kamerayı dene
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
# USB CİHAZ ARAÇLARI
# =============================================================================

def tool_list_usb_devices() -> Dict[str, Any]:
    """Bağlı USB cihazlarını listele."""
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
                # Bazı cihazlar string alanlarını desteklemez
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
    """USB sürücüsünü güvenli çıkar."""
    try:
        if platform.system() == "Windows":
            # PowerShell ile çıkar
            ps_command = f"(New-Object -comObject Shell.Application).Namespace(17).ParseName('{drive_letter}:').InvokeVerb('Eject')"
            result = subprocess.run(["powershell", "-Command", ps_command], 
                                  capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                return {"success": True, "drive": drive_letter, "message": "Sürücü güvenli çıkarıldı"}
            else:
                return {"error": result.stderr or "Çıkarma başarısız"}
        else:
            return {"error": "Bu özellik şu anda sadece Windows'da destekleniyor"}
            
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# GELİŞMİŞ OTOMASYON
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
    """Sürükle-bırak yap."""
    try:
        pyautogui.dragTo(x, y, duration=duration, button=button)
        return {"success": True, "to_x": x, "to_y": y}
    except Exception as e:
        return {"error": str(e)}


def tool_scroll(amount: int, x: int = None, y: int = None) -> Dict[str, Any]:
    """Fare tekerleği kaydır."""
    try:
        if x is not None and y is not None:
            pyautogui.scroll(amount, x=x, y=y)
        else:
            pyautogui.scroll(amount)
        return {"success": True, "amount": amount}
    except Exception as e:
        return {"error": str(e)}


def tool_hotkey(*keys: str) -> Dict[str, Any]:
    """Klavye kısayolu çalıştır."""
    try:
        pyautogui.hotkey(*keys)
        return {"success": True, "keys": keys}
    except Exception as e:
        return {"error": str(e)}


def tool_alert(message: str, title: str = "OpenWorld Agent") -> Dict[str, Any]:
    """Ekranda uyarı penceresi göster."""
    try:
        pyautogui.alert(text=message, title=title, button='Tamam')
        return {"success": True, "message": message}
    except Exception as e:
        return {"error": str(e)}


def tool_confirm(message: str, title: str = "OpenWorld Agent") -> Dict[str, Any]:
    """Onay penceresi göster."""
    try:
        result = pyautogui.confirm(text=message, title=title, buttons=['Evet', 'Hayır'])
        return {"success": True, "result": result}
    except Exception as e:
        return {"error": str(e)}


def tool_prompt(message: str, title: str = "OpenWorld Agent", default: str = "") -> Dict[str, Any]:
    """Kullanıcıdan giriş iste."""
    try:
        result = pyautogui.prompt(text=message, title=title, default=default)
        return {"success": True, "result": result}
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# WINDOWS ÖZEL ARAÇLAR
# =============================================================================

def tool_get_window_list() -> Dict[str, Any]:
    """Açık penceleri listele."""
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
            return {"error": "Bu özellik şu anda sadece Windows'da destekleniyor"}
            
    except Exception as e:
        return {"error": str(e)}


def tool_activate_window(title_pattern: str) -> Dict[str, Any]:
    """Belirli bir pencereyi öne getir."""
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
            return {"error": "Bu özellik şu anda sadece Windows'da destekleniyor"}
            
    except Exception as e:
        return {"error": str(e)}


def tool_minimize_all_windows() -> Dict[str, Any]:
    """Tüm pencereleri simge durumuna küçült."""
    try:
        if platform.system() == "Windows":
            import win32gui
            win32gui.EnumWindows(lambda hwnd, extra: win32gui.ShowWindow(hwnd, 6) if win32gui.IsWindowVisible(hwnd) else None, None)
            return {"success": True, "message": "Tüm pencereler simge durumuna küçültüldü"}
        else:
            return {"error": "Bu özellik şu anda sadece Windows'da destekleniyor"}
    except Exception as e:
        return {"error": str(e)}


def tool_lock_workstation() -> Dict[str, Any]:
    """İş istasyonunu kilitle."""
    try:
        if platform.system() == "Windows":
            import ctypes
            ctypes.windll.user32.LockWorkStation()
            return {"success": True, "message": "İş istasyonu kilitlendi"}
        else:
            return {"error": "Bu özellik şu anda sadece Windows'da destekleniyor"}
    except Exception as e:
        return {"error": str(e)}


def tool_shutdown_system(action: str = "shutdown", timeout: int = 60) -> Dict[str, Any]:
    """Bilgisayarı kapat/yeniden başlat."""
    try:
        if action not in ["shutdown", "restart", "logout"]:
            return {"error": "Geçersiz action. shutdown/restart/logout kullanın"}
        
        if platform.system() == "Windows":
            if action == "shutdown":
                subprocess.run(["shutdown", "/s", "/t", str(timeout), "/c", "OpenWorld Agent tarafından kapatılıyor"])
            elif action == "restart":
                subprocess.run(["shutdown", "/r", "/t", str(timeout), "/c", "OpenWorld Agent tarafından yeniden başlatılıyor"])
            elif action == "logout":
                subprocess.run(["shutdown", "/l"])
            
            return {"success": True, "action": action, "timeout": timeout}
        else:
            return {"error": "Bu özellik şu anda sadece Windows'da destekleniyor"}
            
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# OCR (OPTİK KARAKTER TANIMA)
# =============================================================================

def tool_ocr_screenshot(region: List[int] = None, lang: str = "tur") -> Dict[str, Any]:
    """Ekran görüntüsünden metin oku."""
    try:
        import pytesseract
        
        # Ekran görüntüsü al
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
        return {"error": str(e), "note": "Tesseract OCR kurulu olduğundan emin olun"}


def tool_ocr_image(image_path: str, lang: str = "tur") -> Dict[str, Any]:
    """Görüntü dosyasından metin oku."""
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
