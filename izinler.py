"""
MFY AI - İzin ve Güvenlik Katmanı
Bilgisayarı kontrol eden TÜM araçlar buradaki kuralları kullanır.

ONAY SEVİYELERİ
  0  Okuma / sorgulama                  -> asla sormaz
  1  Güvenli ve geri alınabilir eylem   -> yalnızca "sıkı" modda sorar
  2  Sonuçları olan eylem               -> "sıkı" ve "dengeli" modda sorar
  3  Geri alınamaz / sistemi etkileyen  -> HER modda sorar (silme, kapatma, komut çalıştırma, güç işlemleri)

GÜVEN MODU (config.py içinde  GUVEN_MODU = "siki" | "dengeli" | "rahat",  varsayılan "dengeli")

Ek korumalar: yazma/silme yalnızca kullanıcı klasörü içinde, sistem ve proje klasörleri korunur,
çalıştırılabilir dosya türleri engellenir, her araç çağrısı audit_log.jsonl dosyasına kaydedilir.
"""
import os
import re
import json
import time
import threading
import functools
from datetime import datetime

import config

GUVEN_MODU = str(getattr(config, "GUVEN_MODU", "dengeli")).lower()
if GUVEN_MODU not in ("siki", "dengeli", "rahat", "sinirsiz"):
    GUVEN_MODU = "dengeli"

# "sinirsiz": hiçbir onay sorulmaz; yol, dosya türü ve komut engelleri uygulanmaz (TAM YETKİ).
# Etkinlik günlüğü (audit_log.jsonl) ve acil durdurma yine çalışır.
SINIRSIZ = GUVEN_MODU == "sinirsiz"

EV = os.path.abspath(os.path.expanduser("~"))
PROJE = os.path.abspath(config.PROJE_DIZINI)
LOG_YOLU = os.path.join(PROJE, "audit_log.jsonl")

RED_MESAJI = ("Kullanıcı bu işlemi REDDETTİ. İşlem YAPILMADI; bunu kullanıcıya bildir ve ısrar etme.")

# ------------------------------------------------------------
# Metin yardımcıları
# ------------------------------------------------------------
_TR_TABLO = str.maketrans({
    "ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g", "ı": "i", "İ": "i", "I": "i",
    "ö": "o", "Ö": "o", "ş": "s", "Ş": "s", "ü": "u", "Ü": "u",
})


def sade(metin: str) -> str:
    return (metin or "").translate(_TR_TABLO).lower()


# ------------------------------------------------------------
# Onay ve bildirim bağlantıları (beyin.py bunları arayüze bağlar)
# ------------------------------------------------------------
_onay_kaynagi = lambda aciklama: False
_bildirim_kaynagi = lambda metin: print(f"🔔 {metin}")


def onay_kaynagini_ayarla(fonksiyon):
    global _onay_kaynagi
    _onay_kaynagi = fonksiyon


def bildirim_kaynagini_ayarla(fonksiyon):
    global _bildirim_kaynagi
    _bildirim_kaynagi = fonksiyon


def bildir(metin: str):
    try:
        _bildirim_kaynagi(metin)
    except Exception:
        pass


def onay_gerekli_mi(seviye: int) -> bool:
    if SINIRSIZ:
        return False
    if seviye >= 3:
        return True
    if seviye == 2:
        return GUVEN_MODU in ("siki", "dengeli")
    if seviye == 1:
        return GUVEN_MODU == "siki"
    return False


def onay_iste(baslik: str, ayrintilar: str = "", seviye: int = 2) -> bool:
    """Seviyeye ve güven moduna göre kullanıcıya sorar. True: devam edilebilir."""
    if not onay_gerekli_mi(seviye):
        return True
    uyari = "\n\n⚠️ Bu işlem geri alınamayabilir veya sistemi etkileyebilir." if seviye >= 3 else ""
    return bool(_onay_kaynagi(f"{baslik}\n\n{ayrintilar}".strip() + uyari))


# ------------------------------------------------------------
# Yol politikası
# ------------------------------------------------------------
CALISTIRILABILIR_UZANTILAR = {
    ".exe", ".bat", ".cmd", ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".scr", ".msi",
    ".lnk", ".reg", ".dll", ".com", ".pif", ".hta", ".cpl", ".jar",
}

_KLASOR_ADLARI = {
    "masaustu": ("B4BFCC3A-DB2C-424C-B029-7FE99A87C641", ["Desktop", os.path.join("OneDrive", "Desktop"), os.path.join("OneDrive", "Masaüstü")]),
    "desktop": ("B4BFCC3A-DB2C-424C-B029-7FE99A87C641", ["Desktop", os.path.join("OneDrive", "Desktop")]),
    "indirilenler": ("374DE290-123F-4565-9164-39C4925E467B", ["Downloads"]),
    "indirmeler": ("374DE290-123F-4565-9164-39C4925E467B", ["Downloads"]),
    "downloads": ("374DE290-123F-4565-9164-39C4925E467B", ["Downloads"]),
    "belgeler": ("FDD39AD0-238F-46AF-ADB4-6C85480369C7", ["Documents", os.path.join("OneDrive", "Documents"), os.path.join("OneDrive", "Belgeler")]),
    "documents": ("FDD39AD0-238F-46AF-ADB4-6C85480369C7", ["Documents", os.path.join("OneDrive", "Documents")]),
    "resimler": ("33E28130-4E1E-4676-835A-98395C3BC3BB", ["Pictures", os.path.join("OneDrive", "Pictures"), os.path.join("OneDrive", "Resimler")]),
    "pictures": ("33E28130-4E1E-4676-835A-98395C3BC3BB", ["Pictures", os.path.join("OneDrive", "Pictures")]),
    "muzik": ("4BD8D571-6D19-48D3-BE97-422220080E43", ["Music"]),
    "videolar": ("18989B1D-99B5-455B-841C-AB7C74E4DDFC", ["Videos"]),
}


def _bilinen_klasor_api(guid_metni: str):
    """Windows'a gerçek klasör yolunu sorar (OneDrive yönlendirmesini de doğru verir)."""
    try:
        import ctypes
        import uuid
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                        ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

        u = uuid.UUID(guid_metni)
        g = GUID(u.time_low, u.time_mid, u.time_hi_version, (ctypes.c_ubyte * 8)(*u.bytes[8:]))
        isaretci = ctypes.c_wchar_p()
        sonuc = ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(isaretci))
        if sonuc != 0:
            return None
        return isaretci.value
    except Exception:
        return None


def bilinen_klasor(ad: str):
    """'masaüstü', 'indirilenler' gibi adları gerçek klasör yoluna çevirir; bilinmiyorsa None."""
    anahtar = sade(ad).strip()
    kayit = _KLASOR_ADLARI.get(anahtar)
    if not kayit:
        return None
    guid, adaylar = kayit
    yol = _bilinen_klasor_api(guid)
    if yol and os.path.isdir(yol):
        return yol
    for alt in adaylar:
        aday = os.path.join(EV, alt)
        if os.path.isdir(aday):
            return aday
    return None


def yol_coz(yol: str) -> str:
    """Kullanıcının/modelin verdiği yolu tam yola çevirir ('masaüstü/not.txt', '~', %USERPROFILE% desteklenir)."""
    yol = (yol or "").strip().strip('"').strip("'")
    parcalar = re.split(r"[\\/]", yol, maxsplit=1)
    ilk = parcalar[0]
    if ilk:
        s_ilk = sade(ilk)
        for anahtar in _KLASOR_ADLARI:
            if s_ilk == anahtar or (s_ilk.startswith(anahtar) and len(s_ilk) <= len(anahtar) + 4):
                klasor = bilinen_klasor(anahtar)
                if klasor:
                    yol = os.path.join(klasor, parcalar[1]) if len(parcalar) > 1 and parcalar[1] else klasor
                break
    return os.path.abspath(os.path.expandvars(os.path.expanduser(yol)))


def altinda_mi(yol: str, kok: str) -> bool:
    try:
        return os.path.commonpath([os.path.abspath(yol), os.path.abspath(kok)]) == os.path.abspath(kok)
    except ValueError:
        return False


def _korunan_dizinler() -> list:
    adaylar = [
        os.environ.get("WINDIR"), os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
        os.environ.get("ProgramData"), PROJE, os.path.join(EV, ".ssh"), os.path.join(EV, "AppData"),
    ]
    return [os.path.abspath(a) for a in adaylar if a]


def kutuphane_koku_mu(yol: str) -> bool:
    """Masaüstü, Belgeler, İndirilenler gibi klasörlerin KENDİSİ mi? (silinemez / taşınamaz)"""
    yol = os.path.abspath(yol)
    for ad in ("masaustu", "indirilenler", "belgeler", "resimler", "muzik", "videolar"):
        k = bilinen_klasor(ad)
        if k and os.path.abspath(k) == yol:
            return True
    return False


def degisiklige_acik_mi(yol: str):
    """(izin_var_mi, neden). Yazma/silme/taşıma için yolun güvenli olup olmadığını denetler."""
    if SINIRSIZ:
        return True, ""
    yol = os.path.abspath(yol)
    if not altinda_mi(yol, EV):
        return False, "Yalnızca kullanıcı klasörü içinde değişiklik yapılabilir."
    if yol == EV:
        return False, "Kullanıcı klasörünün kendisi değiştirilemez."
    for k in _korunan_dizinler():
        if altinda_mi(yol, k) or altinda_mi(k, yol):
            return False, "Bu konum sistem ya da asistanın kendi dosyalarını içeriyor, korunuyor."
    return True, ""


def calistirilabilir_mi(yol: str) -> bool:
    return os.path.splitext(yol)[1].lower() in CALISTIRILABILIR_UZANTILAR


# ------------------------------------------------------------
# Etkinlik günlüğü (audit log)
# ------------------------------------------------------------
_log_kilidi = threading.Lock()


def kaydet(arac: str, argumanlar, sonuc=None, hata=None, sure: float = 0.0):
    satir = {
        "zaman": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "arac": arac,
        "arguman": {k: str(v)[:200] for k, v in argumanlar.items()} if isinstance(argumanlar, dict) else str(argumanlar)[:200],
        "sonuc": None if sonuc is None else str(sonuc)[:300],
        "hata": hata,
        "sure_ms": int(sure * 1000),
    }
    with _log_kilidi:
        try:
            if os.path.exists(LOG_YOLU) and os.path.getsize(LOG_YOLU) > 5 * 1024 * 1024:
                os.replace(LOG_YOLU, LOG_YOLU + ".1")
            with open(LOG_YOLU, "a", encoding="utf-8") as f:
                f.write(json.dumps(satir, ensure_ascii=False) + "\n")
        except OSError:
            pass


def izlemeli(fonksiyon, ad: str):
    """Bir aracın her çağrısını (ne zaman, hangi parametreyle, ne sonuç) günlüğe yazan sarmalayıcı."""
    @functools.wraps(fonksiyon)
    def sarmal(*args, **kwargs):
        baslangic = time.time()
        sonuc, hata = None, None
        try:
            sonuc = fonksiyon(*args, **kwargs)
            return sonuc
        except Exception as e:
            hata = repr(e)
            raise
        finally:
            kaydet(ad, kwargs if kwargs else {"args": args}, sonuc, hata, time.time() - baslangic)
    sarmal._izlemeli = True
    return sarmal


def araclari_izle(araclar: list) -> int:
    """Tüm araçlara günlük kaydı ekler. Kaç aracın izlendiğini döndürür."""
    sayac = 0
    for arac in araclar:
        f = getattr(arac, "func", None)
        if f is None or getattr(f, "_izlemeli", False):
            continue
        try:
            arac.func = izlemeli(f, arac.name)
            sayac += 1
        except Exception:
            pass
    return sayac
