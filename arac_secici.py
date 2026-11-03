"""
MFY AI - Araç Seçici
Küçük modeller çok fazla araç görünce şaşırır. Bu modül mesajdaki kelimelere bakıp modele sadece
ilgili araç gruplarını gösterir. Gruplar mesajla ne kadar örtüştüğüne göre PUANLANIR ve modele aynı anda
en fazla MAKS_ARAC araç gösterilir.

Anahtar kelime kuralları (Türkçe karakterler otomatik sadeleştirilir: ş->s, ı->i ...):
  "kelime"   -> mesajda tam bu kelime geçerse eşleşir
  "kelime*"  -> bu kelimeyle BAŞLAYAN herhangi bir kelime eşleşir (örn. "dosya*" -> dosyayi, dosyalar)
Yeni bir yetenek eklediğinde aracın adını uygun gruba yazman yeterli.
"""
import re

MAKS_ARAC = 30

_TABLO = str.maketrans({
    "ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g", "ı": "i", "İ": "i", "I": "i",
    "ö": "o", "Ö": "o", "ş": "s", "Ş": "s", "ü": "u", "Ü": "u",
})

# Her mesajda her zaman verilen araçlar
CEKIRDEK = ["get_time", "powershell_calistir", "run_python_code"]

# Hiçbir grup eşleşmezse (sohbet, genel soru) verilen araçlar
VARSAYILAN = ["duckduckgo_search", "calculator"]

GRUPLAR = {
    "uygulama": {
        "araclar": ["uygulama_ac", "pencere_duzenle", "kurulu_programlar", "islem_kontrol", "acik_pencereler"],
        "kelimeler": [
            "ac", "acsana", "acar*", "acabilir*", "calistir*", "baslat*", "uygulama*", "program*", "chrome*",
            "edge*", "firefox*", "spotify*", "discord*", "steam*", "word*", "excel*", "powerpoint*", "notepad*",
            "not", "hesap", "paint*", "vscode*", "kapat*", "kapatsana", "kurulu*", "yuklu*",
        ],
    },
    "tarayici": {
        "araclar": ["youtube_ac", "site_ac", "spotify_ara"],
        "kelimeler": [
            "youtube*", "site*", "tarayici*", "chrome*", "edge*", "firefox*", "google*", "spotify*", "sarki*",
            "muzik*", "video*", "izle*", "dinle*", "cal", "calsana", "web*", "url*", "link*", "git", "gir",
            "klip*", "album",
        ],
    },
    "ses_medya": {
        "araclar": ["ses_kontrol", "medya_kontrol", "ekran_parlakligi"],
        "kelimeler": [
            "ses", "sesi", "sesini", "ses*", "sessiz*", "sustur*", "kis", "kissana", "arttir*", "artir*",
            "azalt*", "yukselt*", "alcalt*", "volume", "mute", "medya*", "duraklat*", "durdur*", "devam",
            "sonraki", "onceki", "gecir*", "parlaklik*", "parlak*", "karart*", "aydinlat*", "hoparlor*", "muzik*",
        ],
    },
    "pencere_klavye": {
        "araclar": ["pencere_duzenle", "yaz", "tus_bas", "ekran_goruntusu", "acik_pencereler",
                    "aktif_pencere", "masaustunu_goster", "panoyu_oku", "panoya_yaz"],
        "kelimeler": [
            "pencere*", "yaz", "yazsana", "yazdir*", "tus*", "kisayol*", "bas", "bassana", "kopyala*", "yapistir*",
            "pano*", "ekran*", "goruntu*", "screenshot", "masaustunu*", "kucult*", "buyut*", "yasla*", "one",
            "getir*", "enter", "ctrl*", "alt", "aktif*", "ustte*",
        ],
    },
    "ekran_ajan": {
        "araclar": ["ekrani_incele", "tarifle_tikla", "yaz", "tus_bas", "ogeye_tikla", "fare_kaydir", "ekranda_bul",
                    "arayuz_ogeleri", "fare_tikla", "bekle", "fare_surukle", "fare_konumu", "aktif_pencere",
                    "pencere_duzenle", "acik_pencereler"],
        "kelimeler": [
            "ekran*", "gor", "gorsene", "goruyor*", "gorun*", "bak*", "tikla*", "fare*", "mouse", "imlec*",
            "kaydir*", "surukle*", "sekme*", "buton*", "dugme*", "menu*", "simge*", "ikon*", "secenek*",
            "yazan", "yaziyor", "incele*", "analiz*", "sayfa*", "pencerede", "otomatik*", "kutu*", "kutusuna",
        ],
    },
    "sistem": {
        "araclar": ["get_system_status", "ag_durumu", "disk_durumu", "pil_durumu", "islemler_listele",
                    "get_detailed_hardware_info", "islem_kontrol", "ekran_parlakligi"],
        "kelimeler": [
            "cpu", "ram", "gpu", "islemci*", "donanim*", "sistem*", "bellek*", "islem*", "kullanim*", "performans*",
            "yavas*", "kasiyor*", "sicaklik*", "bilgisayar*", "pil*", "sarj*", "batarya*", "disk*", "depolama*",
            "bos", "alan*", "internet*", "wifi", "ag", "baglanti*", "ip", "ping", "durum*", "yuzde*",
        ],
    },
    "guc": {
        "araclar": ["guc_islemi", "bilgisayari_kilitla", "guc_iptal"],
        "kelimeler": [
            "kilitle*", "kilit*", "uyut*", "uyku*", "yeniden", "restart", "oturum*", "shutdown",
            "iptal*", "guc*", "pc",
        ],
    },
    "bildirim": {
        "araclar": ["hatirlatici_kur", "bildirim_gonder", "hatirlaticilari_listele", "hatirlatici_iptal"],
        "kelimeler": [
            "hatirlatma*", "hatirlatici*", "hatirlat", "hatirlatsana", "bildirim*", "uyar*", "alarm*",
            "zamanlayici*", "dakika*", "saniye*", "sonra", "bildir*", "haber",
        ],
    },
    "dosya_oku": {
        "araclar": ["dosya_listele", "dosya_ara", "dosya_oku", "dosya_ac", "klasor_ac", "dosya_bilgisi", "klasor_yolu_bul"],
        "kelimeler": [
            "dosya*", "klasor*", "indirilenler*", "indirmeler*", "masaustu*", "belgeler*", "resimler*", "videolar*",
            "listele*", "oku*", "ara", "arat*", "bul", "bulsana", "dizin*", "boyut*", "buyuk*", "icinde*",
            "icerik*", "ne var",
        ],
    },
    "dosya_duzenle": {
        "araclar": ["dosya_sil", "dosya_tasi", "dosya_kopyala", "dosya_yaz", "klasor_olustur", "klasor_duzenle",
                    "duzenlemeyi_geri_al", "klasor_yolu_bul", "dosya_ara"],
        "kelimeler": [
            "sil*", "silsene", "kaldir*", "tasi*", "kopyala*", "kopya*", "olustur*", "yaz", "kaydet*", "duzenle*",
            "duzenleme*", "organize*", "temizle*", "geri", "isim*", "adlandir*", "yeni", "klasor*", "dosya*",
            "cop*", "dagin*", "topla*",
        ],
    },
    "komut": {
        "araclar": ["powershell_calistir", "run_python_code", "yonetici_olarak_calistir"],
        "kelimeler": [
            "powershell*", "komut*", "terminal*", "cmd", "script*", "python*", "kod*", "calistir*", "batch",
            "ipconfig", "pip", "winget", "yukle*",
        ],
    },
    "hesap": {
        "araclar": ["calculator"],
        "kelimeler": [
            "hesapla*", "kac", "carp*", "topla*", "bol", "kok", "us", "yuzde*", "eder", "islem*",
        ],
    },
    "web": {
        "araclar": ["duckduckgo_search"],
        "kelimeler": [
            "internet*", "web*", "haber*", "hava*", "arastir*", "guncel*", "bugun*", "dun", "dolar*", "euro",
            "fiyat*", "kimdir", "nedir", "son", "yeni", "ara", "arama*", "mac*", "skor*",
        ],
    },
    "sistem_ileri": {
        "araclar": ["servis_listele", "servis_islem", "olay_gunlugu", "kayit_defteri_oku", "kayit_defteri_yaz",
                    "kayit_defteri_sil", "islem_detay", "islem_kontrol", "wmi_sorgu", "kurulu_programlar",
                    "baslangic_programlari", "zamanlanmis_gorevler", "zamanli_gorev_olustur", "zamanli_gorev_sil",
                    "ortam_degiskeni", "yonetici_olarak_calistir", "ekran_bilgisi", "yazicilar_listele", "dosya_yazdir"],
        "kelimeler": [
            "servis*", "hizmet*", "registry", "regedit", "kayit*", "olay*", "gunluk*", "wmi", "yonetici*", "admin*",
            "zamanlanmis*", "gorev*", "baslangic*", "ortam*", "degisken*", "yazici*", "yazdir*", "kurulu*", "yuklu*",
            "program*", "surec*", "pid", "oncelik*", "askiya*", "donanim*", "usb", "bios", "anakart*", "surucu*",
            "monitor*", "cozunurluk*", "dondur*", "hata*",
        ],
    },
    "dosya_ileri": {
        "araclar": ["dosya_ara", "dosya_listele", "dosya_oku", "klasor_boyutlari", "yinelenen_dosyalar", "dosya_hash",
                    "arsiv_olustur", "arsiv_ac", "dosya_kalici_sil", "toplu_yeniden_adlandir", "sqlite_sorgu"],
        "kelimeler": [
            "icinde", "agac*", "boyut*", "buyuk*", "yer", "kaplayan*", "zip", "arsiv*", "rar", "sikistir*", "hash",
            "sha*", "md5", "kalici*", "yeniden", "adlandir*", "yinelen*", "kopya*", "ayni", "pdf", "docx", "word",
            "pptx", "excel", "xlsx", "belge*", "sqlite", "veritabani*", "db", "sorgu*", "oku*", "ozetle*",
        ],
    },
    "ag_web": {
        "araclar": ["web_sayfasi_oku", "http_istegi", "wikipedia_ara", "dosya_indir", "ip_bilgisi", "ping_at",
                    "port_kontrol", "dns_sorgu", "ag_baglantilari", "ag_trafigi", "duckduckgo_results_json",
                    "wikipedia", "arxiv", "youtube_search", "duckduckgo_search"],
        "kelimeler": [
            "http*", "api", "indir*", "download", "wikipedia", "vikipedi", "ip", "ping", "port*", "dns", "baglanti*",
            "trafik*", "sayfa*", "sayfayi", "url", "link*", "makale*", "arxiv", "ara*", "arastir*", "site*",
        ],
    },
    "medya": {
        "araclar": ["ses_cihazlari", "mikrofon_kaydet", "ses_cal", "ses_dosyasini_yaziya_cevir",
                    "metni_sese_cevir", "gorsel_bilgisi", "gorsel_donustur"],
        "kelimeler": [
            "mikrofon*", "cihaz*", "kayit*", "wav", "mp3", "gorsel*", "resim*", "foto*",
            "boyutlandir*", "kucult*", "donustur*", "jpg", "png", "webp", "yaziya", "transkript*", "seslendir*",
            "toplanti*",
        ],
    },
    "hafiza": {
        "araclar": ["hatirla", "unut", "profilimi_goster"],
        "kelimeler": [
            "hatirla", "hatirlasana", "unut", "unutma", "unutsana", "profil*", "hafiza*",
            "beni", "benim", "adim", "ismim", "hakkimda", "taniyor*", "biliyor*",
        ],
    },
}

# Son seçimde eşleşen gruplar (beyin.py "işlem istendi mi?" kontrolü için okur)
SON_GRUPLAR: list = []
# Bu gruplar araç ÇAĞIRMADAN doğru cevaplanamayacak istekleri temsil eder
EYLEM_GRUPLARI = {"uygulama", "tarayici", "ses_medya", "pencere_klavye", "ekran_ajan", "guc", "bildirim",
                  "dosya_duzenle", "komut"}


EYLEM_GRUPLARI |= {"sistem_ileri", "dosya_ileri", "medya"}


def _kelimeler(mesaj: str) -> list:
    return re.findall(r"[a-z0-9]+", mesaj.translate(_TABLO).lower())


def _eslesir(kural: str, mesaj_kelimeleri: list) -> bool:
    if kural.endswith("*"):
        kok = kural[:-1]
        return any(k.startswith(kok) for k in mesaj_kelimeleri)
    return kural in mesaj_kelimeleri


def arac_sec(mesaj: str, tum_araclar: list) -> list:
    """Mesaja uygun araç listesini döndürür."""
    global SON_GRUPLAR
    kelimeler = _kelimeler(mesaj)

    puanlar = []
    for sira, (ad, grup) in enumerate(GRUPLAR.items()):
        puan = sum(1 for k in grup["kelimeler"] if _eslesir(k, kelimeler))
        if puan:
            if ad in EYLEM_GRUPLARI:
                puan += 0.5      # eşitlikte işlem yapan grup, salt okuyan gruptan önce gelsin
            puanlar.append((puan, -sira, ad))
    puanlar.sort(reverse=True)   # önce yüksek puan, eşitlikte tanım sırası

    mevcut_adlar = {t.name for t in tum_araclar}
    secilen_adlar = [a for a in CEKIRDEK if a in mevcut_adlar]
    eslesen = []
    for puan, _, ad in puanlar:
        for arac in GRUPLAR[ad]["araclar"]:          # gruptaki araçlar ÖNCELİK SIRASIYLA eklenir
            if arac in mevcut_adlar and arac not in secilen_adlar:
                if len(secilen_adlar) >= MAKS_ARAC:
                    break                             # sert sınır: model aynı anda en fazla MAKS_ARAC araç görür
                secilen_adlar.append(arac)
        eslesen.append(ad)

    if not eslesen:
        secilen_adlar.extend(a for a in VARSAYILAN if a in mevcut_adlar and a not in secilen_adlar)

    SON_GRUPLAR = eslesen
    secilen = [t for t in tum_araclar if t.name in secilen_adlar]
    print(f"🧰 Eşleşen gruplar: {eslesen or ['(varsayılan)']} | Araçlar ({len(secilen)}): {[t.name for t in secilen]}")
    return secilen


def eylem_mesaji_mi(mesaj: str) -> bool:
    """Yan etkisiz kontrol: bu mesaj araç gerektiren bir işlem isteği gibi mi? (arayüz, sesli akış kararı için kullanır)"""
    kelimeler = _kelimeler(mesaj)
    for ad, grup in GRUPLAR.items():
        if ad in EYLEM_GRUPLARI and any(_eslesir(k, kelimeler) for k in grup["kelimeler"]):
            return True
    return False


def eylem_istegi_mi() -> bool:
    """Son mesaj, araç gerektiren bir işlem isteği gibi görünüyor mu?"""
    return any(g in EYLEM_GRUPLARI for g in SON_GRUPLAR)
