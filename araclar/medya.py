"""
MFY AI - Medya, Ses ve Görsel Araçları
  SES        : ses_kontrol (genel ses VE uygulama başına ses; sonucu doğrular), medya_kontrol (oynat/duraklat/sonraki/önceki)
  CİHAZ/KAYIT: ses_cihazlari, mikrofon_kaydet, ses_cal
  SES<->YAZI : ses_dosyasini_yaziya_cevir (faster-whisper), metni_sese_cevir (Pocket TTS)
  GÖRSEL     : gorsel_bilgisi (boyut, EXIF), gorsel_donustur (boyutlandır / biçim değiştir)
Kurulum: pip install pycaw sounddevice pillow faster-whisper pocket-tts-turkish
"""

import os
import time
import wave
import threading
from datetime import datetime

import win32api
import win32con
from langchain.tools import tool

import config
import izinler
from izinler import sade
from araclar.ortak import boyut_metni as _boyut


# ============================================================
# SES SEVİYESİ
# ============================================================


_SES_KOMUTLARI = {
    "azalt": "azalt", "kis": "azalt", "kisalt": "azalt", "alcalt": "azalt", "dusur": "azalt", "azalt_": "azalt",
    "arttir": "arttir", "artir": "arttir", "yukselt": "arttir", "yuksel": "arttir", "yukari": "arttir",
    "ac": "ac", "sesi_ac": "sesi_ac", "sessizi_kapat": "sesi_ac", "unmute": "sesi_ac",
    "sessize_al": "sessize_al", "sessiz": "sessize_al", "sustur": "sessize_al", "mute": "sessize_al", "kapat": "sessize_al",
    "ayarla": "ayarla", "yap": "ayarla", "durum": "durum", "kac": "durum",
}


def _ses_arayuzu():
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    from ctypes import cast, POINTER
    hoparlor = AudioUtilities.GetSpeakers()
    if hasattr(hoparlor, "EndpointVolume"):        # yeni pycaw sürümleri
        return hoparlor.EndpointVolume
    arayuz = hoparlor.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)   # eski sürümler
    return cast(arayuz, POINTER(IAudioEndpointVolume))


def _ses_pycaw(komut: str, miktar: int) -> str:
    import comtypes
    comtypes.CoInitialize()
    try:
        vol = _ses_arayuzu()
        mevcut = round(vol.GetMasterVolumeLevelScalar() * 100)
        sessiz = bool(vol.GetMute())

        if komut == "durum":
            return f"Ses seviyesi %{mevcut}" + (" (şu an SESSİZDE)" if sessiz else "")
        if komut == "sessize_al":
            vol.SetMute(1, None)
            return f"Ses kapatıldı (sessize alındı). Seviye %{mevcut}."
        if komut == "sesi_ac" or (komut == "ac" and sessiz):
            vol.SetMute(0, None)
            return f"Sessiz modu kaldırıldı. Ses seviyesi %{mevcut}."

        if komut == "azalt":
            yeni = max(0, mevcut - miktar)
        elif komut in ("arttir", "ac"):
            yeni = min(100, mevcut + miktar)
        else:   # ayarla
            yeni = max(0, min(100, miktar))

        vol.SetMasterVolumeLevelScalar(yeni / 100.0, None)
        if yeni > 0 and sessiz:
            vol.SetMute(0, None)
        gercek = round(vol.GetMasterVolumeLevelScalar() * 100)
        return f"Ses %{mevcut} → %{gercek} (doğrulandı)."
    finally:
        try:
            comtypes.CoUninitialize()
        except Exception:
            pass


def _ses_tus(komut: str, miktar: int) -> str:
    """pycaw yoksa yedek yöntem: medya tuşları (sonucu doğrulayamaz)."""
    adim = max(1, min(int(miktar) // 2, 50))
    harita = {"azalt": 0xAE, "arttir": 0xAF, "ac": 0xAF, "sessize_al": 0xAD, "sesi_ac": 0xAD}
    if komut not in harita:
        return "Bu komut için pycaw gerekli. Terminalde şunu çalıştır: pip install pycaw"
    kez = 1 if komut in ("sessize_al", "sesi_ac") else adim
    for _ in range(kez):
        win32api.keybd_event(harita[komut], 0, 0, 0)
        win32api.keybd_event(harita[komut], 0, 2, 0)
        time.sleep(0.02)
    return ("Ses tuşu komutu gönderildi ama sonucu DOĞRULAYAMADIM (pycaw kurulu değil). "
            "Kesin kontrol için kullanıcıya şunu söyle: terminalde 'pip install pycaw' çalıştırsın.")


def _ses_uygulama(komut: str, miktar: int, uygulama: str) -> str:
    """Tek bir uygulamanın (Spotify, Chrome...) sesini pycaw ile yönetir ve sonucu okuyup doğrular."""
    import comtypes
    from pycaw.pycaw import AudioUtilities
    hedef = sade(uygulama).strip()
    if hedef in ("hepsi", "tumu", "tum", "herkes"):
        hedef = ""
    comtypes.CoInitialize()
    try:
        oturumlar = []
        for oturum in AudioUtilities.GetAllSessions():
            if oturum.Process is None:
                continue
            try:
                ad = oturum.Process.name()
            except Exception:
                continue
            if hedef and hedef not in sade(ad):
                continue
            oturumlar.append((ad, oturum.SimpleAudioVolume))
        if not oturumlar:
            return (f"'{uygulama}' için ses çıkaran bir uygulama bulunamadı "
                    f"(uygulama şu an ses çalmıyor olabilir).")
        satirlar = []
        for ad, ses in oturumlar:
            mevcut, sessiz = round(ses.GetMasterVolume() * 100), bool(ses.GetMute())
            if komut == "sessize_al":
                ses.SetMute(1, None)
            elif komut == "sesi_ac" or (komut == "ac" and sessiz):
                ses.SetMute(0, None)
            elif komut != "durum":
                if komut == "azalt":
                    yeni = max(0, mevcut - miktar)
                elif komut in ("arttir", "ac"):
                    yeni = min(100, mevcut + miktar)
                else:
                    yeni = max(0, min(100, miktar))
                ses.SetMasterVolume(yeni / 100.0, None)
                if yeni > 0 and sessiz:
                    ses.SetMute(0, None)
            gercek = round(ses.GetMasterVolume() * 100)
            satirlar.append(f"{ad}: %{mevcut}" + (f" → %{gercek}" if gercek != mevcut else "")
                            + (" (SESSİZ)" if ses.GetMute() else ""))
        return "\n".join(satirlar)
    finally:
        try:
            comtypes.CoUninitialize()
        except Exception:
            pass


@tool
def ses_kontrol(komut: str, miktar: int = 10, uygulama: str = "") -> str:
    """Ses seviyesini yönetir ve sonucu doğrular. uygulama BOŞSA bilgisayarın genel sesi, DOLUYSA yalnızca o uygulamanın sesi
    (örn. uygulama='spotify': sadece Spotify'ı kıs; uygulama='hepsi': ses çıkaran tüm uygulamalar).
    komut: 'azalt' (sesi kıs), 'arttir' (sesi aç/yükselt), 'ayarla' (miktar = hedef yüzde, örn. 30), 'sessize_al',
    'sesi_ac' (sessizi kaldır) veya 'durum'. miktar: azalt/arttir için kaç yüzde değişeceği (varsayılan 10).
    Ses çıkaran uygulamaları listelemek için uygulama='hepsi', komut='durum' kullan."""
    anahtar = sade(komut).strip().replace(" ", "_")
    kanonik = _SES_KOMUTLARI.get(anahtar)
    if kanonik is None:
        return "Hata: komut 'azalt', 'arttir', 'ayarla', 'sessize_al', 'sesi_ac' veya 'durum' olmalı."
    try:
        miktar = int(miktar)
    except (TypeError, ValueError):
        miktar = 10
    uygulama = (uygulama or "").strip()
    if uygulama:
        try:
            return _ses_uygulama(kanonik, miktar, uygulama)
        except ImportError:
            return "Uygulama başına ses için kullanıcıya terminalde 'pip install pycaw' çalıştırmasını söyle."
        except Exception as e:
            return f"Hata: {str(e)[:150]}"
    try:
        return _ses_pycaw(kanonik, miktar)
    except ImportError:
        return _ses_tus(kanonik, miktar)
    except Exception as e:
        try:
            return _ses_tus(kanonik, miktar) + f" (pycaw hatası: {e})"
        except Exception as e2:
            return f"Hata: Ses ayarlanamadı: {e2}"


# ============================================================
# MEDYA TUŞLARI
# ============================================================


def _tus_bas(vk_kodu: int, kez: int = 1):
    for _ in range(kez):
        win32api.keybd_event(vk_kodu, 0, 0, 0)
        win32api.keybd_event(vk_kodu, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.02)


@tool
def medya_kontrol(komut: str) -> str:
    """Çalan müziği/videoyu kontrol eder. komut: 'oynat_duraklat', 'sonraki' veya 'onceki'."""
    komut = komut.strip().lower()
    haritalama = {
        "oynat_duraklat": win32con.VK_MEDIA_PLAY_PAUSE, "oynat": win32con.VK_MEDIA_PLAY_PAUSE,
        "duraklat": win32con.VK_MEDIA_PLAY_PAUSE, "durdur": win32con.VK_MEDIA_PLAY_PAUSE,
        "sonraki": win32con.VK_MEDIA_NEXT_TRACK, "onceki": win32con.VK_MEDIA_PREV_TRACK,
        "önceki": win32con.VK_MEDIA_PREV_TRACK,
    }
    if komut not in haritalama:
        return "Hata: komut 'oynat_duraklat', 'sonraki' veya 'onceki' olmalı."
    _tus_bas(haritalama[komut])
    return f"Medya komutu gönderildi: {komut}"


# ============================================================
# CİHAZLAR, KAYIT, ÇALMA
# ============================================================


_model_kilidi = threading.Lock()


_stt_modeli = None


_tts_modeli = None


def _kayit_klasoru() -> str:
    k = os.path.join(config.CALISMA_ALANI, "kayitlar")
    os.makedirs(k, exist_ok=True)
    return k


@tool
def ses_cihazlari(bos_girdi: str = "") -> str:
    """Bilgisayardaki ses giriş (mikrofon) ve çıkış (hoparlör, kulaklık) cihazlarını listeler; varsayılanları işaretler."""
    try:
        import sounddevice as sd
    except ImportError:
        return "Bu araç için kullanıcıya terminalde 'pip install sounddevice' çalıştırmasını söyle."
    try:
        giris, cikis = sd.default.device
        satirlar = []
        for i, d in enumerate(sd.query_devices()):
            tur = []
            if d.get("max_input_channels", 0) > 0:
                tur.append("giriş" + (" (VARSAYILAN)" if i == giris else ""))
            if d.get("max_output_channels", 0) > 0:
                tur.append("çıkış" + (" (VARSAYILAN)" if i == cikis else ""))
            if tur:
                satirlar.append(f"[{i}] {d['name']} · {', '.join(tur)}")
        return "\n".join(satirlar[:40])
    except Exception as e:
        return f"Hata: {e}"


@tool
def mikrofon_kaydet(saniye: int = 5, dosya: str = "") -> str:
    """Mikrofondan ses kaydı alır ve .wav dosyası olarak kaydeder. saniye: süre (1-600). dosya: kayıt yolu
    (boşsa çalışma alanındaki 'kayitlar' klasörü). Kaydı yazıya çevirmek için ses_dosyasini_yaziya_cevir kullan."""
    try:
        import sounddevice as sd
    except ImportError:
        return "Bu araç için kullanıcıya terminalde 'pip install sounddevice' çalıştırmasını söyle."
    try:
        saniye = max(1, min(int(saniye), 600))
    except (TypeError, ValueError):
        saniye = 5
    yol = izinler.yol_coz(dosya) if (dosya or "").strip() else os.path.join(
        _kayit_klasoru(), datetime.now().strftime("kayit_%Y%m%d_%H%M%S.wav"))
    if not yol.lower().endswith(".wav"):
        yol += ".wav"
    izin, neden = izinler.degisiklige_acik_mi(yol)
    if not izin and os.path.abspath(yol).startswith(os.path.abspath(config.CALISMA_ALANI)) is False:
        return f"Yapılamaz: {neden}"
    if not izinler.onay_iste(f"Mikrofon {saniye} saniye kaydedilecek:", yol, seviye=2):
        return izinler.RED_MESAJI
    try:
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        kayit = sd.rec(int(saniye * 16000), samplerate=16000, channels=1, dtype="int16")
        sd.wait()
        with wave.open(yol, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(kayit.tobytes())
        return f"Kayıt alındı: {yol} ({saniye} sn, {_boyut(os.path.getsize(yol))})"
    except Exception as e:
        return f"Hata: Kayıt alınamadı: {str(e)[:150]}"


@tool
def ses_cal(dosya: str) -> str:
    """Bir ses dosyasını çalar (.wav doğrudan, diğer türler varsayılan oynatıcıyla)."""
    yol = izinler.yol_coz(dosya)
    if not os.path.isfile(yol):
        return f"Dosya bulunamadı: {yol}"
    try:
        if yol.lower().endswith(".wav"):
            import winsound
            winsound.PlaySound(yol, winsound.SND_FILENAME | winsound.SND_ASYNC)
        else:
            os.startfile(yol)
        return f"Çalınıyor: {yol}"
    except Exception as e:
        return f"Hata: {e}"


# ============================================================
# SES <-> YAZI
# ============================================================


@tool
def ses_dosyasini_yaziya_cevir(dosya: str, dil: str = "tr") -> str:
    """Bir ses ya da video dosyasındaki konuşmayı yazıya çevirir (toplantı kaydı, sesli not, video). dil: 'tr', 'en'...
    Uzun dosyalar CPU'da zaman alır; ilk kullanımda model belleğe yüklenir."""
    global _stt_modeli
    yol = izinler.yol_coz(dosya)
    if not os.path.isfile(yol):
        return f"Dosya bulunamadı: {yol}"
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return "Bu araç için kullanıcıya terminalde 'pip install faster-whisper' çalıştırmasını söyle."
    try:
        with _model_kilidi:
            if _stt_modeli is None:
                cihaz = "cuda" if getattr(config, "SES_STT_CIHAZ", "cpu") == "cuda" else "cpu"
                _stt_modeli = WhisperModel(getattr(config, "SES_STT_MODEL", "large-v3-turbo"), device=cihaz,
                                           compute_type="int8_float16" if cihaz == "cuda" else "int8")
        bas = time.time()
        segmentler, bilgi = _stt_modeli.transcribe(yol, language=(dil or "tr").strip().lower(), beam_size=1,
                                                   vad_filter=True, condition_on_previous_text=False)
        metin = " ".join(s.text.strip() for s in segmentler).strip()
        if not metin:
            return "Dosyada anlaşılır bir konuşma bulunamadı."
        return f"[{bilgi.duration:.0f} sn ses, {time.time() - bas:.0f} sn'de çözüldü]\n{metin[:12000]}"
    except Exception as e:
        return f"Hata: Yazıya çevrilemedi: {str(e)[:200]}"


@tool
def metni_sese_cevir(metin: str, dosya: str = "", ses: str = "female_2") -> str:
    """Bir metni konuşma sesine çevirip .wav dosyası olarak kaydeder (sesli not, duyuru). ses: female_1-3, male_1-3.
    dosya: kaydedilecek yol (boşsa çalışma alanındaki 'kayitlar' klasörü)."""
    global _tts_modeli
    metin = (metin or "").strip()
    if not metin:
        return "Hata: Metin boş."
    try:
        import numpy as np
        from pocket_tts_turkish import TurkishTTS
    except ImportError:
        return "Bu araç için kullanıcıya terminalde 'pip install pocket-tts-turkish' çalıştırmasını söyle."
    yol = izinler.yol_coz(dosya) if (dosya or "").strip() else os.path.join(
        _kayit_klasoru(), datetime.now().strftime("ses_%Y%m%d_%H%M%S.wav"))
    if not yol.lower().endswith(".wav"):
        yol += ".wav"
    izin, neden = izinler.degisiklige_acik_mi(yol)
    if not izin and os.path.abspath(yol).startswith(os.path.abspath(config.CALISMA_ALANI)) is False:
        return f"Yapılamaz: {neden}"
    try:
        with _model_kilidi:
            if _tts_modeli is None:
                _tts_modeli = TurkishTTS.from_pretrained(device=getattr(config, "SES_TTS_CIHAZ", "cpu"))
            dizi = np.asarray(_tts_modeli.generate(metin[:3000], voice=ses), dtype=np.float32).reshape(-1)
            hiz = int(getattr(_tts_modeli, "sample_rate", 24000))
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with wave.open(yol, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(hiz)
            w.writeframes((np.clip(dizi, -1, 1) * 32767).astype(np.int16).tobytes())
        return f"Ses dosyası oluşturuldu: {yol} ({len(dizi) / hiz:.1f} sn)"
    except Exception as e:
        return f"Hata: Ses üretilemedi: {str(e)[:200]}"


# ============================================================
# GÖRSEL (Pillow)
# ============================================================


@tool
def gorsel_bilgisi(yol: str) -> str:
    """Bir görselin (jpg, png, webp...) boyutunu, türünü ve varsa EXIF bilgilerini (çekim tarihi, cihaz modeli) söyler."""
    yol_t = izinler.yol_coz(yol)
    if not os.path.isfile(yol_t):
        return f"Dosya bulunamadı: {yol_t}"
    try:
        from PIL import Image, ExifTags
    except ImportError:
        return "Bu araç için kullanıcıya terminalde 'pip install pillow' çalıştırmasını söyle."
    try:
        with Image.open(yol_t) as g:
            satirlar = [f"{os.path.basename(yol_t)}: {g.width}x{g.height} piksel · {g.format} · {g.mode} · {_boyut(os.path.getsize(yol_t))}"]
            exif = g.getexif()
            for etiket, deger in exif.items():
                ad = ExifTags.TAGS.get(etiket, str(etiket))
                if ad in ("Make", "Model", "DateTime", "Software", "Orientation") and deger:
                    satirlar.append(f"{ad}: {str(deger)[:80]}")
        return "\n".join(satirlar)
    except Exception as e:
        return f"Hata: Görsel okunamadı: {e}"


@tool
def gorsel_donustur(yol: str, hedef: str = "", genislik: int = 0, yukseklik: int = 0, kalite: int = 90) -> str:
    """Bir görseli yeniden boyutlandırır ve/veya biçimini değiştirir. hedef: yeni dosya yolu; uzantısı biçimi belirler
    (örn. 'foto_kucuk.jpg', 'logo.webp'); boşsa aynı klasöre '_yeni' ekleyerek kaydeder. genislik/yukseklik: piksel
    (yalnızca biri verilirse oran korunur; 0 = değiştirme). kalite: jpg/webp için 1-100. Orijinal dosya değişmez."""
    yol_t = izinler.yol_coz(yol)
    if not os.path.isfile(yol_t):
        return f"Dosya bulunamadı: {yol_t}"
    try:
        from PIL import Image
    except ImportError:
        return "Bu araç için kullanıcıya terminalde 'pip install pillow' çalıştırmasını söyle."
    if (hedef or "").strip():
        h = izinler.yol_coz(hedef)
    else:
        kok, uz = os.path.splitext(yol_t)
        h = kok + "_yeni" + uz
    if os.path.abspath(h) == os.path.abspath(yol_t):
        return "Hata: Hedef, orijinal dosyayla aynı olamaz (orijinal korunur)."
    izin, neden = izinler.degisiklige_acik_mi(h)
    if not izin:
        return f"Yapılamaz: {neden}"
    if not izinler.onay_iste("Görsel dönüştürülecek:", f"{yol_t}\n→ {h}", seviye=1):
        return izinler.RED_MESAJI
    try:
        genislik, yukseklik = max(0, int(genislik)), max(0, int(yukseklik))
        kalite = max(1, min(int(kalite), 100))
    except (TypeError, ValueError):
        return "Hata: genislik, yukseklik ve kalite sayı olmalı."
    try:
        with Image.open(yol_t) as g:
            g.load()
            if genislik or yukseklik:
                if genislik and not yukseklik:
                    yukseklik = max(1, round(g.height * genislik / g.width))
                elif yukseklik and not genislik:
                    genislik = max(1, round(g.width * yukseklik / g.height))
                g = g.resize((genislik, yukseklik), Image.LANCZOS)
            if h.lower().endswith((".jpg", ".jpeg", ".bmp")) and g.mode in ("RGBA", "LA", "P"):
                g = g.convert("RGB")
            os.makedirs(os.path.dirname(h), exist_ok=True)
            g.save(h, quality=kalite)
        return f"Kaydedildi: {h} ({_boyut(os.path.getsize(h))})"
    except Exception as e:
        return f"Hata: Dönüştürülemedi: {str(e)[:150]}"


ARACLAR = [
    ses_kontrol, medya_kontrol, ses_cihazlari, mikrofon_kaydet, ses_cal,
    ses_dosyasini_yaziya_cevir, metni_sese_cevir, gorsel_bilgisi, gorsel_donustur,
]
