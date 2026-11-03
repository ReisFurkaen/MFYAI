"""
MFY AI - Ses Çıkışı (Pocket TTS Turkish)
  * Metni parça parça (stream) üretip hemen çalar: ilk ses 0,1 sn civarında başlar
  * durdur(): çalan sesi ve kuyruğu anında keser (söz kesme / sustur)
  * hiz_ayarla(): konuşma hızını canlı olarak değiştirir (0.5 - 2.0)
  * Sık kullanılan kısa tepkiler ("Hemen hallediyorum" vb.) açılışta hazırlanır, gecikmesiz çalınır
  * Çok iş parçacıklı güvenlidir; çağıranlar hiç beklemez (konus() anında döner)

Kurulum:  pip install pocket-tts-turkish sounddevice
"""
import queue
import threading
import time

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

import konusma_stili

# Marka/yabancı kelimelerin doğru okunması için telaffuz sözlüğü
TELAFFUZLAR = {
    "YouTube": "yutüp", "Chrome": "krom", "Spotify": "spotifay", "Discord": "diskord", "Steam": "stim",
    "Windows": "vindovs", "PowerShell": "pauır şel", "Wi-Fi": "vay fay", "WiFi": "vay fay", "MFY": "me fe ye",
    "CPU": "si pi yu", "GPU": "ci pi yu", "WhatsApp": "votsap", "Google": "gugıl",
}

SES_ADLARI = {
    "female_1": "Kadın - parlak, enerjik",
    "female_2": "Kadın - sıcak, samimi",
    "female_3": "Kadın - kendinden emin, net",
    "male_1": "Erkek - sakin, derin",
    "male_2": "Erkek - enerjik, parlak",
    "male_3": "Erkek - kendinden emin, net",
}

HIZ_MIN = 0.5
HIZ_MAX = 2.0


class SesCikisi:
    def __init__(self, ses: str = "male_1", cihaz: str = "cpu", seviye: float = 0.9,
                 cikis_cihazi=None, tts_nesnesi=None, sd_modulu=None, hiz: float = 1.0):
        self.ses = ses
        self.cihaz = cihaz
        self.seviye = max(0.0, min(1.0, seviye))
        self.hiz = max(HIZ_MIN, min(HIZ_MAX, float(hiz)))  # 1.0 normal, 1.2 = %20 hızlı, 0.8 = %20 yavaş
        self.cikis_cihazi = cikis_cihazi
        self.tts = tts_nesnesi
        self._sd = sd_modulu
        self.sample_rate = 24000
        self.hazir = False

        self.on_basla = None     # konuşma başlayınca (kuyruk boşken ilk öğe eklendiğinde)
        self.on_bitti = None     # kuyruk tamamen bitince / susturulunca
        self.on_hata = None      # hata metni

        self._kuyruk = queue.Queue()
        self._kilit = threading.Lock()
        self._tts_kilidi = threading.Lock()
        self._nesil = 0
        self._bekleyen = 0
        self._kapat = threading.Event()
        self._isci = None
        self._onbellek = {}
        self._son_dolgu = {}
        self._akis = None

    # ------------------------------------------------------------
    # Yükleme
    # ------------------------------------------------------------
    def yukle(self, ilerleme=None):
        if self.tts is None:
            from pocket_tts_turkish import TurkishTTS
            if ilerleme:
                ilerleme("Ses modeli yükleniyor…")
            try:
                self.tts = TurkishTTS.from_pretrained(device=self.cihaz, pronunciations=TELAFFUZLAR)
            except TypeError:
                self.tts = TurkishTTS.from_pretrained(device=self.cihaz)
        self.sample_rate = int(getattr(self.tts, "sample_rate", 24000))
        if self._sd is None:
            import sounddevice as sd
            self._sd = sd
        if ilerleme:
            ilerleme("Ses hazırlanıyor…")
        # İlk çağrı sesi hazırlar (CPU'da ~0,4 sn); kullanıcı beklemesin diye şimdi yap
        with self._tts_kilidi:
            for _ in self.tts.stream("Merhaba.", voice=self.ses):
                break
        self._onbellek_hazirla()
        self._isci = threading.Thread(target=self._isci_dongusu, daemon=True)
        self._isci.start()
        self.hazir = True

    def _onbellek_hazirla(self):
        yeni = {}
        with self._tts_kilidi:
            for cumle in konusma_stili.TUM_DOLGULAR:
                try:
                    yeni[cumle] = np.asarray(self.tts.generate(cumle, voice=self.ses), dtype=np.float32).reshape(-1)
                except Exception:
                    pass
        self._onbellek = yeni

    # ------------------------------------------------------------
    # Kuyruk ve sayaçlar
    # ------------------------------------------------------------
    @property
    def konusuyor(self) -> bool:
        return self._bekleyen > 0

    def _kuyruga(self, tur, veri, duygu, say=True):
        ilk = False
        with self._kilit:
            nesil = self._nesil
            if say:
                self._bekleyen += 1
                ilk = self._bekleyen == 1
        self._kuyruk.put((nesil, tur, veri, duygu, say))
        if ilk and self.on_basla:
            try:
                self.on_basla()
            except Exception:
                pass

    def _bitir_say(self):
        bitti = False
        with self._kilit:
            if self._bekleyen > 0:
                self._bekleyen -= 1
                bitti = self._bekleyen == 0
        if bitti and self.on_bitti:
            try:
                self.on_bitti()
            except Exception:
                pass

    def konus(self, metin: str, duygu=None):
        """Metni konuşma kuyruğuna ekler ve hemen döner."""
        metin = (metin or "").strip()
        if metin and self.hazir:
            self._kuyruga("metin", metin, duygu)

    def dolgu_cal(self, kategori: str):
        """Kısa insani tepki çalar ('Hemen hallediyorum' vb.). Çalınan cümleyi döndürür."""
        if not self.hazir:
            return ""
        cumle = konusma_stili.dolgu_sec(kategori, self._son_dolgu.get(kategori))
        self._son_dolgu[kategori] = cumle
        dizi = self._onbellek.get(cumle)
        if dizi is not None:
            self._kuyruga("dizi", dizi, None)
        else:
            self._kuyruga("metin", cumle, None)
        return cumle

    def durdur(self):
        """Çalan sesi ve bekleyen her şeyi anında durdurur."""
        atilan, bitti = 0, False
        with self._kilit:
            self._nesil += 1
            while True:
                try:
                    oge = self._kuyruk.get_nowait()
                    if oge[4]:
                        atilan += 1
                except queue.Empty:
                    break
            if atilan:
                self._bekleyen = max(0, self._bekleyen - atilan)
                bitti = self._bekleyen == 0
        if bitti and self.on_bitti:
            try:
                self.on_bitti()
            except Exception:
                pass

    def bekle(self, zaman_asimi: float = 60.0) -> bool:
        bitis = time.time() + zaman_asimi
        while self._bekleyen > 0 and time.time() < bitis:
            time.sleep(0.02)
        return self._bekleyen == 0

    def ses_ayarla(self, ses: str):
        if ses and ses != self.ses:
            self.ses = ses
            self._kuyruga("onbellek_yenile", None, None, say=False)

    def seviye_ayarla(self, seviye: float):
        self.seviye = max(0.0, min(1.0, float(seviye)))

    def hiz_ayarla(self, hiz: float):
        """Konuşma hızı (0.5 - 2.0). 1.0 = normal. Sonraki ses parçasından itibaren geçerli olur."""
        self.hiz = max(HIZ_MIN, min(HIZ_MAX, float(hiz)))

    def kapat(self):
        self._kapat.set()
        self.durdur()
        self._kuyruk.put((self._nesil, "bitir", None, None, False))

    # ------------------------------------------------------------
    # Çalma işçisi (tek iş parçacığı)
    # ------------------------------------------------------------
    def _akis_ac(self):
        akis = self._sd.OutputStream(samplerate=self.sample_rate, channels=1, dtype="float32",
                                     device=self.cikis_cihazi)
        akis.start()
        return akis

    def _isci_dongusu(self):
        akis = None
        try:
            while not self._kapat.is_set():
                try:
                    nesil, tur, veri, duygu, say = self._kuyruk.get(timeout=0.25)
                except queue.Empty:
                    continue
                if tur == "bitir":
                    break
                try:
                    if nesil == self._nesil or tur == "onbellek_yenile":
                        if tur == "onbellek_yenile":
                            self._onbellek_hazirla()
                        else:
                            if akis is None:
                                akis = self._akis_ac()
                            self._akis = akis
                            if tur == "dizi":
                                self._cal_dizi(akis, veri, nesil)
                            elif tur == "metin":
                                self._cal_metin(akis, veri, duygu, nesil)
                except Exception as e:
                    if self.on_hata:
                        try:
                            self.on_hata(f"Ses çalınamadı: {e}")
                        except Exception:
                            pass
                    try:
                        if akis is not None:
                            akis.close()
                    except Exception:
                        pass
                    akis = None
                finally:
                    if say:
                        self._bitir_say()
        finally:
            try:
                if akis is not None:
                    akis.stop()
                    akis.close()
            except Exception:
                pass

    def _yaz(self, akis, parca):
        x = np.asarray(parca, dtype=np.float32).reshape(-1)
        # Hız ayarı: parçayı yeniden örnekleyerek hızlandır / yavaşlat
        hiz = self.hiz
        if abs(hiz - 1.0) > 0.01 and len(x) > 1:
            n = max(1, int(round(len(x) / hiz)))
            x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
        if self.seviye < 0.999:
            x = x * self.seviye
        akis.write(np.clip(x, -1.0, 1.0).reshape(-1, 1))

    def _kes(self, akis):
        """Cihazın tamponundaki kalan sesi de at (söz kesmede 'kuyruk' çalmaya devam etmesin)."""
        try:
            akis.abort()
            akis.start()
        except Exception:
            pass

    def _cal_dizi(self, akis, dizi, nesil):
        adim = 2400
        for i in range(0, len(dizi), adim):
            if nesil != self._nesil or self._kapat.is_set():
                self._kes(akis)
                return
            self._yaz(akis, dizi[i:i + adim])

    def _cal_metin(self, akis, metin, duygu, nesil):
        kwargs = {"voice": self.ses}
        if duygu:
            kwargs["emotion"] = duygu
        kesildi = False
        with self._tts_kilidi:
            uretec = self.tts.stream(metin, **kwargs)
            try:
                for parca in uretec:
                    if nesil != self._nesil or self._kapat.is_set():
                        kesildi = True
                        break
                    self._yaz(akis, parca)
            finally:
                kapat = getattr(uretec, "close", None)
                if kapat:
                    try:
                        kapat()
                    except Exception:
                        pass
        if kesildi:
            self._kes(akis)