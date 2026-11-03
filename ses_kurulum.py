"""
MFY AI - Ses Kurulumu ve Ölçümü
Çalıştır:   python ses_kurulum.py          (arayüz KAPALIYKEN, internet açıkken)

Ne yapar:
  1) Gerekli paketlerin kurulu olup olmadığını kontrol eder
  2) Ses modellerini indirir (Pocket TTS ~440 MB, Whisper large-v3-turbo ~1,6 GB). Sadece bir kez gerekir.
  3) Hoparlörünü dener: asistanın sesini duyarsın
  4) KENDİ bilgisayarında hız ölçer (ses üretme ve yazıya çevirme) ve ayar önerir
  5) İstersen mikrofonunu dener

Not: beyin.py HuggingFace'i çevrimdışı moda aldığı için modellerin indirilmesi BU scriptle yapılır.
"""
import os
import sys
import time
import importlib.util

os.environ.pop("HF_HUB_OFFLINE", None)          # indirme için çevrimdışı modu kapat
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

import config  # noqa: E402

CUMLE = "Merhaba! Ben MFY AI. Chrome'dan YouTube'da bir şarkı açmamı ister misin?"
BASLIK = "=" * 62


def baslik(metin):
    print(f"\n{BASLIK}\n{metin}\n{BASLIK}")


def paket_var(ad):
    return importlib.util.find_spec(ad) is not None


def main():
    baslik("1) PAKET KONTROLÜ")
    paketler = [("numpy", "numpy"), ("sounddevice", "sounddevice"), ("faster_whisper", "faster-whisper"),
                ("pocket_tts_turkish", "pocket-tts-turkish"), ("silero_vad", "silero-vad")]
    eksik = []
    for modul, pip_adi in paketler:
        var = paket_var(modul)
        print(f"  {'OK   ' if var else 'EKSİK'} {pip_adi}")
        if not var:
            eksik.append(pip_adi)
    if eksik:
        zorunlu = [p for p in eksik if p != "silero-vad"]
        if zorunlu:
            print("\nÖnce şunu çalıştır, sonra bu scripti yeniden başlat:")
            print("  pip install " + " ".join(eksik))
            return
        print("\n  Not: silero-vad yok. Sistem yine çalışır (basit ses algılama kullanılır) ama gürültülü ortamda "
              "daha az başarılı olur. İstersen: pip install silero-vad")

    import numpy as np
    import sounddevice as sd

    baslik("2) SES CİHAZLARI")
    try:
        giris, cikis = sd.default.device
        aygitlar = sd.query_devices()
        print(f"  Varsayılan mikrofon : {aygitlar[giris]['name'] if giris is not None and giris >= 0 else 'YOK'}")
        print(f"  Varsayılan hoparlör : {aygitlar[cikis]['name'] if cikis is not None and cikis >= 0 else 'YOK'}")
    except Exception as e:
        print(f"  Cihazlar okunamadı: {e}")

    baslik("3) KONUŞMA SESİ (Pocket TTS Turkish) - ilk seferde model iner")
    from pocket_tts_turkish import TurkishTTS
    cihaz = getattr(config, "SES_TTS_CIHAZ", "cpu")
    ses = getattr(config, "SES_TTS_SES", "female_2")
    t0 = time.time()
    tts = TurkishTTS.from_pretrained(device=cihaz)
    print(f"  Model yüklendi ({cihaz}): {time.time() - t0:.1f} sn")
    list(tts.stream("Isınma.", voice=ses))
    t0 = time.time()
    ilk, parcalar = None, []
    for parca in tts.stream(CUMLE, voice=ses):
        if ilk is None:
            ilk = time.time() - t0
        parcalar.append(np.asarray(parca, dtype=np.float32).reshape(-1))
    toplam = time.time() - t0
    ses_dizisi = np.concatenate(parcalar)
    sure = len(ses_dizisi) / tts.sample_rate
    print(f"  İlk ses parçası : {ilk * 1000:.0f} ms")
    print(f"  Toplam üretim   : {toplam:.2f} sn  ({sure:.1f} sn'lik ses -> hız {sure / toplam:.1f}x gerçek zaman)")
    if sure / toplam < 1.3:
        print("  ⚠️ Üretim gerçek zamana yakın ya da yavaş: konuşma kesik kesik olabilir.")
        print("     Çözüm: config.py içine  SES_TTS_CIHAZ = \"cuda\"  yaz (GPU belleği yeterliyse).")
    print("\n  Şimdi hoparlörden bir cümle çalacağım, dinle:")
    print(f"  \"{CUMLE}\"")
    sd.play(ses_dizisi, tts.sample_rate)
    sd.wait()
    onay = input("\n  Sesi duydun mu? (e/h): ").strip().lower()
    if onay.startswith("h"):
        print("  Hoparlör sorunu olabilir: Windows ses ayarlarında doğru çıkış cihazını seçtiğinden emin ol.")

    baslik("4) KONUŞMA TANIMA (Whisper) - ilk seferde model iner (~1,6 GB, sabırlı ol)")
    from faster_whisper import WhisperModel
    model_adi = getattr(config, "SES_STT_MODEL", "large-v3-turbo")
    stt_cihaz = getattr(config, "SES_STT_CIHAZ", "cpu")
    hesap = getattr(config, "SES_STT_HESAP", "int8")
    kwargs = {"device": "cuda" if stt_cihaz == "cuda" else "cpu",
              "compute_type": "int8_float16" if stt_cihaz == "cuda" else hesap}
    if kwargs["device"] == "cpu":
        kwargs["cpu_threads"] = max(2, (os.cpu_count() or 4) // 2)
    t0 = time.time()
    stt = WhisperModel(model_adi, **kwargs)
    print(f"  Model yüklendi ({model_adi}, {kwargs['device']}): {time.time() - t0:.1f} sn")
    list(stt.transcribe(np.zeros(16000, dtype=np.float32), language="tr", beam_size=1)[0])

    # Asistanın kendi sesini 16 kHz'e çevirip geri yazıya çevir (mikrofon gerekmeden uçtan uca test)
    try:
        from scipy.signal import resample_poly
        ses16 = resample_poly(ses_dizisi, 2, 3).astype(np.float32)
    except Exception:
        x = np.arange(0, len(ses_dizisi), 1.5)
        ses16 = np.interp(x, np.arange(len(ses_dizisi)), ses_dizisi).astype(np.float32)
    t0 = time.time()
    segmentler, _ = stt.transcribe(ses16, language="tr", beam_size=1, temperature=0.0)
    metin = " ".join(s.text.strip() for s in segmentler)
    gecen = time.time() - t0
    sure16 = len(ses16) / 16000
    print(f"  Okunan cümle : {CUMLE}")
    print(f"  Duyulan      : {metin}")
    print(f"  Çözümleme    : {gecen:.2f} sn ({sure16:.1f} sn'lik konuşma için)")
    if gecen > 3.5:
        print("\n  ⚠️ Konuşma tanıma yavaş: cevapların başlaması gecikir. Seçenekler (config.py'ye yaz):")
        print("     SES_STT_MODEL = \"small\"      # çok daha hızlı, biraz daha az doğru")
        print("     SES_STT_CIHAZ = \"cuda\"       # GPU'da boş yer varsa (LM Studio modeli yüklüyken çoğu zaman yetmez)")
    else:
        print("  ✅ Hız yeterli.")

    baslik("5) MİKROFON TESTİ (isteğe bağlı)")
    cevap = input("  Mikrofonu denemek ister misin? 4 saniye kayıt yapacağım (e/h): ").strip().lower()
    if cevap.startswith("e"):
        print("  Şimdi konuş: örneğin 'Chrome'u aç ve YouTube'a git' ...")
        kayit = sd.rec(int(4 * 16000), samplerate=16000, channels=1, dtype="float32")
        sd.wait()
        kayit = kayit.reshape(-1)
        seviye = float(np.sqrt(np.mean(np.square(kayit))))
        print(f"  Ses seviyesi (RMS): {seviye:.4f}  " + ("(çok düşük: mikrofon sessiz ya da yanlış cihaz)" if seviye < 0.003 else "(iyi)"))
        segmentler, _ = stt.transcribe(kayit, language="tr", beam_size=1, temperature=0.0)
        print(f"  Duyulan: {' '.join(s.text.strip() for s in segmentler)}")

    baslik("ÖZET")
    print("  Kurulum tamam. Arayüzü açabilirsin: python arayuz.py")
    print("  İlk kullanımda ses sistemi arka planda yüklenir (birkaç saniye).")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nİptal edildi.")
        sys.exit(1)
