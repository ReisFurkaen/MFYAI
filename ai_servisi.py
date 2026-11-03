"""
MFY AI - Yapay Zeka Servisi
Arayüz ile beyin.py arasındaki köprü. Hiçbir arayüz kütüphanesine (Qt, tkinter) bağımlı
DEĞİLDİR; bu yüzden ileride ses arayüzü, Telegram botu vb. aynı servisi kullanabilir.

Arayüzün bilmesi gereken tek şey:
    servis = AIServisi()
    servis.onay_fonksiyonu_ayarla(fonksiyon)        # onay penceresi (True/False döndürür)
    servis.yukle(on_hazir, on_hata)                 # arka planda yükler
    servis.sor(mesaj, gecmis, on_token, on_cevap, on_hata)

Dikkat: on_hazir / on_hata / on_token / on_cevap fonksiyonları ARKA PLAN thread'inden çağrılır.
Arayüz bunları kendi ana thread'ine aktarmaktan sorumludur.
"""
import re
import threading
import traceback

from langchain_core.callbacks import BaseCallbackHandler

# Qwen3 gibi modellerin ürettiği <think>...</think> blokları kullanıcıya gösterilmez
_THINK_TAMAM = re.compile(r"<think>.*?</think>", re.DOTALL)
_THINK_ACIK = re.compile(r"<think>.*$", re.DOTALL)
# Modelin düz metin olarak yazdığı araç çağrıları da kullanıcıya gösterilmez
_ARAC_TAMAM = re.compile(r"<tool_call>.*?</tool_call>", re.DOTALL)
_ARAC_ACIK = re.compile(r"<tool_call>.*$", re.DOTALL)
# Sesli konuşma için kullanılan duygu etiketleri ekranda görünmez: [mutlu], [üzgün] ...
_DUYGU_ETIKETI = re.compile(r"^[ \t]*\[(mutlu|üzgün|kızgın|şaşkın|sakin)\][ \t]*", re.IGNORECASE | re.MULTILINE)


def dusunceyi_temizle(metin: str) -> str:
    """Modelin 'düşünme' ve ham araç çağrısı bloklarını (tamamlanmış ya da yarım) metinden çıkarır."""
    if not metin:
        return ""
    if "</think>" in metin and "<think>" not in metin:
        metin = metin.split("</think>", 1)[1]
    metin = _THINK_TAMAM.sub("", metin)
    metin = _THINK_ACIK.sub("", metin)
    metin = _ARAC_TAMAM.sub("", metin)
    metin = _ARAC_ACIK.sub("", metin)
    metin = _DUYGU_ETIKETI.sub("", metin)
    return metin.strip()


class _AkisCallback(BaseCallbackHandler):
    """Modelden gelen her token'ı, o an aktif olan isteğin akış fonksiyonuna iletir."""

    def __init__(self, servis):
        self._servis = servis

    def on_llm_new_token(self, token: str, **kwargs):
        akis = self._servis._akis_fonksiyonu
        if akis and token:
            akis(token)


class AIServisi:
    def __init__(self):
        self.backend = None          # beyin modülü
        self.hazir = False
        self.yukleme_hatasi = None
        self._akis_fonksiyonu = None
        self._onay_fonksiyonu = None
        self._bildirim_fonksiyonu = None

    # ------------------------------------------------------------
    # Bildirim (asistanın kendiliğinden verdiği haberler: "Öğrendim: ...", ileride hatırlatmalar vb.)
    # ------------------------------------------------------------
    def bildirim_fonksiyonu_ayarla(self, fonksiyon):
        """fonksiyon(metin: str)  (arka plan thread'inden çağrılır)"""
        self._bildirim_fonksiyonu = fonksiyon
        if self.backend is not None:
            self.backend.bildirim_fonksiyonu = fonksiyon

    # ------------------------------------------------------------
    # Onay (kod çalıştırma, dosya taşıma vb. için kullanıcıya sorma)
    # ------------------------------------------------------------
    def onay_fonksiyonu_ayarla(self, fonksiyon):
        """fonksiyon(aciklama: str) -> bool  (arka plan thread'inden çağrılır, bekleyebilir)"""
        self._onay_fonksiyonu = fonksiyon
        if self.backend is not None:
            self.backend.onay_fonksiyonu = fonksiyon

    # ------------------------------------------------------------
    # Yükleme
    # ------------------------------------------------------------
    def yukle(self, on_hazir, on_hata):
        threading.Thread(target=self._yukle_is, args=(on_hazir, on_hata), daemon=True).start()

    def _yukle_is(self, on_hazir, on_hata):
        try:
            import beyin
            self.backend = beyin

            if self._onay_fonksiyonu is not None:
                beyin.onay_fonksiyonu = self._onay_fonksiyonu
            if self._bildirim_fonksiyonu is not None:
                beyin.bildirim_fonksiyonu = self._bildirim_fonksiyonu

            # Gerçek zamanlı akışı aç (model desteklemiyorsa sessizce normal devam eder)
            try:
                beyin.llm.streaming = True
                beyin.llm.callbacks = [_AkisCallback(self)]
            except Exception:
                pass

            self.hazir = True
            on_hazir()
        except Exception as e:
            self.yukleme_hatasi = str(e)
            print(traceback.format_exc())
            on_hata(str(e))

    # ------------------------------------------------------------
    # Soru sorma
    # ------------------------------------------------------------
    def sor(self, mesaj, gecmis, on_token, on_cevap, on_hata, ses_modu=False):
        """
        mesaj  : kullanıcının yeni mesajı
        gecmis : bu sohbetteki önceki mesajlar [{"sender","text","is_ai"}, ...]
        on_token(token), on_cevap(metin), on_hata(hata_metni)
        ses_modu : True ise model kısa, doğal, sesli okunmaya uygun konuşur
        """
        if not self.hazir:
            on_hata("Yapay zeka henüz hazır değil.")
            return
        threading.Thread(target=self._sor_is,
                         args=(mesaj, gecmis, on_token, on_cevap, on_hata, ses_modu),
                         daemon=True).start()

    def _sor_is(self, mesaj, gecmis, on_token, on_cevap, on_hata, ses_modu=False):
        self._akis_fonksiyonu = on_token
        try:
            cevap = self.backend.yapay_zekaya_sor(mesaj, gecmis, ses_modu=ses_modu)
            on_cevap(dusunceyi_temizle(cevap))
        except Exception as e:
            print(traceback.format_exc())
            on_hata(str(e))
        finally:
            self._akis_fonksiyonu = None
