"""
MFY AI - Kişisel Asistan Araçları
  BİLDİRİM    : bildirim_gonder (Windows bildirimi)
  HATIRLATICI : hatirlatici_kur ("20 dakika sonra" / "17:30'da"; program kapansa bile saklanır), hatirlaticilari_listele,
                hatirlatici_iptal. Zamanı gelince hem Windows bildirimi hem arayüz bildirimi çıkar; program kapalıyken
                geçenler açılışta "kaçırıldı" notuyla gösterilir (beyin.py açılışta hatirlaticilari_yukle() çağırır).
  HAFIZA      : hatirla, unut, profilimi_goster (kullanıcı profili, profil.json)
beyin.py bildirim_kaynagini_ayarla() ile "Öğrendim: ..." bildirimlerini arayüze bağlar.
"""

import os
import json
import uuid
import threading
import subprocess
from datetime import datetime, timedelta

from langchain.tools import tool

import config
import izinler
from izinler import sade
from hafiza import profil, hassas_mi


# ============================================================
# BİLDİRİM VE HATIRLATICILAR
# ============================================================


_NOWINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


DOSYA = os.path.join(config.PROJE_DIZINI, "hatirlaticilar.json")


MAKS_HATIRLATICI = 50


MAKS_GUN = 30


_kilit = threading.RLock()


_zamanlayicilar = {}


def windows_bildirimi(baslik: str, mesaj: str) -> bool:
    betik = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null; "
        "$x = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
        "$t = $x.GetElementsByTagName('text'); "
        "$t.Item(0).AppendChild($x.CreateTextNode($env:MFY_BASLIK)) | Out-Null; "
        "$t.Item(1).AppendChild($x.CreateTextNode($env:MFY_MESAJ)) | Out-Null; "
        "$n = [Windows.UI.Notifications.ToastNotification]::new($x); "
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
        "'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe').Show($n)"
    )
    try:
        env = dict(os.environ, MFY_BASLIK=baslik[:100], MFY_MESAJ=mesaj[:250])
        sonuc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", betik],
                               env=env, capture_output=True, timeout=20, creationflags=_NOWINDOW)
        return sonuc.returncode == 0
    except Exception:
        return False


@tool
def bildirim_gonder(baslik: str, mesaj: str) -> str:
    """Windows bildirimi gönderir (ekranın sağ altında çıkan bildirim)."""
    if not (mesaj or "").strip():
        return "Hata: Bildirim mesajı boş."
    if windows_bildirimi((baslik or "MFY AI").strip(), mesaj.strip()):
        return "Windows bildirimi gönderildi."
    return "Windows bildirimi gönderilemedi (Windows'ta Rahatsız Etmeyin/Odak modu açık olabilir)."


def _oku() -> list:
    try:
        with open(DOSYA, "r", encoding="utf-8") as f:
            veri = json.load(f)
        return veri if isinstance(veri, list) else []
    except (OSError, ValueError):
        return []


def _yaz(veri: list):
    gecici = DOSYA + ".tmp"
    try:
        with open(gecici, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False, indent=2)
        os.replace(gecici, DOSYA)
    except OSError:
        pass


def _tetikle(hid: str, kacirildi: bool = False):
    with _kilit:
        kayitlar = _oku()
        kayit = next((k for k in kayitlar if k.get("id") == hid), None)
        _yaz([k for k in kayitlar if k.get("id") != hid])
        _zamanlayicilar.pop(hid, None)
    if not kayit:
        return
    metin = ("(Kaçırıldı) " if kacirildi else "") + f"Hatırlatma: {kayit['mesaj']}"
    izinler.bildir(metin)
    windows_bildirimi("MFY AI - Hatırlatma", metin)


def _planla(kayit: dict):
    try:
        saniye = (datetime.fromisoformat(kayit["zaman"]) - datetime.now()).total_seconds()
    except (ValueError, KeyError):
        return
    kacirildi = saniye < -30
    zamanlayici = threading.Timer(max(0.0, saniye), _tetikle, args=(kayit["id"], kacirildi))
    zamanlayici.daemon = True
    zamanlayici.start()
    _zamanlayicilar[kayit["id"]] = zamanlayici


def hatirlaticilari_yukle() -> int:
    """Program açılırken çağrılır: kayıtlı hatırlatıcıları yeniden kurar."""
    with _kilit:
        kayitlar = _oku()
        for k in kayitlar:
            _planla(k)
        return len(kayitlar)


def _zaman_coz(dakika_sonra, saat: str):
    """(hedef_zaman, hata). 'saat' HH:MM biçimindedir; geçmişse yarına kurulur."""
    simdi = datetime.now()
    saat = (saat or "").strip()
    if saat:
        try:
            ss, dd = saat.replace(".", ":").split(":")[:2]
            hedef = simdi.replace(hour=int(ss), minute=int(dd), second=0, microsecond=0)
        except (ValueError, IndexError):
            return None, "Saat 'SS:DD' biçiminde olmalı (örn. 17:30)."
        if hedef <= simdi:
            hedef += timedelta(days=1)
        return hedef, None
    try:
        dakika = float(dakika_sonra)
    except (TypeError, ValueError):
        dakika = 0
    if dakika <= 0:
        return None, "Ne zaman hatırlatılacağını belirt: dakika_sonra (örn. 20) ya da saat (örn. 17:30)."
    return simdi + timedelta(minutes=dakika), None


@tool
def hatirlatici_kur(mesaj: str, dakika_sonra: float = 0, saat: str = "") -> str:
    """Hatırlatıcı kurar. mesaj: ne hatırlatılacak. Zamanı iki yoldan biriyle ver: dakika_sonra (örn. 20 → 20 dakika sonra)
    VEYA saat ('SS:DD' biçiminde, örn. '17:30'; geçmişse yarına kurulur). Saati hesaplamak için önce get_time aracını kullanabilirsin."""
    mesaj = (mesaj or "").strip()
    if not mesaj:
        return "Hata: Neyin hatırlatılacağı belirtilmedi."
    hedef, hata = _zaman_coz(dakika_sonra, saat)
    if hata:
        return f"Hata: {hata}"
    if hedef - datetime.now() > timedelta(days=MAKS_GUN):
        return f"En fazla {MAKS_GUN} gün sonrasına hatırlatıcı kurulabilir."
    with _kilit:
        kayitlar = _oku()
        if len(kayitlar) >= MAKS_HATIRLATICI:
            return "Çok fazla bekleyen hatırlatıcı var, önce bazılarını iptal etmek gerekiyor."
        kayit = {"id": uuid.uuid4().hex[:6], "zaman": hedef.isoformat(timespec="seconds"), "mesaj": mesaj[:200]}
        kayitlar.append(kayit)
        _yaz(kayitlar)
        _planla(kayit)
    return f"Hatırlatıcı kuruldu: {hedef.strftime('%d.%m.%Y %H:%M')} → {mesaj}"


@tool
def hatirlaticilari_listele(bos_girdi: str = "") -> str:
    """Bekleyen tüm hatırlatıcıları listeler."""
    with _kilit:
        kayitlar = sorted(_oku(), key=lambda k: k.get("zaman", ""))
    if not kayitlar:
        return "Bekleyen hatırlatıcı yok."
    satirlar = []
    for k in kayitlar:
        try:
            zaman = datetime.fromisoformat(k["zaman"]).strftime("%d.%m.%Y %H:%M")
        except (ValueError, KeyError):
            zaman = "?"
        satirlar.append(f"- [{k.get('id')}] {zaman}: {k.get('mesaj')}")
    return "\n".join(satirlar)


@tool
def hatirlatici_iptal(kelime_veya_id: str) -> str:
    """Bir hatırlatıcıyı iptal eder. kelime_veya_id: hatırlatıcının numarası ya da mesajından bir kelime ('hepsi' yazılırsa tümü iptal edilir)."""
    hedef = sade(kelime_veya_id).strip()
    if not hedef:
        return "Hata: Hangi hatırlatıcının iptal edileceğini belirt."
    with _kilit:
        kayitlar = _oku()
        if hedef in ("hepsi", "tumu", "hepsini"):
            silinecek = list(kayitlar)
        else:
            silinecek = [k for k in kayitlar if k.get("id") == hedef or hedef in sade(k.get("mesaj", ""))]
        if not silinecek:
            return f"'{kelime_veya_id}' ile eşleşen hatırlatıcı bulunamadı."
        if len(silinecek) > 3 and hedef not in ("hepsi", "tumu", "hepsini"):
            return "Çok fazla eşleşme var, daha belirgin bir kelime ya da numara belirt."
        idler = {k["id"] for k in silinecek}
        for hid in idler:
            z = _zamanlayicilar.pop(hid, None)
            if z:
                z.cancel()
        _yaz([k for k in kayitlar if k.get("id") not in idler])
    return f"{len(silinecek)} hatırlatıcı iptal edildi: " + "; ".join(k.get("mesaj", "") for k in silinecek)


# ============================================================
# KULLANICI PROFİLİ (HAFIZA)
# ============================================================


# beyin.py burayı bildirim sistemine bağlar (arayüzde "Öğrendim: ..." bildirimi göstermek için)
_bildirim_kaynagi = lambda metin: None


def bildirim_kaynagini_ayarla(fonksiyon):
    global _bildirim_kaynagi
    _bildirim_kaynagi = fonksiyon


@tool
def hatirla(konu: str, bilgi: str) -> str:
    """Kullanıcı hakkında KALICI bir bilgiyi hafızaya kaydeder. konu: kısa başlık (örn. 'yaşadığı şehir', 'favori takım'),
    bilgi: değeri (örn. 'İstanbul'). Kullanıcı 'bunu hatırla' dediğinde ya da kendisi hakkında kalıcı bir şey söylediğinde kullan."""
    if hassas_mi(f"{konu} {bilgi}"):
        return "Şifre, anahtar, kart numarası gibi hassas bilgileri saklamam. Bunu kullanıcıya nazikçe söyle."
    sonuc = profil.ekle(konu, bilgi, kaynak="kullanici")
    if sonuc == "gecersiz":
        return "Bilgi kaydedilemedi: konu ve bilgi boş olamaz ve çok uzun olmamalı."
    if sonuc == "dolu":
        return "Hafıza dolu, önce bazı bilgileri silmek gerekiyor."
    if sonuc == "ayni":
        return f"Bu bilgiyi zaten biliyordum: {konu} = {bilgi}"
    _bildirim_kaynagi(f"{'Güncelledim' if sonuc == 'guncellendi' else 'Öğrendim'}: {konu} → {bilgi}")
    return f"Kaydedildi ({sonuc}): {konu} = {bilgi}"


@tool
def unut(konu: str) -> str:
    """Hafızadaki bir kullanıcı bilgisini siler. konu: unutulacak bilginin başlığı ya da içinden bir kelime."""
    adaylar = profil.ara(konu)
    if not adaylar:
        return f"'{konu}' ile eşleşen bir bilgi bulamadım."
    if len(adaylar) > 3:
        liste = ", ".join(k["konu"] for k in adaylar[:8])
        return f"Çok fazla eşleşme var ({liste}). Kullanıcıdan hangisini unutmam gerektiğini netleştirmesini iste."
    for k in adaylar:
        profil.sil(k["anahtar"])
    silinen = ", ".join(f"{k['konu']} = {k['bilgi']}" for k in adaylar)
    _bildirim_kaynagi(f"Unuttum: {silinen}")
    return f"Unutuldu: {silinen}"


@tool
def profilimi_goster(bos_girdi: str = "") -> str:
    """Kullanıcı hakkında hafızada kayıtlı olan tüm bilgileri listeler."""
    metin = profil.metin(3000)
    return metin if metin else "Henüz kullanıcı hakkında kayıtlı bir bilgi yok."


ARACLAR = [
    bildirim_gonder, hatirlatici_kur, hatirlaticilari_listele, hatirlatici_iptal, hatirla,
    unut, profilimi_goster,
]
