"""
MFY AI - Konuşma Stili
Yazılı cevabı SESLİ okunmaya hazırlar:
  * etiket_temizle / konusmaya_hazirla : <think>, kod blokları, markdown, link, emoji gibi okunmaması gerekenleri temizler
  * CumleBolucu                        : Akan metni cümle cümle böler (ilk cümle bitince konuşma başlayabilir)
  * duygu_sec / etiketi_ayir           : Cümleye uygun duygu etiketini (mutlu, üzgün, şaşkın, sakin) seçer
  * DOLGU / dolgu_sec                  : "Hemen hallediyorum", "Tam duyamadım" gibi insani kısa tepkiler
  * kisalt                             : Çok uzun cevabın sadece başını okur, gerisini "ekrana yazdım" der

Bu dosya bilerek HAFİFTİR (ağır bağımlılık yok).
"""
import re
import random
import difflib

_TR_TABLO = str.maketrans({
    "ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g", "ı": "i", "İ": "i", "I": "i",
    "ö": "o", "Ö": "o", "ş": "s", "Ş": "s", "ü": "u", "Ü": "u",
})


def sade(metin: str) -> str:
    return (metin or "").translate(_TR_TABLO).lower()


# ============================================================
# TEMİZLEME
# ============================================================
_ETIKET_TAMAM = re.compile(r"<(think|tool_call)>.*?</\1>", re.DOTALL | re.IGNORECASE)
_ETIKET_ACIK = re.compile(r"<(think|tool_call)>.*$", re.DOTALL | re.IGNORECASE)
_KOD_BLOGU = re.compile(r"```.*?```", re.DOTALL)
_KOD_ACIK = re.compile(r"```.*$", re.DOTALL)
_SATIR_ICI_KOD = re.compile(r"`([^`]*)`")
_MD_BAGLANTI = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_URL = re.compile(r"(?:https?://|www\.)\S+")
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\U0001F1E6-\U0001F1FF\u200d\ufe0f]")
_BASLIK = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]*", re.MULTILINE)
_LISTE = re.compile(r"^[ \t]*(?:[-*•·]|\d{1,2}[.)])[ \t]+", re.MULTILINE)
_TABLO_CIZGI = re.compile(r"^[ \t]*\|?[ \t:|-]{3,}\|?[ \t]*$", re.MULTILINE)
_VURGU = re.compile(r"(\*\*|__|\*|~~)")
_DUYGU_BASTA = re.compile(r"^\s*\[(mutlu|üzgün|kızgın|şaşkın|sakin|happy|sad|angry|surprised|calm)\][ \t]*", re.IGNORECASE)


def etiket_temizle(metin: str) -> str:
    """Modelin <think> ve <tool_call> bloklarını (tamamlanmış ya da yarım) çıkarır. Başı/sonu kırpmaz."""
    metin = metin or ""
    if "</think>" in metin and "<think>" not in metin:
        metin = metin.split("</think>", 1)[1]
    metin = _ETIKET_TAMAM.sub("", metin)
    metin = _ETIKET_ACIK.sub("", metin)
    son = metin.rfind("<")                       # yarım kalmış etiket başlangıcı ("<thi") okunmasın
    if son != -1 and ">" not in metin[son:] and len(metin) - son <= 12:
        metin = metin[:son]
    return metin


def konusmaya_hazirla(metin: str) -> str:
    """Bir cümleyi/parçayı sesli okunacak düz metne çevirir."""
    m = etiket_temizle(metin)
    m = _KOD_BLOGU.sub(" ", m)
    m = _KOD_ACIK.sub(" ", m)
    m = _SATIR_ICI_KOD.sub(r"\1", m)
    m = _MD_BAGLANTI.sub(r"\1", m)
    m = _URL.sub("bağlantı", m)
    m = _BASLIK.sub("", m)
    m = _TABLO_CIZGI.sub("", m)
    m = _LISTE.sub("", m)
    m = m.replace("|", ", ")
    m = _VURGU.sub("", m)
    m = re.sub(r"(?<=\w)_(?=\w)", " ", m)        # ses_kontrol -> ses kontrol
    m = m.replace("→", ", ").replace("=>", ", ").replace("->", ", ").replace("&", " ve ")
    m = _EMOJI.sub("", m)
    m = _DUYGU_BASTA.sub("", m)
    m = re.sub(r"[ \t]+", " ", m)
    m = re.sub(r"\n{2,}", "\n", m)
    return m.strip()


# ============================================================
# DUYGU
# ============================================================
_DUYGU_KURALLARI = [
    ("şaşkın", ["vay", "inanilmaz", "sasirtici", "gercekten mi", "yok artik", "hayret", "beklemiyordum"]),
    ("üzgün", ["maalesef", "uzgunum", "yazik", "ne yazik", "basaramadim", "yapamadim", "hata olustu",
               "sorun cikti", "gerceklestiremedim", "ulasamadim"]),
    ("mutlu", ["harika", "super", "mukemmel", "tebrikler", "guzel haber", "sevindim", "cok guzel", "yasasin",
               "hos geldin", "gunaydin", "ne guzel"]),
    ("sakin", ["merak etme", "endiselenme", "sorun degil", "sakin ol", "acelen yok", "onemli degil", "rahat ol"]),
]


def etiketi_ayir(cumle: str):
    """Cümle başındaki [mutlu] gibi etiketi ayırır. Döner: (duygu_veya_None, kalan_metin)"""
    m = _DUYGU_BASTA.match(cumle or "")
    if not m:
        return None, cumle
    return m.group(1).lower(), cumle[m.end():]


def duygu_sec(metin: str):
    """Cümlenin içeriğine göre duygu etiketi seçer; belirgin bir şey yoksa None (nötr ses)."""
    s = sade(metin)
    for duygu, kaliplar in _DUYGU_KURALLARI:
        if any(k in s for k in kaliplar):
            return duygu
    return None


# ============================================================
# DOLGU / KISA TEPKİLER (insani his)
# ============================================================
DOLGU = {
    # İşlem yapılacağı zaman, işe başlarken (işin bittiğini İDDİA ETMEZ)
    "eylem": ["Hemen hallediyorum.", "Tamam, bir saniye.", "Olur, hemen bakıyorum.", "Bir bakayım."],
    "anlamadim": ["Tam duyamadım, tekrar eder misin?", "Pardon, bir daha söyler misin?",
                  "Şunu tam anlayamadım, tekrar söyler misin?"],
    "hata": ["Bir sorun çıktı.", "Bunu yaparken bir sorun yaşadım."],
    "onay": ["Bunun için onayına ihtiyacım var.", "Onayını bekliyorum, ekrana bakar mısın?"],
    "uyandirma": ["Dinliyorum.", "Efendim?", "Buyur, dinliyorum."],
}
TUM_DOLGULAR = [c for liste in DOLGU.values() for c in liste]
KESME_CUMLESI = "Gerisini ekrana yazdım."


def dolgu_sec(kategori: str, son=None) -> str:
    secenekler = [d for d in DOLGU.get(kategori, []) if d != son] or DOLGU.get(kategori, [""])
    return random.choice(secenekler)


# ============================================================
# UYANDIRMA KELİMESİ: "Hey MFY" (okunuşu "mefeye")
# ============================================================
_HEY = {"hey", "hay", "hei", "hej", "ey", "heyy", "he", "hi", "ay"}
_UYANDIRMA_HEDEFLERI = ("mefeye", "mfy", "emefeye")


def uyandirma_ayikla(metin: str, esik_hey: float = 0.67, esik_yok: float = 0.85):
    """
    Cümle 'Hey MFY' ile (Whisper'ın 'mefeye', 'mefiye', 'em ef ye' gibi yazımları dahil) başlıyor mu?
    Döner: (bulundu_mu, kalan_komut). 'Hey MFY, sesi kıs' -> (True, 'sesi kıs')
    esik_hey: 'hey' ile başlıyorsa gereken benzerlik (düşürürsen daha kolay tetiklenir)
    """
    jetonlar = []
    for ham in (metin or "").split():
        norm = re.sub(r"[^a-z0-9]", "", sade(ham))
        if norm:
            jetonlar.append((ham, norm))
    if not jetonlar:
        return False, ""
    hey_var = jetonlar[0][1] in _HEY
    bas = 1 if hey_var else 0
    esik = esik_hey if hey_var else esik_yok
    en_iyi_oran, en_iyi_n = 0.0, 0
    for n in range(1, 5):
        parca = jetonlar[bas:bas + n]
        if len(parca) < n:
            break
        aday = "".join(p[1] for p in parca)
        oran = max(difflib.SequenceMatcher(None, aday, h).ratio() for h in _UYANDIRMA_HEDEFLERI)
        if oran > en_iyi_oran:
            en_iyi_oran, en_iyi_n = oran, n
    if en_iyi_oran < esik:
        return False, ""
    kalan = " ".join(h for h, _ in jetonlar[bas + en_iyi_n:]).strip(" ,.;:!?-–")
    return True, kalan


# ============================================================
# CÜMLE BÖLÜCÜ (akan metin için)
# ============================================================
_KISALTMALAR = {
    "dr", "prof", "doç", "doc", "örn", "orn", "vb", "vs", "yy", "bkz", "no", "sn", "dk", "sa", "tl", "mr", "mrs",
    "st", "cad", "sok", "apt", "mah", "tel", "av", "yrd", "uzm", "sayın", "sayin", "san", "çev", "cev", "ed",
}


class CumleBolucu:
    """
    Token token gelen metni cümlelere böler.
      ekle(parca)  -> yeni tamamlanan cümlelerin listesi
      bitir()      -> kalan son parçayı da cümle olarak verir
    İlk cümle kısa olsa bile hemen verilir (konuşma erken başlasın); sonrakiler çok kısaysa birleştirilir.
    Kısaltmalara (Dr., vb.), sayılara (3.5, 15.10.2026) ve kod bloklarına (```) dikkat eder.
    """

    def __init__(self, ilk_min: int = 3, min_uzunluk: int = 14, maks: int = 220):
        self.tampon = ""
        self.ilk_min = ilk_min
        self.min_uzunluk = min_uzunluk
        self.maks = maks
        self._ilk = True

    def ekle(self, parca: str) -> list:
        self.tampon += parca or ""
        return self._topla(False)

    def bitir(self) -> list:
        cikti = self._topla(True)
        kalan = self.tampon.strip()
        self.tampon = ""
        if kalan:
            cikti.append(kalan)
            self._ilk = False
        return cikti

    def _topla(self, son: bool) -> list:
        cikti = []
        while True:
            e = self._cumle_sonu(son)
            if e < 0:
                break
            cumle = self.tampon[:e].strip()
            self.tampon = self.tampon[e:]
            if cumle:
                cikti.append(cumle)
                self._ilk = False
        return cikti

    def _cumle_sonu(self, son: bool) -> int:
        t = self.tampon
        n = len(t)
        min_u = self.ilk_min if self._ilk else self.min_uzunluk
        i, kod = 0, False
        while i < n:
            if t.startswith("```", i):
                kod = not kod
                i += 3
                continue
            if kod:
                i += 1
                continue
            c = t[i]
            sinir = None
            if c == "\n":
                sinir = i + 1
            elif c in "?!…":
                j = i + 1
                while j < n and t[j] in "?!.…\"'”’)":
                    j += 1
                sinir = j
            elif c == ".":
                if i + 1 >= n:
                    if son:
                        sinir = n
                    else:
                        break                      # nokta mı, 3.5 gibi bir sayı mı? Sonraki karakteri bekle
                else:
                    sonraki = t[i + 1]
                    if sonraki.isspace() or sonraki in "\"')”’":
                        onceki = re.search(r"([^\s]+)$", t[:i])
                        kelime = (onceki.group(1) if onceki else "").lower().strip("\"'(")
                        liste_numarasi = kelime.isdigit() and (i - len(kelime) == 0 or t[i - len(kelime) - 1] == "\n")
                        bas_harf = len(kelime) == 1 and kelime.isalpha()
                        if not (kelime.rstrip(".") in _KISALTMALAR or bas_harf or liste_numarasi):
                            sinir = i + 2 if sonraki in "\"')”’" else i + 1
            if sinir is not None and len(t[:sinir].strip()) >= min_u:
                return sinir
            i += 1
        if kod:
            return -1
        if len(t) > self.maks:                     # çok uzun cümle: virgülden ya da boşluktan zorla böl
            k = max(t.rfind(", ", 0, self.maks), t.rfind(" ", 0, self.maks))
            return (k + 1) if k > 40 else self.maks
        return -1


def kisalt(cumleler: list, maks_cumle: int = 4, maks_karakter: int = 420):
    """Uzun cevabın başını alır. Döner: (okunacak_cumleler, kesildi_mi). İlk cümle her zaman okunur."""
    secilen, toplam = [], 0
    for c in cumleler:
        if secilen and (len(secilen) >= maks_cumle or toplam + len(c) > maks_karakter):
            return secilen, True
        secilen.append(c)
        toplam += len(c)
    return secilen, False
