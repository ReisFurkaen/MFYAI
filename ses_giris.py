"""
MFY AI - Ses Girişi
  * Mikrofon    : 16 kHz mono, 32 ms'lik çerçevelerle sürekli akış
  * VAD         : Konuşmanın başlayıp bittiğini anlar (Silero varsa onu, yoksa basit enerji tabanlı yedeği kullanır)
  * Söz kesme   : Asistan konuşurken (kulaklık modunda) kullanıcı konuşmaya başlarsa bildirir
  * Çözümleme   : faster-whisper ile Türkçe yazıya çevirir, güven puanı verir, Whisper'ın sessizlikte
                  uydurduğu cümleleri ("Abone olmayı unutmayın" vb.) ayıklar

Kurulum:  pip install faster-whisper sounddevice silero-vad
"""
import os
import re
import math
import time
import queue
import threading
import collections

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

from konusma_stili import sade

ORNEK_HIZI = 16000
CERCEVE = 512                                   # 32 ms
CERCEVE_SN = CERCEVE / ORNEK_HIZI
ONSOZ_CERCEVE = 12                              # konuşma başlamadan önceki ~380 ms de kayda katılır
SOZ_KESME_CERCEVE = 10                          # söz kesme için ~320 ms kesintisiz ve net konuşma
MIN_KONUSMA_CERCEVE = 8                         # ~250 ms'den kısa sesler gürültü sayılır
MAKS_KONUSMA_SN = 20.0

IPUCU = ("Bilgisayar asistanı komutları: Chrome'u aç, YouTube'da şarkı çal, sesi kıs, pencereyi kapat, "
         "not defteri, Spotify, dosya, klasör, hatırlatıcı kur.")

# Whisper'ın sessizlik/gürültüde uydurduğu bilinen kalıplar (sadeleştirilmiş)
_HALUSINASYON = [
    "altyazi", "abone ol", "izlediginiz icin", "iyi seyirler", "bir sonraki video", "begenmeyi unutmayin",
    "kanalima", "amara.org", "devami bir sonraki", "videoyu izledi",
]


def halusinasyon_mu(metin: str, sure_sn: float, ipucu: str = IPUCU) -> bool:
    s = sade(metin).strip()
    if not s:
        return True
    if any(k in s for k in _HALUSINASYON):
        return True
    if re.fullmatch(r"[\[\(].*[\]\)]\.?", metin.strip()):          # [Müzik], (alkış) gibi ses notları
        return True
    kelimeler = s.split()
    if len(kelimeler) >= 5 and len(set(kelimeler)) <= 2:            # "evet evet evet evet evet"
        return True
    if len(s) > 12 and s in sade(ipucu or ""):                      # ipucu metnini geri okumuş
        return True
    return False


# ============================================================
# VAD (konuşma algılama)
# ============================================================
class EnerjiVAD:
    """Silero yoksa kullanılan basit yedek: ortam gürültüsüne uyum sağlayan enerji eşiği."""
    ad = "enerji"

    def __init__(self):
        self.gurultu = 0.008

    def olasilik(self, cerceve) -> float:
        rms = float(np.sqrt(np.mean(np.square(cerceve)))) if len(cerceve) else 0.0
        esik = max(0.012, self.gurultu * 3.0)
        if rms < esik:
            self.gurultu = 0.97 * self.gurultu + 0.03 * rms
        return max(0.0, min(1.0, (rms / esik - 0.8) / 0.6))

    def sifirla(self):
        pass


class SileroVAD:
    ad = "silero"

    def __init__(self):
        import torch
        from silero_vad import load_silero_vad
        self._torch = torch
        self.model = load_silero_vad()

    def olasilik(self, cerceve) -> float:
        with self._torch.no_grad():
            return float(self.model(self._torch.from_numpy(cerceve), ORNEK_HIZI).item())

    def sifirla(self):
        try:
            self.model.reset_states()
        except Exception:
            pass


def vad_sec():
    try:
        return SileroVAD()
    except Exception:
        return EnerjiVAD()


# ============================================================
# MİKROFON
# ============================================================
def mikrofon_bul(ad: str, sd_modulu=None):
    """Kayıtlı mikrofon adını cihaz numarasına çevirir. Bulunamazsa None (varsayılan mikrofon)."""
    if not ad:
        return None
    try:
        sd = sd_modulu
        if sd is None:
            import sounddevice as sd
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) > 0 and d.get("name") == ad:
                return i
    except Exception:
        pass
    return None


class Mikrofon:
    def __init__(self, cihaz: str = "", sd_modulu=None):
        self.cihaz = cihaz
        self._sd = sd_modulu
        self._q = queue.Queue(maxsize=400)
        self._akis = None

    @property
    def acik(self) -> bool:
        return self._akis is not None

    def ac(self):
        if self._akis is not None:
            return
        if self._sd is None:
            import sounddevice as sd
            self._sd = sd
        idx = mikrofon_bul(self.cihaz, self._sd)

        def geri_cagri(indata, frames, zaman, durum):
            x = np.array(indata[:, 0], dtype=np.float32, copy=True)
            try:
                self._q.put_nowait(x)
            except queue.Full:
                try:
                    self._q.get_nowait()
                    self._q.put_nowait(x)
                except Exception:
                    pass

        self.temizle()
        self._akis = self._sd.InputStream(samplerate=ORNEK_HIZI, channels=1, dtype="float32",
                                          blocksize=CERCEVE, device=idx, callback=geri_cagri)
        self._akis.start()

    def oku(self, zaman_asimi: float = 0.1):
        try:
            return self._q.get(timeout=zaman_asimi)
        except queue.Empty:
            return None

    def temizle(self):
        while True:
            try:
                self._q.get_nowait()
            except queue.Empty:
                break

    def kapat(self):
        akis, self._akis = self._akis, None
        if akis is not None:
            try:
                akis.stop()
                akis.close()
            except Exception:
                pass


# ============================================================
# SES GİRİŞİ (mikrofon + VAD + Whisper)
# ============================================================
class SesGirisi:
    def __init__(self, model: str = "large-v3-turbo", cihaz: str = "cpu", hesap: str = "int8",
                 mikrofon: str = "", sessizlik_ms: int = 700, ipucu: str = IPUCU,
                 stt_nesnesi=None, vad=None, mik=None, sd_modulu=None):
        self.model_adi = model
        self.cihaz = cihaz
        self.hesap = hesap
        self.mikrofon = mikrofon
        self.sessizlik_cerceve = max(4, int(sessizlik_ms / 1000.0 / CERCEVE_SN))
        self.ipucu = ipucu
        self.model = stt_nesnesi
        self.vad = vad
        self.vad_adi = getattr(vad, "ad", "?") if vad else None
        self.mik = mik
        self._sd = sd_modulu
        self.hazir = False

    # ------------------------------------------------------------
    def _cihaz_sec(self):
        if self.cihaz == "auto":
            try:
                import torch
                bos, _ = torch.cuda.mem_get_info()
                if bos > 3.2 * 1024 ** 3:
                    return "cuda", "int8_float16"
            except Exception:
                pass
            return "cpu", self.hesap
        if self.cihaz == "cuda":
            return "cuda", "int8_float16"
        return "cpu", self.hesap

    def yukle(self, ilerleme=None):
        if self.vad is None:
            self.vad = vad_sec()
            self.vad_adi = self.vad.ad
        if self.model is None:
            from faster_whisper import WhisperModel
            cihaz, hesap = self._cihaz_sec()
            if ilerleme:
                ilerleme(f"Konuşma tanıma modeli yükleniyor ({self.model_adi}, {cihaz})…")
            kwargs = {"device": cihaz, "compute_type": hesap}
            if cihaz == "cpu":
                kwargs["cpu_threads"] = max(2, (os.cpu_count() or 4) // 2)
            self.model = WhisperModel(self.model_adi, **kwargs)
            list(self.model.transcribe(np.zeros(ORNEK_HIZI, dtype=np.float32), language="tr", beam_size=1)[0])
        self.hazir = True

    # ------------------------------------------------------------
    def mikrofonu_ac(self):
        if self.mik is None:
            self.mik = Mikrofon(self.mikrofon, self._sd)
        else:
            self.mik.cihaz = self.mikrofon
        self.mik.ac()

    def mikrofonu_kapat(self):
        if self.mik is not None:
            self.mik.kapat()

    def konusma_bekle(self, iptal, engel_fn=None, soz_kesme_cb=None, ilk_zaman_asimi=None, on_basladi=None):
        """
        Bir kullanıcı konuşması tamamlanana kadar dinler. Döner: float32 ses dizisi (16 kHz) ya da None.
        engel_fn()      -> None | "engel" | "soz_kesme"
                           "engel": gelen sesi yok say (asistan konuşuyor/düşünüyor, yankı koruması)
                           "soz_kesme": asistan konuşuyor ama kulaklık modu; daha sıkı eşikle dinle
        soz_kesme_cb()  -> söz kesme algılanınca bir kez çağrılır (arayüz/yönetici konuşmayı susturur)
        """
        onsoz = collections.deque(maxlen=ONSOZ_CERCEVE)
        konusma, konusuyor = [], False
        ardisik, sessiz, gercek = 0, 0, 0
        baslangic = time.time()
        self.vad.sifirla()
        self.mik.temizle()

        def sifirla():
            nonlocal konusma, konusuyor, ardisik, sessiz, gercek
            onsoz.clear()
            konusma, konusuyor, ardisik, sessiz, gercek = [], False, 0, 0, 0
            self.vad.sifirla()

        while not iptal.is_set():
            cerceve = self.mik.oku(0.1)
            if cerceve is None:
                if ilk_zaman_asimi and not konusuyor and time.time() - baslangic > ilk_zaman_asimi:
                    return None
                continue
            if len(cerceve) != CERCEVE:
                continue
            durum = engel_fn() if engel_fn else None
            if durum == "engel":
                sifirla()
                baslangic = time.time()
                continue

            p = self.vad.olasilik(cerceve)
            siki = durum == "soz_kesme"
            if not konusuyor:
                onsoz.append(cerceve)
                ardisik = ardisik + 1 if p >= (0.75 if siki else 0.5) else 0
                if ardisik >= (SOZ_KESME_CERCEVE if siki else 2):
                    konusuyor = True
                    konusma = list(onsoz)
                    sessiz, gercek = 0, ardisik
                    if siki and soz_kesme_cb:
                        soz_kesme_cb()
                    if on_basladi:
                        on_basladi()
            else:
                konusma.append(cerceve)
                if p >= 0.5:
                    gercek += 1
                sessiz = sessiz + 1 if p < 0.35 else 0
                bitti = sessiz >= self.sessizlik_cerceve
                cok_uzun = len(konusma) * CERCEVE_SN >= MAKS_KONUSMA_SN
                if bitti or cok_uzun:
                    if gercek >= MIN_KONUSMA_CERCEVE:
                        return np.concatenate(konusma)
                    sifirla()          # çok kısa: tıklama/öksürük gibi gürültü, yok say
        return None

    # ------------------------------------------------------------
    def cozumle(self, ses):
        """Döner: (metin, guven 0-1, sure_sn). Metin boşsa anlaşılabilir bir konuşma yok demektir."""
        t0 = time.time()
        segmentler, _ = self.model.transcribe(
            ses, language="tr", beam_size=1, temperature=0.0, condition_on_previous_text=False,
            vad_filter=False, no_speech_threshold=0.6, log_prob_threshold=-1.0, initial_prompt=self.ipucu)
        parcalar = list(segmentler)
        konusma_suresi = len(ses) / float(ORNEK_HIZI)
        metin = " ".join(p.text.strip() for p in parcalar).strip()
        gecen = time.time() - t0
        if not parcalar or not metin:
            return "", 0.0, gecen
        guven = math.exp(sum(p.avg_logprob for p in parcalar) / len(parcalar))
        if max(p.no_speech_prob for p in parcalar) > 0.7:
            guven *= 0.5
        if halusinasyon_mu(metin, konusma_suresi, self.ipucu):
            return "", 0.0, gecen
        return metin, max(0.0, min(1.0, guven)), gecen

    def kapat(self):
        self.mikrofonu_kapat()
