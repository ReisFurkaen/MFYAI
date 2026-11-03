"""
MFY AI - Ekran / Fare Testi
Çalıştır:  python ekran_testi.py
Ekranı görme, öğe bulma ve fare hareketini TIKLAMADAN dener.
Hata ayıklama açıktır: modelin ham cevapları yazdırılır, tahmin edilen nokta
calisma_alani/ekran_debug/ klasörüne işaretli resim olarak kaydedilir (kırmızı = ilk tahmin, yeşil = doğrulanmış).
"""
import time
import traceback

import config
import izinler

config.VIZYON_DEBUG = True
izinler.onay_kaynagini_ayarla(lambda a: input(f"\n⚠️ ONAY:\n{a}\n(e/h): ").strip().lower() in ("e", "evet"))


def adim(ad, fonksiyon):
    print(f"\n[...] {ad}", flush=True)
    t0 = time.time()
    try:
        fonksiyon()
        print(f"[OK ] ({time.time() - t0:.1f} sn)", flush=True)
    except Exception:
        print(f"[HATA] ({time.time() - t0:.1f} sn)\n{traceback.format_exc()}", flush=True)


def bul(E, tarif, dogrula):
    config.VIZYON_DOGRULA = dogrula
    print("     ", E.ekranda_bul.invoke({"tarif": tarif, "pencere": "", "imleci_goster": True}))


def main():
    from araclar import ekran_ajan as E

    adim("1) Fare ve ekran bilgisi", lambda: print("     ", E.fare_konumu.invoke({"bos_girdi": ""})))
    adim("2) Ekranı incele (görüntü destekli model gerekir)",
         lambda: print("     ", E.ekrani_incele.invoke({"soru": "Ekranda ne var? Kısaca anlat.", "pencere": ""})))

    tarif = "Görev çubuğundaki Windows Başlat düğmesi (Windows logosu)"
    adim("3) Öğe bul, DOĞRULAMASIZ: ham tahmin (imleç oraya gider, TIKLAMAZ)", lambda: bul(E, tarif, False))
    print("\n  >>> İmleç Başlat düğmesinin yakınında mı? Resim: calisma_alani/ekran_debug/bul_sonuc.png")
    time.sleep(2)
    adim("4) Öğe bul, DOĞRULAMALI", lambda: bul(E, tarif, True))
    print("\nTest bitti. Çıktıyı (ve istersen ekran_debug resimlerini) gönderebilirsin.")


if __name__ == "__main__":
    main()
