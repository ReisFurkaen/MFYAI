"""
MFY AI - Araç Zinciri Testi
Çalıştır:  python arac_testi.py
Sorunun nerede olduğunu gösterir: araç mı bozuk, bağlantı mı eksik, seçici mi eler, model mi çağırmıyor?
"""
import time
import traceback

MESAJ = "Not defterini aç"


def adim(ad, fonksiyon):
    print(f"\n[...] {ad}", flush=True)
    baslangic = time.time()
    try:
        sonuc = fonksiyon()
        print(f"[OK ] ({time.time() - baslangic:.1f} sn)", flush=True)
        return sonuc
    except Exception:
        print(f"[HATA] ({time.time() - baslangic:.1f} sn)", flush=True)
        print(traceback.format_exc(), flush=True)
        return None


def arac_dogrudan():
    from araclar import programlar
    print("      programlar.py içindeki araçlar:", [t.name for t in programlar.ARACLAR])
    sonuc = programlar.uygulama_ac.invoke({"uygulama_adi": "not defteri"})
    print("      uygulama_ac sonucu:", sonuc)
    print("      >>> Not Defteri açıldı mı? (Açıldıysa kapat.)")


def beyin_yukle():
    import beyin
    adlar = [t.name for t in beyin.tools]
    print(f"      beyin.tools içinde {len(adlar)} araç var.")
    print("      uygulama_ac beyin'e bağlı mı:", "uygulama_ac" in adlar)
    print("      Araç seçici (_ajan_sec) bağlı mı:", hasattr(beyin, "_ajan_sec"))
    return beyin


def secici_testi(beyin):
    import arac_secici
    secilen = arac_secici.arac_sec(MESAJ, beyin.tools)
    return secilen


def model_dogrudan(beyin, secilen):
    """Ajan katmanı olmadan: model, seçilen araçlarla 'tool call' üretiyor mu?"""
    cevap = beyin.llm.bind_tools(secilen).invoke(MESAJ)
    print("      Modelin metin cevabı:", repr(cevap.content[:200]))
    print("      Modelin araç çağrıları:", cevap.tool_calls)
    if not cevap.tool_calls:
        print("      >>> Model araç ÇAĞIRMADI. (Sorun model/ayar tarafında)")


def tam_ajan(beyin):
    ajan = beyin._ajan_sec(MESAJ) if hasattr(beyin, "_ajan_sec") else beyin.asistan
    sonuc = ajan.invoke({
        "input": MESAJ,
        "context": "(yok)",
        "chat_history": [],
        "profil": "(Test için kullanıcı profili kullanılmıyor.)",
        "ses_kipi": "",
    })
    print("      Nihai cevap:", sonuc["output"][:300])


if __name__ == "__main__":
    adim("1) Araç doğrudan çalıştırılıyor (Not Defteri açılmalı)", arac_dogrudan)
    beyin = adim("2) beyin.py yükleniyor ve araç bağlantısı kontrol ediliyor", beyin_yukle)
    if beyin is not None:
        secilen = adim(f"3) Araç seçici: '{MESAJ}' için hangi araçlar seçiliyor?", lambda: secici_testi(beyin))
        if secilen:
            adim("4) Model doğrudan: araç çağrısı üretiyor mu?", lambda: model_dogrudan(beyin, secilen))
        adim("5) Tam ajan çalıştırılıyor (Invoking: satırı görünmeli)", lambda: tam_ajan(beyin))
    print("\nTest bitti. Tüm çıktıyı kopyalayıp gönder.")
