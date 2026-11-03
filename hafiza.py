"""
MFY AI - Hafıza Yardımcıları
  * ProfilDeposu : Kullanıcı hakkında KALICI bilgiler (profil.json). İnsan okuyabilir, elle de düzenlenebilir.
  * Filtreler    : Başarısız / yanıltıcı sohbet kayıtlarının uzun süreli hafızaya girmesini engeller.
  * Çıkarma      : Sohbetten kullanıcı bilgisi çıkarmak için yardımcılar.

Bu dosya bilerek HAFİFTİR (langchain gerektirmez): arayüz de doğrudan kullanabilir.
"""
import os
import re
import json
import threading
from datetime import datetime

import config

# ------------------------------------------------------------
# Metin sadeleştirme (Türkçe karakterler -> ASCII, küçük harf)
# ------------------------------------------------------------
_TR_TABLO = str.maketrans({
    "ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g", "ı": "i", "İ": "i", "I": "i",
    "ö": "o", "Ö": "o", "ş": "s", "Ş": "s", "ü": "u", "Ü": "u",
})


def sade(metin: str) -> str:
    return (metin or "").translate(_TR_TABLO).lower()


def anahtar_uret(konu: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", sade(konu)).strip("_")


# ------------------------------------------------------------
# Hassas bilgi koruması: bunlar asla kaydedilmez
# ------------------------------------------------------------
_HASSAS = [
    "sifre", "parola", "password", "api key", "apikey", "api anahtar", "token", "secret",
    "gizli anahtar", "kredi kart", "kart numara", "cvv", "tc kimlik", "kimlik numara", "iban", "pin kod",
]


def hassas_mi(metin: str) -> bool:
    s = sade(metin)
    return any(k in s for k in _HASSAS)


# ------------------------------------------------------------
# PROFİL DEPOSU
# ------------------------------------------------------------
class ProfilDeposu:
    """[{"anahtar","konu","bilgi","zaman","kaynak"}] listesini profil.json'da tutar."""
    MAKS_KAYIT = 200

    def __init__(self, yol=None):
        self.yol = yol or os.path.join(config.PROJE_DIZINI, "profil.json")
        self._kilit = threading.RLock()

    def _oku(self) -> list:
        try:
            with open(self.yol, "r", encoding="utf-8") as f:
                veri = json.load(f)
            return veri if isinstance(veri, list) else []
        except (OSError, ValueError):
            return []

    def _yaz(self, veri: list):
        gecici = self.yol + ".tmp"
        try:
            with open(gecici, "w", encoding="utf-8") as f:
                json.dump(veri, f, ensure_ascii=False, indent=2)
            os.replace(gecici, self.yol)
        except OSError:
            pass

    def tumu(self) -> list:
        with self._kilit:
            return self._oku()

    def ekle(self, konu: str, bilgi: str, kaynak: str = "otomatik") -> str:
        """Döner: 'eklendi' | 'guncellendi' | 'ayni' | 'gecersiz' | 'dolu'"""
        konu, bilgi = (konu or "").strip(), (bilgi or "").strip()
        anahtar = anahtar_uret(konu)
        if not anahtar or not (2 <= len(konu) <= 60) or not (1 <= len(bilgi) <= 300):
            return "gecersiz"
        with self._kilit:
            veri = self._oku()
            simdi = datetime.now().strftime("%Y-%m-%d %H:%M")
            for kayit in veri:
                if kayit.get("anahtar") == anahtar:
                    if sade(kayit.get("bilgi", "")).strip() == sade(bilgi).strip():
                        return "ayni"
                    kayit.update({"konu": konu, "bilgi": bilgi, "zaman": simdi, "kaynak": kaynak})
                    self._yaz(veri)
                    return "guncellendi"
            if len(veri) >= self.MAKS_KAYIT:
                return "dolu"
            veri.append({"anahtar": anahtar, "konu": konu, "bilgi": bilgi, "zaman": simdi, "kaynak": kaynak})
            self._yaz(veri)
            return "eklendi"

    def sil(self, anahtar: str) -> bool:
        with self._kilit:
            veri = self._oku()
            yeni = [k for k in veri if k.get("anahtar") != anahtar]
            if len(yeni) == len(veri):
                return False
            self._yaz(yeni)
            return True

    def ara(self, kelime: str) -> list:
        """Konu adıyla birebir ya da konu/bilgi içinde geçen kayıtları bulur."""
        anahtar = anahtar_uret(kelime)
        s = sade(kelime).strip()
        with self._kilit:
            veri = self._oku()
        tam = [k for k in veri if k.get("anahtar") == anahtar]
        if tam:
            return tam
        if not s:
            return []
        return [k for k in veri if s in k.get("anahtar", "").replace("_", " ") or s in sade(k.get("bilgi", ""))]

    def metin(self, maks_karakter: int = 1500) -> str:
        """Modelin prompt'una konacak profil metni (en yeni bilgiler önceliklidir)."""
        veri = self.tumu()
        satirlar, toplam = [], 0
        for k in reversed(veri):
            satir = f"- {k.get('konu', '?')}: {k.get('bilgi', '')}"
            if toplam + len(satir) > maks_karakter:
                break
            satirlar.append(satir)
            toplam += len(satir) + 1
        return "\n".join(reversed(satirlar))


profil = ProfilDeposu()   # tüm program bu tek örneği paylaşır

# ------------------------------------------------------------
# SOHBET KAYDI FİLTRELERİ (uzun süreli hafızayı zehirlemesin)
# ------------------------------------------------------------
_RED_KALIPLARI = [
    "kontrol edemiyorum", "yapamiyorum", "yapamam", "erisemiyorum", "ozel bir arac gerek",
    "yeteneklerim", "hangisini tercih edersiniz", "acamiyorum", "ulasamiyorum", "kullanamiyorum",
    "<tool_call>", "dosya bulunamadi", "uzgunum, su anda", "su anda yapamiyorum", "bilmiyorum",
    "veremeyebilirim", "kisisel bilgileri bilmiyorum",
]
_YETENEK_SORULARI = ["neler yapabilirsin", "yeteneklerin", "kullanabildigin", "hangi araclar"]


def kotu_icerik_mi(metin: str) -> bool:
    """Metin parçası bir 'yapamıyorum / bilmiyorum / ham araç çağrısı' içeriyor mu?"""
    s = sade(metin)
    return any(k in s for k in _RED_KALIPLARI)


def kotu_kayit_mu(kullanici_mesaji: str, asistan_cevabi: str):
    """Uzun süreli hafızaya KAYDEDİLMEMESİ gereken bir konuşma mı? Nedenini döndürür, iyiyse None."""
    cevap_s = sade(asistan_cevabi)
    mesaj_s = sade(kullanici_mesaji)
    if len(mesaj_s.strip()) < 5:
        return "çok kısa mesaj"
    if cevap_s.startswith("hata") or cevap_s.startswith("**hata"):
        return "hata cevabı"
    if kotu_icerik_mi(asistan_cevabi):
        return "yetersizlik / ret cevabı"
    if any(k in mesaj_s for k in _YETENEK_SORULARI) or ("arac" in mesaj_s and "listele" in mesaj_s):
        return "yetenek listesi (güncelliğini yitirir)"
    return None


def kayit_ayir(birlesik_metin: str):
    """'Kullanıcı: ...\\nAsistan: ...' biçimindeki kaydı (kullanıcı, asistan) olarak ayırır."""
    metin = birlesik_metin or ""
    isaret = "\nAsistan:"
    if isaret in metin:
        kullanici, asistan = metin.split(isaret, 1)
        return kullanici.replace("Kullanıcı:", "", 1).strip(), asistan.strip()
    return "", metin.strip()


# ------------------------------------------------------------
# SOHBETTEN KULLANICI BİLGİSİ ÇIKARMA
# ------------------------------------------------------------
_OZELLIK_IPUCLARI = [
    " ben ", " benim ", " bana ", "adim", "ismim", "yasiyorum", "calisiyorum", "kullaniyorum", "seviyorum",
    "sevmiyorum", "hoslaniyorum", "tutuyorum", "dogdum", "dogumlu", "yasindayim", "okuyorum", "evliyim",
    "kedim", "kopegim", "projem", "hedefim", "aliskanlig", "genelde", "hatirla", "unutma", "bundan sonra",
    "tercih", "favori", "bilgisayarim", "telefonum", "mezun", "ogrenciyim", "mesleg",
]


def ogrenilebilir_mi(mesaj: str) -> bool:
    """Mesajda kullanıcı hakkında kalıcı bilgi olma ihtimali var mı? (Gereksiz model çağrısını önler.)"""
    temiz = sade(mesaj).strip()
    if len(temiz) < 12:
        return False
    acik_istek = any(k in temiz for k in ("hatirla", "unutma", "bundan sonra"))
    ilk_kelime = temiz.split()[0] if temiz.split() else ""
    soru_mu = temiz.endswith("?") or ilk_kelime in ("kac", "nasil", "neden", "nerede", "kim", "hangi", "ne", "nedir")
    if soru_mu and not acik_istek:
        return False   # sorular kullanıcı hakkında bilgi vermez
    s = " " + temiz + " "
    return any(ip in s for ip in _OZELLIK_IPUCLARI)


def cikarma_istemi(mevcut_profil: str, dusunme_kapat: bool = False) -> str:
    return (
        ("/no_think\n" if dusunme_kapat else "") +
        "Sen bir bilgi çıkarma aracısın. Kullanıcının mesajından, kullanıcının KENDİSİ HAKKINDAKİ uzun süre "
        "geçerli kalacak somut bilgileri çıkar: ad, yaşadığı yer, mesleği/okulu, kullandığı program ve donanımlar, "
        "hobileri, tercihleri, alışkanlıkları, projeleri, aile ve evcil hayvanları.\n"
        "ASLA çıkarma: geçici durumlar ('şu an şunu yapıyorum'), komutlar, sorular, genel bilgi, asistanla ilgili şeyler.\n"
        "ASLA çıkarma: şifre, parola, API anahtarı, kart/kimlik numarası gibi gizli bilgiler.\n"
        "Aynı konuda bilgi zaten varsa AYNI konu adını kullan (böylece güncellenir).\n\n"
        "Mevcut profil:\n" + (mevcut_profil or "(boş)") + "\n\n"
        'Cevabın SADECE şu biçimde bir JSON olsun, başka hiçbir şey yazma:\n'
        '{"bilgiler":[{"konu":"yaşadığı şehir","bilgi":"İstanbul"}]}\n'
        'Çıkarılacak bir şey yoksa: {"bilgiler":[]}'
    )


def json_ayikla(model_cevabi: str) -> list:
    """Modelin cevabından [(konu, bilgi), ...] listesini güvenle çıkarır."""
    temiz = re.sub(r"<think>.*?</think>", "", model_cevabi or "", flags=re.DOTALL)
    temiz = temiz.replace("```json", "").replace("```", "")
    bas, son = temiz.find("{"), temiz.rfind("}")
    if bas < 0 or son <= bas:
        return []
    try:
        veri = json.loads(temiz[bas:son + 1])
    except ValueError:
        return []
    liste = veri.get("bilgiler") if isinstance(veri, dict) else None
    if not isinstance(liste, list):
        return []
    sonuc = []
    for oge in liste:
        if isinstance(oge, dict):
            konu, bilgi = str(oge.get("konu", "")).strip(), str(oge.get("bilgi", "")).strip()
            if konu and bilgi:
                sonuc.append((konu, bilgi))
    return sonuc[:5]
