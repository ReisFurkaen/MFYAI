"""
MFY AI - Hafıza Onarım Aracı
Çalıştırmadan ÖNCE arayüzü / programı kapat (veritabanı dosyası kilitli olabilir).

    python hafiza_onar.py

Ne yapar:
  1) Veritabanının YEDEĞİNİ alır (mfy_chroma_db_yedek_<tarih> klasörü).
  2) Eski sohbet kayıtlarını tarar; asistanın "yapamıyorum / kontrol edemiyorum / bilmiyorum", ham araç çağrısı
     ya da eski araç listesi içeren BOZUK kayıtlarını bulur (bunlar modeli yanıltır).
  3) Sana gösterir, onay verirsen siler.
"""
import os
import shutil
import collections
from datetime import datetime

import config
import hafiza

KOLEKSIYON = "mfy_rag_memory"


def onizleme(metin: str, n: int = 90) -> str:
    return " ".join((metin or "").split())[:n]


def main():
    import chromadb

    if not os.path.isdir(config.CHROMA_YOLU):
        print("Hafıza veritabanı klasörü bulunamadı, yapılacak bir şey yok.")
        return

    yedek = f"{config.CHROMA_YOLU}_yedek_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"Yedek alınıyor: {yedek}")
    shutil.copytree(config.CHROMA_YOLU, yedek)

    istemci = chromadb.PersistentClient(path=config.CHROMA_YOLU)
    try:
        koleksiyon = istemci.get_collection(KOLEKSIYON)
    except Exception as e:
        print(f"Koleksiyon açılamadı: {e}")
        return

    veri = koleksiyon.get(include=["documents", "metadatas"])
    ids, belgeler, metalar = veri["ids"], veri["documents"], veri["metadatas"]
    print(f"Toplam {len(ids)} parça bulundu.\n")

    kayitlar = collections.defaultdict(list)
    for parca_id, belge, meta in zip(ids, belgeler, metalar):
        meta = meta or {}
        kayit_id = meta.get("kayit_id") or parca_id
        kayitlar[kayit_id].append((int(meta.get("parca_index", 0) or 0), parca_id, belge or ""))

    kotu = []   # (neden, onizleme, [parça id'leri])
    for kayit_id, parcalar in kayitlar.items():
        parcalar.sort(key=lambda x: x[0])
        birlesik = "\n".join(p[2] for p in parcalar)
        kullanici, asistan = hafiza.kayit_ayir(birlesik)
        neden = hafiza.kotu_kayit_mu(kullanici, asistan) if kullanici else (
            "yetersizlik / ret cevabı" if hafiza.kotu_icerik_mi(birlesik) else None)
        if neden:
            kotu.append((neden, onizleme(kullanici or birlesik), [p[1] for p in parcalar]))

    toplam_kayit = len(kayitlar)
    print(f"{toplam_kayit} sohbet kaydından {len(kotu)} tanesi bozuk görünüyor:\n")
    for neden, ozet, _ in kotu[:40]:
        print(f"  - [{neden}] {ozet}")
    if len(kotu) > 40:
        print(f"  ... ve {len(kotu) - 40} tane daha")

    print("\nNe yapmak istersin?")
    print("  1) Akıllı temizlik: yalnızca yukarıdaki bozuk kayıtları sil (önerilen)")
    print("  2) Tüm sohbet hafızasını sıfırla (profil.json'a dokunulmaz)")
    print("  3) Hiçbir şey yapma, çık")
    secim = input("Seçim (1/2/3): ").strip()

    if secim == "1":
        silinecek = [i for _, _, idler in kotu for i in idler]
        if not silinecek:
            print("Silinecek bozuk kayıt yok.")
            return
    elif secim == "2":
        if input("Tüm sohbet hafızası silinecek. Onaylamak için EVET yaz: ").strip() != "EVET":
            print("Vazgeçildi.")
            return
        silinecek = list(ids)
    else:
        print("Çıkılıyor, hiçbir şey silinmedi.")
        return

    for i in range(0, len(silinecek), 500):
        koleksiyon.delete(ids=silinecek[i:i + 500])
    print(f"\n{len(silinecek)} parça silindi. Kalan parça sayısı: {koleksiyon.count()}")
    print(f"Yedeğin burada duruyor (sorun olursa klasörü geri koyabilirsin): {yedek}")


if __name__ == "__main__":
    main()
