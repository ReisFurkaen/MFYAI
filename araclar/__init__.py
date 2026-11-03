"""
MFY AI - Araçlar paketi

Her dosya bir konuyu kapsar ve sonunda ARACLAR = [...] listesi tanımlar:
  sistem.py         Donanım, pil, disk, ağ, güç, hizmetler, kayıt defteri, WMI, olay günlüğü, zamanlanmış görevler
  programlar.py     Uygulama açma, kurulu programlar, işlemler, PowerShell, Python, hesap makinesi
  dosyalar.py       Dosya/klasör okuma, yazma, arama, taşıma, silme, arşiv, belge okuma, SQLite
  pencere_girdi.py  Pencere yönetimi, klavye, pano, ekran görüntüsü
  ekran_ajan.py     Ekranı görme, fare, UI Automation (PC ajanı)
  web_ag.py         Site/YouTube/Spotify, web arama, HTTP, Vikipedi, indirme, ping/port/DNS
  medya.py          Ses (genel ve uygulama başına), medya tuşları, kayıt, ses<->yazı, görsel işleme
  kisisel.py        Bildirim, hatırlatıcı, kullanıcı profili (hafıza araçları)
  ortak.py          Dosyaların ortak kullandığı yardımcılar (araç içermez)

Yeni araç eklemek: ilgili dosyaya @tool fonksiyonunu yaz ve dosyanın sonundaki ARACLAR listesine ekle.
Yeni bir konu dosyası açmak: bu klasöre yeni .py ekle ve içinde ARACLAR = [...] tanımla; otomatik bulunur.
Sonra arac_secici.py'deki ilgili gruba aracın adını yaz. (beyin.py'ye dokunmak gerekmez.)

Kontrol:  python -m araclar     (hangi dosyada hangi araçlar var, yüklenemeyen / çakışan var mı)
"""
import importlib
import pkgutil

_ATLA = {"ortak"}

# modül adı -> o modülden yüklenen araç adları (python -m araclar ve beyin.py bunu gösterir)
YUKLEME_OZETI: dict = {}
HATALAR: dict = {}


def araclari_yukle() -> list:
    """Paketteki tüm araç dosyalarını yükler. Bir dosya yüklenemezse yalnızca o dosyanın araçları devre dışı kalır."""
    YUKLEME_OZETI.clear()
    HATALAR.clear()
    tum, sahip = {}, {}
    for bilgi in sorted(pkgutil.iter_modules(__path__), key=lambda b: b.name):
        ad = bilgi.name
        if ad.startswith("_") or ad in _ATLA:
            continue
        try:
            modul = importlib.import_module(f"{__name__}.{ad}")
            liste = list(getattr(modul, "ARACLAR"))
        except Exception as e:
            HATALAR[ad] = f"{type(e).__name__}: {e}"
            print(f"⚠️ araclar.{ad} yüklenemedi, bu dosyadaki araçlar devre dışı: {type(e).__name__}: {e}")
            continue
        YUKLEME_OZETI[ad] = [t.name for t in liste]
        for t in liste:
            if t.name in tum:
                print(f"⚠️ Aynı adlı araç iki dosyada var: {t.name} ({sahip[t.name]} ve {ad}); sonrakisi kullanılıyor.")
            tum[t.name] = t
            sahip[t.name] = ad
    return list(tum.values())
