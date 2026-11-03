"""
MFY AI - Ses Yöneticisi
Mikrofon -> konuşma tanıma -> (arayüz mesajı AI'a gönderir) -> cümle cümle sesli cevap.
Arayüzden BAĞIMSIZDIR (Qt gerekmez): arayüz sadece geri çağırmaları (callback) bağlar.

Geri çağırmalar (arka plan iş parçacıklarından çağrılır; arayüz kendi iş parçacığına aktarmalıdır):
    on_hazir()                  ses sistemi (en az bir yarısı) hazır
    on_durum(kod, metin)        kod: 'hazir' | 'dinliyor' | 'cozumluyor' | 'konusuyor'
    on_metin(metin)             kullanıcının söylediği (yazıya çevrilmiş) cümle -> arayüz bunu AI'a göndermeli
    on_bilgi(metin) / on_hata(metin)
    on_eller_serbest(acik)      eller serbest hata nedeniyle kapandıysa

Arayüzün çağırdıkları:
    yukle(), dinle(), dinlemeyi_iptal(), eller_serbest_ayarla(bool),
    yanit_basladi(eylem, sesli_cevap), token_ver(token), yanit_bitti(metin), yanit_iptal(),
    sustur(), dolgu_cal(kategori), konus_dogrudan(metin), ornek_cal(metin), ayarla(...), kapat()
"""
import re
import time
import threading

import konusma_stili as KS

GUVEN_ESIGI = 0.40          # Altındaki duymalarda "tam duyamadım" der, tahminle işlem yapmaz
MAKS_CUMLE = 4              # Sesli cevapta en fazla bu kadar cümle okunur, gerisi "ekrana yazdım"
MAKS_KARAKTER = 420
UYANDIRMA_MAKS_SN = 8.0      # 'Hey MFY' modunda bundan uzun konuşmalar asistana seslenmiyor sayılır (yazıya bile çevrilmez)
UYANDIRMA_GUVEN = 0.30       # Altındaki duymalar uyandırma sayılmaz (gürültü/yanlış duyma koruması)
KOMUT_BEKLEME_SN = 10.0      # Sadece 'Hey MFY' denince komut için beklenen süre


def _ayar(ad, varsayilan):
    try:
        import config
        return getattr(config, ad, varsayilan)
    except Exception:
        return varsayilan


class SesYoneticisi:
    def __init__(self, ses=None, seviye: float = 0.9, mikrofon: str = "", kulaklik: bool = False,
                 giris=None, cikis=None):
        self.ses = ses or _ayar("SES_TTS_SES", "female_2")
        self.seviye = seviye
        self.mikrofon = mikrofon
        self.kulaklik = kulaklik
        self.giris = giris
        self.cikis = cikis
        self.giris_hazir = False
        self.cikis_hazir = False

        self.on_hazir = lambda: None
        self.on_durum = lambda kod, metin="": None
        self.on_metin = lambda metin: None
        self.on_bilgi = lambda metin: None
        self.on_hata = lambda metin: None
        self.on_eller_serbest = lambda acik: None

        self._kilit = threading.RLock()
        self._iptal = threading.Event()
        self._dinleme_thread = None
        self._eller_serbest = False          # sürekli dinleme açık mı (eller serbest VEYA Hey MFY modu)
        self._uyandirma = False              # True ise sürekli dinleme 'Hey MFY' ile kapılanmış
        self._komut_bitis = 0.0              # 'Hey MFY' denildi, bir sonraki cümle komut kabul edilir (bu zamana kadar)

        self._yanit_aktif = False
        self._sesli_cevap = False
        self._akis_modu = False
        self._susturuldu = False
        self._bolucu = KS.CumleBolucu()
        self._ham = ""
        self._onceki_temiz = ""
        self._okunan = 0
        self._konusulan_cumle = 0
        self._konusulan_kar = 0
        self._kesildi = False
        self._engel_bitis = 0.0
        self._gonderim_son = 0.0
        self._son_durum = None

    # ============================================================
    # Durum
    # ============================================================
    @property
    def konusuyor(self) -> bool:
        return bool(self.cikis_hazir and self.cikis.konusuyor)

    @property
    def eller_serbest(self) -> bool:
        return self._eller_serbest

    @property
    def uyandirma(self) -> bool:
        return self._uyandirma and self._eller_serbest

    def dinliyor_mu(self) -> bool:
        t = self._dinleme_thread
        return t is not None and t.is_alive()

    def _durum(self, kod: str, metin: str = ""):
        yeni = (kod, metin)
        if yeni != self._son_durum:
            self._son_durum = yeni
            try:
                self.on_durum(kod, metin)
            except Exception:
                pass

    def _bosta_durumu(self):
        if self.konusuyor:
            self._durum("konusuyor", "Konuşuyor…")
        elif self.dinliyor_mu():
            self._durum("dinliyor", "Dinliyor…")
        else:
            self._durum("hazir", "Hazır")

    @staticmethod
    def _hata_metni(e: Exception) -> str:
        if isinstance(e, ImportError):
            return (f"gerekli paket kurulu değil ({e}). Terminalde şunu çalıştır: "
                    f"pip install pocket-tts-turkish faster-whisper sounddevice silero-vad")
        metin = str(e)
        kucuk = (type(e).__name__ + " " + metin).lower()
        if any(k in kucuk for k in ("localentrynotfound", "offline", "local_files_only", "local cache", "not found in cache",
                                    "cannot find the requested files", "connection", "max retries")):
            return (f"modeller henüz indirilmemiş olabilir ({metin[:120]}). "
                    f"Arayüz kapalıyken terminalde şunu çalıştır: python ses_kurulum.py")
        return metin

    # ============================================================
    # Yükleme
    # ============================================================
    def yukle(self):
        threading.Thread(target=self._yukle_is, daemon=True).start()

    def _yukle_is(self):
        hatalar = []

        def giris_yukle():
            try:
                if self.giris is None:
                    from ses_giris import SesGirisi
                    self.giris = SesGirisi(
                        model=_ayar("SES_STT_MODEL", "large-v3-turbo"),
                        cihaz=_ayar("SES_STT_CIHAZ", "cpu"),
                        hesap=_ayar("SES_STT_HESAP", "int8"),
                        mikrofon=self.mikrofon,
                        sessizlik_ms=_ayar("SES_SESSIZLIK_MS", 700))
                self.on_bilgi("Konuşma tanıma modeli yükleniyor…")
                self.giris.yukle()
                self.giris_hazir = True
            except Exception as e:
                hatalar.append(("Konuşma tanıma", e))

        def cikis_yukle():
            try:
                if self.cikis is None:
                    from ses_cikis import SesCikisi
                    self.cikis = SesCikisi(ses=self.ses, cihaz=_ayar("SES_TTS_CIHAZ", "cpu"), seviye=self.seviye,
                                       hiz=_ayar("SES_TTS_HIZ", 1.0))
                self.on_bilgi("Ses modeli yükleniyor…")
                self.cikis.yukle()
                self.cikis.on_basla = self._tts_basladi
                self.cikis.on_bitti = self._tts_bitti
                self.cikis.on_hata = self.on_hata
                self.cikis_hazir = True
            except Exception as e:
                hatalar.append(("Ses çıkışı", e))

        iskler = [threading.Thread(target=giris_yukle, daemon=True), threading.Thread(target=cikis_yukle, daemon=True)]
        for t in iskler:
            t.start()
        for t in iskler:
            t.join()
        for ad, e in hatalar:
            self.on_hata(f"{ad} yüklenemedi: {self._hata_metni(e)}")
        if self.giris_hazir or self.cikis_hazir:
            self.on_hazir()

    # ============================================================
    # Dinleme
    # ============================================================
    def dinle(self) -> bool:
        """Mikrofon düğmesi: tek bir cümle dinler (sessizlikte otomatik biter)."""
        if not self.giris_hazir:
            self.on_bilgi("Konuşma tanıma hazır değil.")
            return False
        with self._kilit:
            if self.dinliyor_mu():
                return False
            self._iptal.clear()
            self._dinleme_thread = threading.Thread(target=self._dinleme_dongusu, args=(True,), daemon=True)
            self._dinleme_thread.start()
        return True

    def dinlemeyi_iptal(self):
        self._iptal.set()

    def eller_serbest_ayarla(self, acik: bool) -> bool:
        if acik:
            return self._surekli_baslat(False)
        self._eller_serbest = False
        self._uyandirma = False
        self._iptal.set()
        return True

    def uyandirma_ayarla(self, acik: bool) -> bool:
        """'Hey MFY' modu: sürekli dinler, yalnızca 'Hey MFY' dediğinde komutu alır."""
        if acik:
            return self._surekli_baslat(True)
        if self._uyandirma:
            self._eller_serbest = False
            self._uyandirma = False
            self._iptal.set()
        return True

    def _surekli_baslat(self, uyandirma: bool) -> bool:
        if not self.giris_hazir:
            return False
        if self.dinliyor_mu() and not self._eller_serbest:        # tek seferlik dinleme sürüyorsa önce onu bitir
            self._iptal.set()
            t = self._dinleme_thread
            if t:
                t.join(timeout=1.0)
        with self._kilit:
            self._uyandirma = uyandirma
            self._komut_bitis = 0.0
            self._eller_serbest = True
            if not self.dinliyor_mu():
                self._iptal.clear()
                self._dinleme_thread = threading.Thread(target=self._dinleme_dongusu, args=(False,), daemon=True)
                self._dinleme_thread.start()
        return True

    def _dinleme_dongusu(self, tek: bool):
        try:
            self.giris.mikrofon = self.mikrofon
            self.giris.mikrofonu_ac()
            while not self._iptal.is_set():
                if not tek and not self._eller_serbest:
                    break
                self._durum("dinliyor", self._bekleme_metni(tek))
                ses = self.giris.konusma_bekle(
                    self._iptal, engel_fn=(None if tek else self._engel),
                    soz_kesme_cb=self._soz_kesildi, ilk_zaman_asimi=(8.0 if tek else None))
                if ses is None:
                    if tek:
                        if not self._iptal.is_set():
                            self.on_bilgi("Seni duyamadım, tekrar dener misin?")
                        break
                    continue
                if not tek and self._uyandirma:
                    self._uyandirma_isle(ses)
                    continue
                self._durum("cozumluyor", "Yazıya çeviriyor…")
                metin, guven, _gecen = self.giris.cozumle(ses)
                self._metin_isle(metin, guven, len(ses) / 16000.0, tek)
                if tek:
                    break
        except Exception as e:
            self.on_hata(f"Mikrofon/konuşma tanıma hatası: {self._hata_metni(e)}")
            if self._eller_serbest:
                self._eller_serbest = False
                self.on_eller_serbest(False)
        finally:
            try:
                self.giris.mikrofonu_kapat()
            except Exception:
                pass
            self._son_durum = None
            self._bosta_durumu()

    def _bekleme_metni(self, tek: bool) -> str:
        if tek or not self._uyandirma:
            return "Dinliyor…"
        return "Dinliyorum…" if time.time() < self._komut_bitis else "“Hey MFY” bekliyor…"

    def _uyandirma_isle(self, ses):
        """Hey MFY modunda bir konuşma yakalandı: seslenme mi, değil mi? Değilse sessizce yok say."""
        sure = len(ses) / 16000.0
        bekleniyor = time.time() < self._komut_bitis
        if not bekleniyor and sure > UYANDIRMA_MAKS_SN:
            return                                    # uzun konuşma asistana seslenmiyor
        self._durum("cozumluyor", "Yazıya çeviriyor…")
        metin, guven, _gecen = self.giris.cozumle(ses)
        if not metin:
            return
        if bekleniyor:                                # "Hey MFY" denmişti, bu cümle komut
            self._komut_bitis = 0.0
            self._metin_isle(metin, guven, sure, True)
            return
        bulundu, komut = KS.uyandirma_ayikla(metin, esik_hey=_ayar("SES_UYANDIRMA_ESIK", 0.67))
        if not bulundu or guven < UYANDIRMA_GUVEN:
            return                                    # seslenilmedi: yok say (hiçbir şey saklanmaz)
        if len(re.findall(r"\w", komut)) >= 3:       # "Hey MFY, sesi kıs": komut aynı cümlede
            self._metin_isle(komut, guven, sure, True)
        else:                                         # sadece "Hey MFY": komut için kulak ver
            self._komut_bitis = time.time() + KOMUT_BEKLEME_SN
            if self.cikis_hazir:
                self.cikis.dolgu_cal("uyandirma")
            else:
                self.on_bilgi("Dinliyorum…")

    def _metin_isle(self, metin: str, guven: float, sure: float, tek: bool):
        if not metin:
            if tek:
                self.on_bilgi("Bir şey anlayamadım.")
            return
        if guven < GUVEN_ESIGI and (tek or sure > 0.8):
            # Emin değilse tahminle işlem yapma: tekrar iste.
            # (Eller serbest modunda çok kısa sesler gürültü olabilir; onlar için sormayız.)
            if self.cikis_hazir:
                self.cikis.dolgu_cal("anlamadim")
            else:
                self.on_bilgi(f"Tam duyamadım: “{metin}”")
            return
        with self._kilit:
            self._gonderim_son = time.time() + 3.0     # arayüz mesajı gönderene kadar yeni konuşma alma
        self.on_metin(metin)

    def _engel(self):
        """Dinleme döngüsüne: gelen sesi şimdi yok say mı, sıkı mı dinle, normal mi?"""
        simdi = time.time()
        if self._yanit_aktif or simdi < self._gonderim_son:
            return "engel"
        if self.konusuyor:
            return "soz_kesme" if self.kulaklik else "engel"      # hoparlörde yankı koruması
        if simdi < self._engel_bitis:
            return "engel"
        return None

    def _soz_kesildi(self):
        """Kulaklık modunda asistan konuşurken kullanıcı araya girdi."""
        with self._kilit:
            self._susturuldu = True
            self._engel_bitis = 0.0
        if self.cikis_hazir:
            self.cikis.durdur()

    # ============================================================
    # Konuşma çıkışı callback'leri
    # ============================================================
    def _tts_basladi(self):
        self._durum("konusuyor", "Konuşuyor…")

    def _tts_bitti(self):
        self._engel_bitis = time.time() + (0.25 if self.kulaklik else 0.7)
        self._bosta_durumu()

    # ============================================================
    # Cevap akışı (arayüz çağırır)
    # ============================================================
    def yanit_basladi(self, eylem: bool = False, sesli_cevap: bool = True):
        """
        AI cevap üretmeye başladı.
        eylem=True  : bilgisayarda bir işlem yapılacak -> önce kısa tepki ("Hemen hallediyorum"), cevap bitince okunur
        eylem=False : sohbet -> cevap üretilirken cümle cümle okunur (daha hızlı hissettirir)
        """
        with self._kilit:
            self._yanit_aktif = True
            self._gonderim_son = 0.0
            self._sesli_cevap = bool(sesli_cevap and self.cikis_hazir)
            self._akis_modu = self._sesli_cevap and not eylem
            self._susturuldu = False
            self._bolucu = KS.CumleBolucu()
            self._ham, self._onceki_temiz, self._okunan = "", "", 0
            self._konusulan_cumle, self._konusulan_kar, self._kesildi = 0, 0, False
        if self._sesli_cevap and eylem:
            self.cikis.dolgu_cal("eylem")

    def token_ver(self, token: str):
        if not (self._yanit_aktif and self._akis_modu and not self._susturuldu):
            return
        self._ham += token
        temiz = KS.etiket_temizle(self._ham)
        if not temiz.startswith(self._onceki_temiz):
            return                      # metin geriye dönük değişti (etiket kapandı vb.): son hâli bekle
        yeni = temiz[self._okunan:]
        self._onceki_temiz, self._okunan = temiz, len(temiz)
        for cumle in self._bolucu.ekle(yeni):
            self._cumle_konus(cumle)

    def yanit_bitti(self, metin: str):
        with self._kilit:
            sesli, akis, susturuldu = self._sesli_cevap, self._akis_modu, self._susturuldu
            self._yanit_aktif = False
        try:
            if sesli and not susturuldu:
                tam = KS.etiket_temizle(metin or "")
                if akis and tam.startswith(self._onceki_temiz):
                    cumleler = self._bolucu.ekle(tam[self._okunan:]) + self._bolucu.bitir()
                else:
                    if akis and self._konusulan_cumle:       # akışta okunan metin son cevaptan farklı çıktı
                        self.cikis.durdur()
                        self._konusulan_cumle, self._konusulan_kar, self._kesildi = 0, 0, False
                    self._bolucu = KS.CumleBolucu()
                    cumleler = self._bolucu.ekle(tam) + self._bolucu.bitir()
                for cumle in cumleler:
                    self._cumle_konus(cumle)
        finally:
            self._bosta_durumu()

    def yanit_iptal(self):
        """Cevap hata ile bitti."""
        with self._kilit:
            self._yanit_aktif = False
            sesli = self._sesli_cevap and not self._susturuldu
        if sesli:
            self.cikis.durdur()
            self.cikis.dolgu_cal("hata")
        self._bosta_durumu()

    def _cumle_konus(self, cumle: str):
        if self._kesildi or not self.cikis_hazir:
            return
        duygu, govde = KS.etiketi_ayir(cumle)
        govde = KS.konusmaya_hazirla(govde)
        if not re.search(r"\w", govde):
            return
        if self._konusulan_cumle >= 1 and (self._konusulan_cumle >= MAKS_CUMLE
                                           or self._konusulan_kar + len(govde) > MAKS_KARAKTER):
            self._kesildi = True
            self.cikis.konus(KS.KESME_CUMLESI)
            return
        self.cikis.konus(govde, duygu or KS.duygu_sec(govde))
        self._konusulan_cumle += 1
        self._konusulan_kar += len(govde)

    # ============================================================
    # Diğer
    # ============================================================
    def sustur(self):
        """Konuşmayı hemen keser; geri kalan cevap okunmaz."""
        with self._kilit:
            self._susturuldu = True
        if self.cikis_hazir:
            self.cikis.durdur()

    def dolgu_cal(self, kategori: str):
        if self.cikis_hazir:
            self.cikis.dolgu_cal(kategori)

    def konus_dogrudan(self, metin: str, duygu=None):
        """Hatırlatma gibi, AI cevabı olmayan metinleri okur."""
        if not self.cikis_hazir:
            return
        govde = KS.konusmaya_hazirla(metin)
        if re.search(r"\w", govde):
            self.cikis.konus(govde, duygu)

    def ornek_cal(self, metin: str):
        if self.cikis_hazir:
            self.cikis.durdur()
            self.cikis.konus(KS.konusmaya_hazirla(metin))

    def ayarla(self, ses=None, seviye=None, mikrofon=None, kulaklik=None):
        if ses is not None:
            self.ses = ses
            if self.cikis_hazir:
                self.cikis.ses_ayarla(ses)
        if seviye is not None:
            self.seviye = seviye
            if self.cikis_hazir:
                self.cikis.seviye_ayarla(seviye)
        if mikrofon is not None:
            self.mikrofon = mikrofon          # bir sonraki dinlemede uygulanır
        if kulaklik is not None:
            self.kulaklik = kulaklik

    def kapat(self):
        self._eller_serbest = False
        self._uyandirma = False
        self._iptal.set()
        try:
            if self.giris is not None:
                self.giris.kapat()
        except Exception:
            pass
        try:
            if self.cikis_hazir:
                self.cikis.kapat()
        except Exception:
            pass
