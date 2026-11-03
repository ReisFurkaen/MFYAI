"""
MFY AI - Depolama
Sohbet oturumlarını (chat_sessions.json) ve arayüz ayarlarını (ai_settings.json) yönetir.
Mevcut JSON dosyalarınla uyumludur, eski sohbetlerin kaybolmaz.
Arayüz kütüphanesine bağımlı değildir.
"""
import os
import json
import datetime

_DIZIN = os.path.dirname(os.path.abspath(__file__))


def _oku(yol, varsayilan):
    if os.path.exists(yol):
        try:
            with open(yol, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return varsayilan


def _yaz(yol, veri, **json_ayarlari):
    """Önce geçici dosyaya yazar, sonra yerine koyar (yarım yazılmış bozuk dosyayı önler)."""
    gecici = yol + ".tmp"
    try:
        with open(gecici, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False, **json_ayarlari)
        os.replace(gecici, yol)
        return True
    except Exception:
        return False


class OturumDeposu:
    """Sohbet geçmişi: {oturum_id: {"title": ..., "messages": [{"sender","text","is_ai"}]}}"""

    def __init__(self, yol=None):
        self.yol = yol or os.path.join(_DIZIN, "chat_sessions.json")
        veri = _oku(self.yol, {})
        self._oturumlar = veri if isinstance(veri, dict) else {}

    def _kaydet(self):
        _yaz(self.yol, self._oturumlar)   # sıkıştırılmış JSON: büyük geçmişte daha hızlı yazılır

    def var_mi(self, oturum_id) -> bool:
        return oturum_id in self._oturumlar

    def yeni_oturum(self, ilk_mesaj: str) -> str:
        oturum_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        while oturum_id in self._oturumlar:          # aynı saniyede çakışmayı önle
            oturum_id += "x"
        baslik = ilk_mesaj[:25] + "..." if len(ilk_mesaj) > 25 else ilk_mesaj
        self._oturumlar[oturum_id] = {"title": baslik, "messages": []}
        self._kaydet()
        return oturum_id

    def mesaj_ekle(self, oturum_id, gonderen: str, metin: str, ai_mi: bool):
        if oturum_id in self._oturumlar:
            self._oturumlar[oturum_id]["messages"].append(
                {"sender": gonderen, "text": metin, "is_ai": ai_mi})
            self._kaydet()

    def mesajlar(self, oturum_id) -> list:
        """Oturumun mesajlarının bir KOPYASINI döndürür."""
        return list(self._oturumlar.get(oturum_id, {}).get("messages", []))

    def baslik_al(self, oturum_id) -> str:
        return self._oturumlar.get(oturum_id, {}).get("title", "Yeni Sohbet")

    def yeniden_adlandir(self, oturum_id, yeni_baslik: str):
        if oturum_id in self._oturumlar and yeni_baslik.strip():
            self._oturumlar[oturum_id]["title"] = yeni_baslik.strip()
            self._kaydet()

    def sil(self, oturum_id):
        if oturum_id in self._oturumlar:
            del self._oturumlar[oturum_id]
            self._kaydet()

    def liste(self) -> list:
        """[(oturum_id, baslik), ...]  en yeniden en eskiye."""
        return [(oid, veri.get("title", "Yeni Sohbet"))
                for oid, veri in reversed(list(self._oturumlar.items()))]


class AyarDeposu:
    VARSAYILAN = {
        "font_size": 14,
        "appearance_mode": "light",
        "enter_gonderir": True,
        "ses_her_cevap": False,     # her cevabı sesli oku (kapalıyken yalnızca mikrofonla konuşunca okunur)
        "ses_kulaklik": False,      # kulaklık modu: asistan konuşurken araya girilebilir
        "ses_ses": "female_2",
        "ses_mikrofon": "",
        "ses_seviye": 90,
    }

    def __init__(self, yol=None):
        self.yol = yol or os.path.join(_DIZIN, "ai_settings.json")
        kayitli = _oku(self.yol, {})
        self.veri = dict(self.VARSAYILAN)
        if isinstance(kayitli, dict):
            for anahtar in self.VARSAYILAN:
                if anahtar in kayitli:
                    self.veri[anahtar] = kayitli[anahtar]

    def al(self, anahtar):
        return self.veri.get(anahtar, self.VARSAYILAN.get(anahtar))

    def toplu_kaydet(self, degerler: dict):
        for anahtar, deger in degerler.items():
            if anahtar in self.VARSAYILAN:
                self.veri[anahtar] = deger
        _yaz(self.yol, self.veri)
