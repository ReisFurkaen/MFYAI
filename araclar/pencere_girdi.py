"""
MFY AI - Pencere, Klavye ve Pano Araçları
  PENCERE : aktif_pencere, acik_pencereler, pencere_duzenle (öne getir / küçült / büyüt / yasla / kapat), masaustunu_goster
  KLAVYE  : tus_bas (kısayol gönderir), yaz (metin yazar; panodan yapıştırır, Türkçe karakter sorunsuz)
  PANO    : panoyu_oku, panoya_yaz
  EKRAN   : ekran_goruntusu (dosyaya kaydeder; ekranı GÖRMEK için ekran_ajan.py'deki ekrani_incele kullanılır)

KORUMA: Asistanın kendi penceresine yazılmaz/kapatılmaz. Terminal pencerelerine yazmak güven moduna göre onay ister.
"""

import os
import time
from datetime import datetime

import psutil
import win32api
import win32con
import win32gui
import win32process
import win32clipboard
from langchain.tools import tool

import config
import izinler
from izinler import sade


# ============================================================
# PENCERE, KLAVYE, PANO, EKRAN GÖRÜNTÜSÜ
# ============================================================


_KEYUP = 0x0002


_EXTENDED = 0x0001


_UZANTILI_TUSLAR = {0x26, 0x28, 0x25, 0x27, 0x24, 0x23, 0x21, 0x22, 0x2D, 0x2E, 0x5B}


def _kendi_penceremiz_mi(baslik: str) -> bool:
    return "mfy ai" in sade(baslik)


def _islem_adi(hwnd) -> str:
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return psutil.Process(pid).name()
    except Exception:
        return ""


def _pencereleri_bul(parca: str, kendimizi_dahil_et: bool = False) -> list:
    """Başlığında ya da program adında verilen kelime geçen görünür pencereler: [(hwnd, baslik), ...]"""
    hedef = sade(parca).strip()
    sonuc = []
    if not hedef:
        return sonuc

    def geri_cagri(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            baslik = win32gui.GetWindowText(hwnd).strip()
            if baslik and baslik != "Program Manager":
                if hedef in sade(baslik) or hedef in sade(_islem_adi(hwnd)):
                    if kendimizi_dahil_et or not _kendi_penceremiz_mi(baslik):
                        sonuc.append((hwnd, baslik))
        return True

    win32gui.EnumWindows(geri_cagri, None)
    return sonuc


def _one_getir(hwnd) -> bool:
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32api.keybd_event(0x12, 0, 0, 0)          # ALT: Windows'un odak kilidini aşmak için
        try:
            win32gui.SetForegroundWindow(hwnd)
        finally:
            win32api.keybd_event(0x12, 0, _KEYUP, 0)
        time.sleep(0.25)
        return win32gui.GetForegroundWindow() == hwnd
    except Exception:
        return False


def _hedef_hazirla(pencere: str):
    """Yazma/tuş işlemi için hedef pencereyi öne getirir. Döner: (hata_mesaji_veya_None, baslik_veya_None)"""
    on = win32gui.GetForegroundWindow()
    if pencere and pencere.strip():
        bulunanlar = _pencereleri_bul(pencere)
        if not bulunanlar:
            return f"'{pencere}' adında açık bir pencere bulamadım.", None
        hwnd, baslik = bulunanlar[0]
        if not _one_getir(hwnd):
            return f"'{baslik}' penceresini öne getiremedim; işlem yapılmadı.", None
        return None, baslik
    baslik = win32gui.GetWindowText(on).strip()
    if _kendi_penceremiz_mi(baslik) or not baslik:
        return ("Hangi pencereye yazılacağı/tuş basılacağı belirtilmedi ve şu an öndeki pencere asistanın kendisi. "
                "Kullanıcıya hedef pencereyi (örn. 'Not Defteri', 'Chrome') sor veya pencere parametresini doldur."), None
    return None, baslik


@tool
def aktif_pencere(bos_girdi: str = "") -> str:
    """Şu an öndeki (aktif) pencerenin başlığını ve programını söyler."""
    hwnd = win32gui.GetForegroundWindow()
    baslik = win32gui.GetWindowText(hwnd).strip()
    if not baslik:
        return "Aktif pencere bulunamadı."
    return f"Aktif pencere: {baslik} ({_islem_adi(hwnd) or 'program bilinmiyor'})"


@tool
def pencere_duzenle(pencere: str, islem: str) -> str:
    """Bir pencereyi yönetir. pencere: pencere başlığından veya program adından bir kelime (örn. 'chrome', 'not defteri').
    islem: 'one_getir', 'kucult', 'buyut', 'geri_al', 'sola_yasla', 'saga_yasla' veya 'kapat' (kapatma onay ister)."""
    islem_k = sade(islem).strip().replace(" ", "_")
    esdeger = {"one": "one_getir", "getir": "one_getir", "ac": "one_getir", "goster": "one_getir", "kucult": "kucult",
               "simge_durumuna_kucult": "kucult", "buyut": "buyut", "tam_ekran": "buyut", "geri": "geri_al",
               "sola": "sola_yasla", "saga": "saga_yasla", "kapat": "kapat"}
    islem_k = esdeger.get(islem_k, islem_k)
    if islem_k not in ("one_getir", "kucult", "buyut", "geri_al", "sola_yasla", "saga_yasla", "kapat"):
        return "Hata: islem 'one_getir', 'kucult', 'buyut', 'geri_al', 'sola_yasla', 'saga_yasla' veya 'kapat' olmalı."

    bulunanlar = _pencereleri_bul(pencere)
    if not bulunanlar:
        return f"'{pencere}' ile eşleşen açık bir pencere bulamadım."
    if islem_k == "kapat" and len(bulunanlar) > 1:
        liste = "\n".join(f"- {b}" for _, b in bulunanlar[:8])
        return f"'{pencere}' ile {len(bulunanlar)} pencere eşleşiyor, hangisini kapatmamı istediğini netleştir:\n{liste}"

    hwnd, baslik = bulunanlar[0]
    try:
        if islem_k == "one_getir":
            return f"'{baslik}' öne getirildi." if _one_getir(hwnd) else f"'{baslik}' öne getirilemedi."
        if islem_k == "kucult":
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            return f"'{baslik}' küçültüldü."
        if islem_k == "buyut":
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            return f"'{baslik}' ekranı kaplayacak şekilde büyütüldü."
        if islem_k == "geri_al":
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            return f"'{baslik}' eski boyutuna döndürüldü."
        if islem_k in ("sola_yasla", "saga_yasla"):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
            sol, ust, sag, alt = win32api.GetMonitorInfo(monitor)["Work"]
            yari = (sag - sol) // 2
            x = sol if islem_k == "sola_yasla" else sol + yari
            win32gui.MoveWindow(hwnd, x, ust, yari, alt - ust, True)
            return f"'{baslik}' ekranın {'sol' if islem_k == 'sola_yasla' else 'sağ'} yarısına yaslandı."
        # kapat
        if not izinler.onay_iste(f"Şu pencere kapatılacak:\n{baslik}", "Kaydedilmemiş veriler için uygulama sana soracaktır.", seviye=2):
            return izinler.RED_MESAJI
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        return f"'{baslik}' penceresine kapatma isteği gönderildi."
    except Exception as e:
        return f"Hata: Pencere işlemi başarısız: {e}"


@tool
def masaustunu_goster(bos_girdi: str = "") -> str:
    """Tüm pencereleri küçültüp masaüstünü gösterir (Win+D)."""
    try:
        win32api.keybd_event(0x5B, 0, _EXTENDED, 0)
        win32api.keybd_event(0x44, 0, 0, 0)
        win32api.keybd_event(0x44, 0, _KEYUP, 0)
        win32api.keybd_event(0x5B, 0, _EXTENDED | _KEYUP, 0)
        return "Masaüstü gösterildi."
    except Exception as e:
        return f"Hata: {e}"


_VK = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "windows": 0x5B,
    "enter": 0x0D, "esc": 0x1B, "escape": 0x1B, "tab": 0x09, "space": 0x20, "bosluk": 0x20,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
}


for _i in range(1, 13):
    _VK[f"f{_i}"] = 0x6F + _i


_MODIFIERS = {0x11, 0x10, 0x12, 0x5B}


# Bu kısayollar onay ister (veri kaybettirebilir / pencere kapatır)
_RISKLI_KISAYOLLAR = {"alt+f4", "ctrl+w", "ctrl+shift+w", "delete", "shift+delete", "ctrl+shift+delete",
                      "win+r", "ctrl+q", "ctrl+f4", "ctrl+shift+n"}


_YASAK_KISAYOLLAR = {"ctrl+alt+delete"}


# Buralara yazılan metin KOMUT olarak çalışabilir (powershell_calistir güvenliğini atlatmasın diye)
_TERMINAL_ISLEMLERI = {"cmd.exe", "powershell.exe", "pwsh.exe", "windowsterminal.exe", "wt.exe",
                       "conhost.exe", "openconsole.exe"}


def _tus_ayristir(kombinasyon: str):
    """'ctrl+shift+t' -> ([0x11, 0x10], 0x54). Geçersizse ValueError."""
    parcalar = [p.strip() for p in sade(kombinasyon).split("+") if p.strip()]
    if not parcalar:
        raise ValueError("Boş kısayol.")
    kodlar = []
    for p in parcalar:
        if p in _VK:
            kodlar.append(_VK[p])
        elif len(p) == 1 and p.isalnum():
            kodlar.append(ord(p.upper()))
        else:
            raise ValueError(f"Tanınmayan tuş: '{p}'")
    *modifiyeler, ana = kodlar
    if ana in _MODIFIERS and ana != 0x5B:
        raise ValueError("Kısayol bir ana tuş içermiyor (örn. 'ctrl+s').")
    if any(m not in _MODIFIERS for m in modifiyeler):
        raise ValueError("Kısayolda yalnızca ctrl/shift/alt/win bir tuşla birlikte kullanılabilir.")
    return modifiyeler, ana


def _tus_gonder(modifiyeler: list, ana: int):
    def bayrak(vk, yukari=False):
        return (_EXTENDED if vk in _UZANTILI_TUSLAR else 0) | (_KEYUP if yukari else 0)
    for m in modifiyeler:
        win32api.keybd_event(m, 0, bayrak(m), 0)
    win32api.keybd_event(ana, 0, bayrak(ana), 0)
    time.sleep(0.03)
    win32api.keybd_event(ana, 0, bayrak(ana, True), 0)
    for m in reversed(modifiyeler):
        win32api.keybd_event(m, 0, bayrak(m, True), 0)


@tool
def tus_bas(kombinasyon: str, pencere: str = "") -> str:
    """Klavye kısayolu gönderir (örn: 'ctrl+s', 'ctrl+shift+t', 'alt+tab', 'enter', 'f5', 'win+d').
    pencere: tuşun gönderileceği pencerenin adı (örn. 'chrome'). Boş bırakılırsa şu an öndeki pencereye gider."""
    norm = "+".join(sade(kombinasyon).replace(" ", "").split("+"))
    if norm in _YASAK_KISAYOLLAR:
        return "Bu kısayol güvenlik nedeniyle gönderilemez."
    try:
        modifiyeler, ana = _tus_ayristir(kombinasyon)
    except ValueError as e:
        return f"Hata: {e}"
    if norm in _RISKLI_KISAYOLLAR:
        if not izinler.onay_iste(f"'{kombinasyon}' kısayolu gönderilecek.",
                                 f"Hedef pencere: {pencere or '(şu an öndeki pencere)'}\nBu kısayol pencere kapatabilir veya veri silebilir.", seviye=2):
            return izinler.RED_MESAJI
    hata, baslik = _hedef_hazirla(pencere)
    if hata:
        return hata
    try:
        _tus_gonder(modifiyeler, ana)
        return f"'{kombinasyon}' '{baslik}' penceresine gönderildi."
    except Exception as e:
        return f"Hata: Tuş gönderilemedi: {e}"


def _pano_oku():
    try:
        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        pass
    return None


def _pano_yaz(metin: str) -> bool:
    for _ in range(6):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, metin)
            finally:
                win32clipboard.CloseClipboard()
            return True
        except Exception:
            time.sleep(0.06)
    return False


@tool
def yaz(metin: str, pencere: str = "", enter_bas: bool = False) -> str:
    """Bir pencereye metin yazar (Not Defteri, Word, tarayıcı arama kutusu vb.). Türkçe karakterleri destekler.
    pencere: yazılacak pencerenin adı (örn. 'not defteri', 'chrome'). Boşsa şu an öndeki pencereye yazar.
    enter_bas: yazdıktan sonra Enter'a bas (mesaj gönderir/aramayı başlatır; onay ister)."""
    if not metin:
        return "Hata: Yazılacak metin boş."
    if len(metin) > 5000:
        return "Hata: Metin çok uzun (en fazla 5000 karakter)."
    if enter_bas:
        if not izinler.onay_iste(f"'{pencere or 'öndeki pencere'}' içine yazılıp Enter'a basılacak:",
                                 metin[:500], seviye=2):
            return izinler.RED_MESAJI
    hata, baslik = _hedef_hazirla(pencere)
    if hata:
        return hata
    if _islem_adi(win32gui.GetForegroundWindow()).lower() in _TERMINAL_ISLEMLERI:
        if not izinler.onay_iste("Bir komut satırı (terminal) penceresine metin yazılacak, komut olarak çalışabilir:",
                                 metin[:500], seviye=3):
            return izinler.RED_MESAJI
    eski = _pano_oku()
    if not _pano_yaz(metin):
        return "Hata: Panoya erişilemedi, metin yazılamadı."
    try:
        _tus_gonder([0x11], ord("V"))
        time.sleep(0.2)
        if enter_bas:
            _tus_gonder([], 0x0D)
            time.sleep(0.1)
    finally:
        time.sleep(0.15)
        if eski is not None:
            _pano_yaz(eski)     # kullanıcının panosunu geri koy
    return f"'{baslik}' penceresine yazıldı ({len(metin)} karakter){' ve Enter basıldı' if enter_bas else ''}."


@tool
def panoya_yaz(metin: str) -> str:
    """Verilen metni panoya kopyalar (kullanıcı sonra istediği yere yapıştırabilir)."""
    if not metin:
        return "Hata: Metin boş."
    return f"{len(metin)} karakter panoya kopyalandı." if _pano_yaz(metin[:20000]) else "Hata: Panoya erişilemedi."


@tool
def ekran_goruntusu(bos_girdi: str = "") -> str:
    """Tüm ekranın görüntüsünü alıp çalışma alanı klasörüne PNG olarak kaydeder ve dosya yolunu söyler."""
    try:
        from PIL import ImageGrab
    except ImportError:
        return "Ekran görüntüsü için Pillow gerekli. Kullanıcıya terminalde 'pip install pillow' çalıştırmasını söyle."
    try:
        klasor = os.path.join(config.CALISMA_ALANI, "ekran_goruntuleri")
        os.makedirs(klasor, exist_ok=True)
        yol = os.path.join(klasor, datetime.now().strftime("ekran_%Y%m%d_%H%M%S.png"))
        ImageGrab.grab(all_screens=True).save(yol)
        return f"Ekran görüntüsü kaydedildi: {yol}"
    except Exception as e:
        return f"Hata: Ekran görüntüsü alınamadı: {e}"


# ============================================================
# PENCERE LİSTESİ VE PANO OKUMA
# ============================================================


@tool
def acik_pencereler(bos_girdi: str = "") -> str:
    """Şu an ekranda açık olan pencerelerin başlıklarını listeler."""
    basliklar = []

    def geri_cagri(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            baslik = win32gui.GetWindowText(hwnd).strip()
            if baslik and baslik != "Program Manager":
                basliklar.append(baslik)
        return True

    win32gui.EnumWindows(geri_cagri, None)
    return "\n".join(basliklar) if basliklar else "Açık pencere bulunamadı."


@tool
def panoyu_oku(bos_girdi: str = "") -> str:
    """Kullanıcının kopyaladığı (panodaki) metni okur."""
    try:
        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)[:3000]
            return "Panoda metin yok."
        finally:
            win32clipboard.CloseClipboard()
    except Exception as e:
        return f"Hata: {e}"


ARACLAR = [
    aktif_pencere, acik_pencereler, pencere_duzenle, masaustunu_goster, tus_bas,
    yaz, panoya_yaz, panoyu_oku, ekran_goruntusu,
]
