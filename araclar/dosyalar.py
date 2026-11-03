"""
MFY AI - Dosya ve Klasör Araçları
  OKUMA   : dosya_listele (ağaç da gösterir), dosya_oku (PDF/Word/PowerPoint/Excel/metin), dosya_ara (ad ya da içerik),
            dosya_bilgisi, dosya_ac, klasor_ac, klasor_yolu_bul, klasor_boyutlari, yinelenen_dosyalar, dosya_hash
  YAZMA   : klasor_olustur, dosya_yaz, dosya_kopyala, dosya_tasi (çakışmada üzerine YAZMAZ), dosya_yazdir
  SİLME   : dosya_sil (Geri Dönüşüm Kutusu), dosya_kalici_sil
  DÜZEN   : klasor_duzenle (türe göre, geri alınabilir), duzenlemeyi_geri_al, toplu_yeniden_adlandir (önizlemeli)
  ARŞİV   : arsiv_olustur, arsiv_ac
  VERİ    : sqlite_sorgu
Yol kuralları ve onaylar izinler.py'de (güven modu "sinirsiz" iken kısıt yoktur).
"""

import os
import re
import html
import json
import stat
import time
import shutil
import sqlite3
import hashlib
import zipfile
import subprocess
from collections import Counter, defaultdict
from datetime import datetime

from langchain.tools import tool

import config
import izinler
from araclar.ortak import (boyut_metni as _boyut_metni, boyut_metni as _boyut,
                           cakismasiz as _cakismasiz, klasor_boyutu as _klasor_boyutu)


# ============================================================
# ORTAK SABİTLER VE YARDIMCILAR
# ============================================================


MAKS_YAZMA_BAYT = (50 * 1024 * 1024) if izinler.SINIRSIZ else (200 * 1024)


MAKS_KLASOR_KOPYA_BAYT = 2 * 1024 ** 3


EV_DIZINI = izinler.EV


GERI_ALMA_DOSYASI = os.path.join(config.CALISMA_ALANI, "son_duzenleme.json")


_ATLA = {"appdata", "node_modules", ".git", "$recycle.bin", "__pycache__", ".venv", "venv", "system volume information"}


_METIN_UZANTILARI = {".txt", ".md", ".py", ".js", ".ts", ".json", ".csv", ".html", ".css", ".xml", ".yaml", ".yml", ".ini",
                     ".cfg", ".log", ".bat", ".ps1", ".sql", ".java", ".c", ".cpp", ".h", ".cs", ".go", ".rs", ".toml", ".env"}


def _yazilabilir(yol: str):
    izin, neden = izinler.degisiklige_acik_mi(yol)
    return None if izin else f"Yapılamaz: {neden}"


def _okuma_yasak_mi(yol: str) -> bool:
    """Gizli anahtarların ve uygulama verilerinin bulunduğu yerler modele okutulmaz."""
    if izinler.SINIRSIZ:
        return False
    yasak = [os.path.join(izinler.EV, ".ssh"), os.path.join(izinler.EV, "AppData")]
    windir = os.environ.get("WINDIR")
    if windir:
        yasak.append(os.path.join(windir, "System32", "config"))
    return any(izinler.altinda_mi(yol, k) for k in yasak)


def _yazma_yolu(yol: str) -> str:
    """Tam yol ya da bilinen klasör ('masaüstü/not.txt') olduğu gibi çözülür; yalnızca dosya adı ('not.txt') çalışma alanına gider."""
    tam = izinler.yol_coz(yol)
    ham = os.path.expandvars(os.path.expanduser((yol or "").strip().strip('"').strip("'")))
    if os.path.isabs(ham) or tam != os.path.abspath(ham):
        return tam
    return os.path.abspath(os.path.join(config.CALISMA_ALANI, ham))


def _calisma_alaninda(yol: str) -> bool:
    return izinler.altinda_mi(yol, config.CALISMA_ALANI)


# ============================================================
# OKUMA, LİSTELEME, ARAMA
# ============================================================


@tool
def dosya_listele(dizin: str, derinlik: int = 1) -> str:
    """Bir klasörün içeriğini listeler (örn: 'masaüstü', 'indirilenler', 'C:/Users/...'). derinlik: 1 = yalnızca o klasör;
    2-6 = alt klasörleri de ağaç olarak gösterir. Klasörler [köşeli parantez] içinde ve önce gelir."""
    yol = izinler.yol_coz(dizin)
    if not os.path.isdir(yol):
        return f"Klasör bulunamadı: {yol}"
    if _okuma_yasak_mi(yol):
        return "Bu konum korunuyor, listelenemez."
    try:
        derinlik = max(1, min(int(derinlik), 6))
    except (TypeError, ValueError):
        derinlik = 1
    sinir = 150 if derinlik == 1 else 200
    satirlar, sayac = [], [0]

    def gez(klasor, girinti, seviye):
        try:
            ogeler = sorted(os.scandir(klasor), key=lambda e: (not e.is_dir(follow_symlinks=False), e.name.lower()))
        except OSError:
            satirlar.append(f"{girinti}(erişilemiyor)")
            return
        for e in ogeler:
            if sayac[0] >= sinir:
                return
            sayac[0] += 1
            klasor_mu = e.is_dir(follow_symlinks=False)
            satirlar.append(f"{girinti}{'[' + e.name + ']' if klasor_mu else e.name}")
            if klasor_mu and seviye < derinlik and e.name.lower() not in _ATLA:
                gez(e.path, girinti + "  ", seviye + 1)

    gez(yol, "", 1)
    if not satirlar:
        return "Klasör boş."
    return "\n".join(satirlar) + (f"\n...({sinir} öğe sınırı)" if sayac[0] >= sinir else "")


@tool
def dosya_oku(yol: str, baslangic: int = 0, maks_karakter: int = 8000) -> str:
    """Bir dosyanın yazısını okur (örn: yol='masaüstü/notlar.txt'): PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx; ham metin) ve her türlü düz metin/kod
    dosyası. Uzun belgeler için baslangic (karakter konumu) ile devamını oku. PDF için 'pip install pypdf' gerekir."""
    yol_t = izinler.yol_coz(yol)
    if not os.path.isfile(yol_t):
        return f"Dosya bulunamadı: {yol_t}"
    if _okuma_yasak_mi(yol_t):
        return "Bu dosya korunuyor, okunamaz."
    uzanti = os.path.splitext(yol_t)[1].lower()
    try:
        if uzanti == ".docx":
            with zipfile.ZipFile(yol_t) as z:
                metin = _xml_metni(z.read("word/document.xml").decode("utf-8", "replace"), "</w:p>")
        elif uzanti == ".pptx":
            with zipfile.ZipFile(yol_t) as z:
                slaytlar = sorted((n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                                  key=lambda n: int(re.findall(r"\d+", n)[-1]))
                parcalar = []
                for i, n in enumerate(slaytlar, 1):
                    yazilar = re.findall(r"<a:t>(.*?)</a:t>", z.read(n).decode("utf-8", "replace"), re.DOTALL)
                    parcalar.append(f"--- Slayt {i} ---\n" + "\n".join(html.unescape(y) for y in yazilar))
                metin = "\n".join(parcalar)
        elif uzanti == ".xlsx":
            with zipfile.ZipFile(yol_t) as z:
                if "xl/sharedStrings.xml" not in z.namelist():
                    return "Bu Excel dosyasında okunabilir metin hücresi yok (yalnızca sayılar olabilir)."
                metin = "\n".join(html.unescape(y) for y in re.findall(
                    r"<t[^>]*>(.*?)</t>", z.read("xl/sharedStrings.xml").decode("utf-8", "replace"), re.DOTALL))
        elif uzanti == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError:
                try:
                    from PyPDF2 import PdfReader
                except ImportError:
                    return "PDF okumak için kullanıcıya terminalde 'pip install pypdf' çalıştırmasını söyle."
            okuyucu = PdfReader(yol_t)
            parcalar, toplam = [], 0
            for no, sayfa in enumerate(okuyucu.pages, 1):
                yazi = sayfa.extract_text() or ""
                parcalar.append(f"--- Sayfa {no} ---\n{yazi}")
                toplam += len(yazi)
                if toplam > max(0, int(baslangic)) + int(maks_karakter) + 2000:
                    break
            metin = "\n".join(parcalar)
        else:
            metin = _metin_oku(yol_t)
    except zipfile.BadZipFile:
        return "Dosya bozuk ya da bu türde değil."
    except Exception as e:
        return f"Hata: Belge okunamadı: {str(e)[:150]}"
    try:
        bas, uzun = max(0, int(baslangic)), max(500, min(int(maks_karakter), 30000))
    except (TypeError, ValueError):
        bas, uzun = 0, 8000
    parca = metin[bas:bas + uzun]
    if not parca.strip():
        return "Belgede okunabilir metin yok (taranmış/görüntü tabanlı olabilir)." if bas == 0 else "Belgenin sonuna ulaşıldı."
    kalan = len(metin) - (bas + uzun)
    return parca + (f"\n\n...(devamı var, {kalan} karakter daha; baslangic={bas + uzun} ile devam et)" if kalan > 0 else "")


@tool
def dosya_ara(kelime: str, dizin: str = "", icerikte: bool = False, uzanti: str = "", adet: int = 20) -> str:
    """Dosya arar. icerikte=False (varsayılan): dosya ADINDA kelime geçenleri bulur. icerikte=True: dosyaların İÇERİĞİNDE kelimeyi
    arar (kod/metin dosyaları; sonuç 'dosya:satır: içerik'). dizin: aranacak klasör (boşsa kullanıcı klasörü).
    uzanti: yalnızca bu türde dosyalar (örn. '.py')."""
    aranan = (kelime or "").strip().lower()
    if not aranan:
        return "Hata: Aranacak kelime boş."
    kok = izinler.yol_coz(dizin) if (dizin or "").strip() else izinler.EV
    if not os.path.isdir(kok):
        return f"Klasör bulunamadı: {kok}"
    uzanti = (uzanti or "").strip().lower()
    if uzanti and not uzanti.startswith("."):
        uzanti = "." + uzanti
    try:
        adet = max(1, min(int(adet), 100))
    except (TypeError, ValueError):
        adet = 20
    sonuc, taranan, bas = [], 0, time.time()
    sure = 30 if icerikte else 10
    for yol, klasorler, dosyalar in os.walk(kok):
        klasorler[:] = [k for k in klasorler if k.lower() not in _ATLA and (icerikte or not k.startswith("."))]
        for d in dosyalar:
            ek = os.path.splitext(d)[1].lower()
            if uzanti and ek != uzanti:
                continue
            tam = os.path.join(yol, d)
            if not icerikte:
                if aranan in d.lower():
                    sonuc.append(tam)
            else:
                if not uzanti and ek not in _METIN_UZANTILARI:
                    continue
                try:
                    if os.path.getsize(tam) > 2 * 1024 * 1024:
                        continue
                    taranan += 1
                    with open(tam, "r", encoding="utf-8", errors="ignore") as f:
                        for no, satir in enumerate(f, 1):
                            if aranan in satir.lower():
                                sonuc.append(f"{tam}:{no}: {satir.strip()[:160]}")
                                if len(sonuc) >= adet:
                                    break
                except OSError:
                    continue
            if len(sonuc) >= adet:
                break
        if len(sonuc) >= adet or time.time() - bas > sure:
            break
    if not sonuc:
        return f"'{kelime}' bulunamadı" + (f" ({taranan} dosya tarandı)." if icerikte else ".")
    return (f"{len(sonuc)} eşleşme" + (f" ({taranan} dosya tarandı)" if icerikte else "") + ":\n") + "\n".join(sonuc[:adet])


@tool
def dosya_bilgisi(yol: str) -> str:
    """Bir dosya ya da klasör hakkında bilgi verir: boyut, değiştirilme tarihi, içindeki öğe sayısı."""
    yol_t = izinler.yol_coz(yol)
    if not os.path.exists(yol_t):
        return f"Bulunamadı: {yol_t}"
    try:
        degisim = datetime.fromtimestamp(os.path.getmtime(yol_t)).strftime("%Y-%m-%d %H:%M")
        if os.path.isdir(yol_t):
            toplam, sayi, tam = _klasor_boyutu(yol_t)
            return (f"Klasör: {yol_t}\nİçerik: {'en az ' if not tam else ''}{sayi} dosya, "
                    f"{'en az ' if not tam else ''}{_boyut_metni(toplam)}\nSon değişiklik: {degisim}")
        return f"Dosya: {yol_t}\nBoyut: {_boyut_metni(os.path.getsize(yol_t))}\nSon değişiklik: {degisim}"
    except Exception as e:
        return f"Hata: {e}"


@tool
def dosya_ac(yol: str) -> str:
    """Bir dosyayı varsayılan programıyla açar (örn: 'masaüstü/rapor.pdf', 'indirilenler/foto.jpg').
    Çalıştırılabilir dosyalar (exe, bat, ps1...) için kullanıcı onayı gerekir."""
    yol_t = izinler.yol_coz(yol)
    if not os.path.isfile(yol_t):
        return f"Dosya bulunamadı: {yol_t}"
    if izinler.calistirilabilir_mi(yol_t):
        if not izinler.onay_iste("Çalıştırılabilir bir dosya açılacak:", yol_t, seviye=3):
            return izinler.RED_MESAJI
    try:
        os.startfile(yol_t)
        return f"Açıldı: {yol_t}"
    except Exception as e:
        return f"Hata: Dosya açılamadı: {e}"


@tool
def klasor_ac(yol: str) -> str:
    """Bir klasörü Dosya Gezgini'nde açar (örn: 'indirilenler', 'masaüstü'). Dosya yolu verilirse klasörünü açıp dosyayı seçer."""
    yol_t = izinler.yol_coz(yol)
    try:
        if os.path.isdir(yol_t):
            os.startfile(yol_t)
            return f"Klasör açıldı: {yol_t}"
        if os.path.isfile(yol_t):
            subprocess.Popen(["explorer", f"/select,{yol_t}"])
            return f"Dosya klasöründe gösterildi: {yol_t}"
        return f"Böyle bir klasör/dosya yok: {yol_t}"
    except Exception as e:
        return f"Hata: {e}"


@tool
def klasor_yolu_bul(klasor_adi: str) -> str:
    """Bilinen bir klasörün tam yolunu verir. klasor_adi: indirilenler, masaustu, belgeler, resimler, muzik veya videolar."""
    yol = izinler.bilinen_klasor(klasor_adi)   # OneDrive yönlendirmesini de doğru çözer
    return yol if yol else "Bu klasör bulunamadı."


@tool
def klasor_boyutlari(dizin: str, adet: int = 15) -> str:
    """Bir klasörün içindeki alt klasör ve dosyaları BOYUTA göre sıralar (disk neden doldu? sorusu için)."""
    kok = izinler.yol_coz(dizin)
    if not os.path.isdir(kok):
        return f"Klasör bulunamadı: {kok}"
    try:
        adet = max(1, min(int(adet), 50))
    except (TypeError, ValueError):
        adet = 15
    bitis, sonuc, tam = time.time() + 25, [], True
    try:
        cocuklar = list(os.scandir(kok))
    except OSError as e:
        return f"Hata: {e}"
    for e in cocuklar:
        try:
            if e.is_file(follow_symlinks=False):
                sonuc.append((e.stat().st_size, e.name, False))
            elif e.is_dir(follow_symlinks=False):
                toplam = 0
                for k, _, dosyalar in os.walk(e.path):
                    for d in dosyalar:
                        try:
                            toplam += os.path.getsize(os.path.join(k, d))
                        except OSError:
                            pass
                    if time.time() > bitis:
                        tam = False
                        break
                sonuc.append((toplam, e.name, True))
        except OSError:
            continue
        if time.time() > bitis:
            tam = False
            break
    sonuc.sort(reverse=True)
    toplam_boyut = sum(s[0] for s in sonuc)
    satirlar = [f"{kok} · toplam {'en az ' if not tam else ''}{_boyut(toplam_boyut)}"]
    satirlar += [f"{_boyut(b):>10}  {'[' + ad + ']' if klasor else ad}" for b, ad, klasor in sonuc[:adet]]
    return "\n".join(satirlar) + ("\n(Süre doldu, bazı klasörler eksik taranmış olabilir.)" if not tam else "")


@tool
def yinelenen_dosyalar(dizin: str, adet: int = 15) -> str:
    """Bir klasörde (alt klasörler dahil) aynı içeriğe sahip yinelenen dosyaları bulur ve boşa harcanan alanı söyler."""
    kok = izinler.yol_coz(dizin)
    if not os.path.isdir(kok):
        return f"Klasör bulunamadı: {kok}"
    bas, boyutlar, sayi = time.time(), defaultdict(list), 0
    for yol, klasorler, dosyalar in os.walk(kok):
        klasorler[:] = [k for k in klasorler if k.lower() not in _ATLA]
        for d in dosyalar:
            tam = os.path.join(yol, d)
            try:
                b = os.path.getsize(tam)
            except OSError:
                continue
            if b > 0:
                boyutlar[b].append(tam)
            sayi += 1
        if sayi > 30000 or time.time() - bas > 20:
            break
    gruplar = defaultdict(list)
    for b, yollar in boyutlar.items():
        if len(yollar) < 2 or b > 500 * 1024 * 1024:
            continue
        for y in yollar:
            if time.time() - bas > 50:
                break
            try:
                h = hashlib.md5()
                with open(y, "rb") as f:
                    for parca in iter(lambda: f.read(1024 * 1024), b""):
                        h.update(parca)
                gruplar[(b, h.hexdigest())].append(y)
            except OSError:
                continue
    cift = [(b, y) for (b, _), y in gruplar.items() if len(y) > 1]
    if not cift:
        return f"Yinelenen dosya bulunamadı ({sayi} dosya tarandı)."
    cift.sort(key=lambda x: -x[0] * (len(x[1]) - 1))
    israf = sum(b * (len(y) - 1) for b, y in cift)
    satirlar = [f"{len(cift)} yinelenen grup, boşa giden alan: {_boyut(israf)}"]
    for b, yollar in cift[:max(1, min(int(adet), 40))]:
        satirlar.append(f"- {_boyut(b)} × {len(yollar)}:\n    " + "\n    ".join(yollar[:5]))
    return "\n".join(satirlar)


@tool
def dosya_hash(yol: str, algoritma: str = "sha256") -> str:
    """Dosyanın parmak izini (hash) hesaplar. algoritma: md5, sha1, sha256, sha512. İndirilen dosyanın bütünlüğünü doğrulamak için."""
    yol_t = izinler.yol_coz(yol)
    if not os.path.isfile(yol_t):
        return f"Dosya bulunamadı: {yol_t}"
    a = (algoritma or "sha256").strip().lower()
    if a not in ("md5", "sha1", "sha256", "sha512"):
        return "Hata: algoritma md5, sha1, sha256 ya da sha512 olmalı."
    try:
        h = hashlib.new(a)
        with open(yol_t, "rb") as f:
            for parca in iter(lambda: f.read(1024 * 1024), b""):
                h.update(parca)
        return f"{a}: {h.hexdigest()}\n{yol_t} ({_boyut(os.path.getsize(yol_t))})"
    except OSError as e:
        return f"Hata: {e}"


def _metin_oku(yol: str) -> str:
    with open(yol, "rb") as f:
        ham = f.read(5 * 1024 * 1024)
    for kodlama in ("utf-8-sig", "cp1254", "latin-1"):
        try:
            return ham.decode(kodlama)
        except UnicodeDecodeError:
            continue
    return ham.decode("utf-8", errors="replace")


def _xml_metni(xml: str, paragraf_etiketi: str = "") -> str:
    if paragraf_etiketi:
        xml = xml.replace(paragraf_etiketi, "\n")
    xml = xml.replace("<w:tab/>", "\t")
    return html.unescape(re.sub(r"<[^>]+>", "", xml))


# ============================================================
# OLUŞTURMA, YAZMA, KOPYALAMA, TAŞIMA
# ============================================================


@tool
def klasor_olustur(yol: str) -> str:
    """Yeni bir klasör oluşturur (örn: 'masaüstü/Projeler/2026'). Yalnızca kullanıcı klasörü içinde çalışır."""
    yol_t = izinler.yol_coz(yol)
    izin, neden = izinler.degisiklige_acik_mi(yol_t)
    if not izin:
        return f"Yapılamaz: {neden}"
    if not izinler.onay_iste(f"Klasör oluşturulacak:\n{yol_t}", seviye=1):
        return izinler.RED_MESAJI
    try:
        var_mi = os.path.isdir(yol_t)
        os.makedirs(yol_t, exist_ok=True)
        return f"Klasör zaten vardı: {yol_t}" if var_mi else f"Klasör oluşturuldu: {yol_t}"
    except Exception as e:
        return f"Hata: {e}"


@tool
def dosya_yaz(yol: str, icerik: str, ekle: bool = False) -> str:
    """Bir metin dosyası oluşturur ya da günceller (örn: yol='masaüstü/notlar.txt'). Yalnızca dosya adı verilirse çalışma alanına kaydedilir. Güven moduna göre yol kısıtları geçerlidir.
    ekle=True ise dosyanın sonuna ekler, değilse içeriği tamamen değiştirir. Var olan dosya değiştirilecekse onay ister."""
    yol_t = _yazma_yolu(yol)
    izin, neden = izinler.degisiklige_acik_mi(yol_t)
    if not izin and not _calisma_alaninda(yol_t):
        return f"Yapılamaz: {neden}"
    if izinler.calistirilabilir_mi(yol_t) and not izinler.SINIRSIZ:
        return "Güvenlik nedeniyle çalıştırılabilir dosya türleri (exe, bat, ps1, vbs...) oluşturulamaz."
    veri = (icerik or "").encode("utf-8")
    if len(veri) > MAKS_YAZMA_BAYT:
        return f"İçerik çok büyük (en fazla {MAKS_YAZMA_BAYT // 1024} KB)."
    mevcut = os.path.exists(yol_t)
    if mevcut and os.path.isdir(yol_t):
        return "Bu yol bir klasör, dosya yazılamaz."
    if mevcut:
        eylem = "SONUNA EKLENECEK" if ekle else "ÜZERİNE YAZILACAK (eski içerik kaybolur)"
        if not izinler.onay_iste(f"Var olan dosya değiştirilecek: {eylem}\n{yol_t}", (icerik or "")[:600], seviye=2):
            return izinler.RED_MESAJI
    else:
        if not izinler.onay_iste(f"Yeni dosya oluşturulacak:\n{yol_t}", (icerik or "")[:600], seviye=1):
            return izinler.RED_MESAJI
    try:
        os.makedirs(os.path.dirname(yol_t), exist_ok=True)
        with open(yol_t, "a" if (ekle and mevcut) else "w", encoding="utf-8") as f:
            f.write(icerik or "")
        return f"{'Eklendi' if ekle and mevcut else ('Güncellendi' if mevcut else 'Oluşturuldu')}: {yol_t} ({_boyut_metni(len(veri))})"
    except Exception as e:
        return f"Hata: {e}"


def _hedef_yolu(kaynak: str, hedef: str) -> str:
    """Hedef bir klasörse kaynağın adını ekler, sonra çakışmayı çözer."""
    if os.path.isdir(hedef):
        hedef = os.path.join(hedef, os.path.basename(kaynak.rstrip("\\/")))
    return _cakismasiz(hedef)


@tool
def dosya_kopyala(kaynak: str, hedef: str) -> str:
    """Bir dosya ya da klasörü kopyalar (örn: kaynak='indirilenler/rapor.pdf', hedef='belgeler'). Aynı adlı dosyanın üzerine YAZMAZ."""
    k, h = izinler.yol_coz(kaynak), izinler.yol_coz(hedef)
    if not os.path.exists(k):
        return f"Kaynak bulunamadı: {k}"
    h_son = _hedef_yolu(k, h)
    izin, neden = izinler.degisiklige_acik_mi(h_son)
    if not izin:
        return f"Hedefe kopyalanamaz: {neden}"
    klasor_mu = os.path.isdir(k)
    if klasor_mu:
        toplam, _, tam = _klasor_boyutu(k)
        if not izinler.SINIRSIZ and (not tam or toplam > MAKS_KLASOR_KOPYA_BAYT):
            return "Klasör çok büyük (2 GB üstü olabilir), kopyalanmadı."
    if not izinler.onay_iste(f"{'Klasör' if klasor_mu else 'Dosya'} kopyalanacak:", f"{k}\n→ {h_son}", seviye=2 if klasor_mu else 1):
        return izinler.RED_MESAJI
    try:
        if klasor_mu:
            shutil.copytree(k, h_son)
        else:
            os.makedirs(os.path.dirname(h_son), exist_ok=True)
            shutil.copy2(k, h_son)
        return f"Kopyalandı: {h_son}"
    except Exception as e:
        return f"Hata: Kopyalanamadı: {e}"


@tool
def dosya_tasi(kaynak: str, hedef: str) -> str:
    """Bir dosya ya da klasörü başka yere taşır veya yeniden adlandırır (örn: kaynak='indirilenler/foto.jpg', hedef='resimler').
    Aynı adlı dosyanın üzerine YAZMAZ. Her zaman onay ister."""
    k, h = izinler.yol_coz(kaynak), izinler.yol_coz(hedef)
    if not os.path.exists(k):
        return f"Kaynak bulunamadı: {k}"
    izin, neden = izinler.degisiklige_acik_mi(k)
    if not izin:
        return f"Bu öğe taşınamaz: {neden}"
    if izinler.kutuphane_koku_mu(k) and not izinler.SINIRSIZ:
        return "Masaüstü, Belgeler, İndirilenler gibi ana klasörler taşınamaz."
    h_son = _hedef_yolu(k, h)
    izin, neden = izinler.degisiklige_acik_mi(h_son)
    if not izin:
        return f"Hedefe taşınamaz: {neden}"
    if not izinler.onay_iste("Taşınacak:", f"{k}\n→ {h_son}", seviye=2):
        return izinler.RED_MESAJI
    try:
        os.makedirs(os.path.dirname(h_son), exist_ok=True)
        shutil.move(k, h_son)
        return f"Taşındı: {h_son}"
    except Exception as e:
        return f"Hata: Taşınamadı: {e}"


@tool
def dosya_yazdir(yol: str) -> str:
    """Bir dosyayı varsayılan yazıcıdan yazdırır (örn: 'masaüstü/rapor.pdf'). Dosyanın türünü yazdırabilen bir program kurulu olmalı."""
    yol_t = izinler.yol_coz(yol)
    if not os.path.isfile(yol_t):
        return f"Dosya bulunamadı: {yol_t}"
    if not izinler.onay_iste("Dosya yazıcıya gönderilecek:", yol_t, seviye=2):
        return izinler.RED_MESAJI
    try:
        os.startfile(yol_t, "print")
        return f"Yazdırma işi gönderildi: {yol_t}"
    except Exception as e:
        return f"Hata: Yazdırılamadı: {e}"


# ============================================================
# SİLME
# ============================================================


def _geri_donusume_gonder(yol: str):
    """Dosya/klasörü Geri Dönüşüm Kutusu'na gönderir. Başarısızsa istisna fırlatır (kalıcı silme YAPILMAZ)."""
    try:
        from win32com.shell import shell, shellcon
        bayraklar = shellcon.FOF_ALLOWUNDO | shellcon.FOF_NOCONFIRMATION | shellcon.FOF_NOERRORUI | shellcon.FOF_SILENT
        sonuc, iptal = shell.SHFileOperation((0, shellcon.FO_DELETE, yol, None, bayraklar, None, None))
        if sonuc != 0 or iptal:
            raise OSError(f"Geri dönüşüme gönderilemedi (kod {sonuc})")
        return
    except ImportError:
        pass
    try:
        from send2trash import send2trash
    except ImportError:
        raise RuntimeError("Geri Dönüşüm Kutusu desteği bulunamadı; güvenlik için kalıcı silme yapılmadı.")
    send2trash(yol)


@tool
def dosya_sil(yol: str) -> str:
    """Bir dosya ya da klasörü Geri Dönüşüm Kutusu'na gönderir (kalıcı silmez, kullanıcı geri alabilir).
    Her zaman onay ister. Yalnızca kullanıcı klasörü içinde çalışır."""
    yol_t = izinler.yol_coz(yol)
    if not os.path.exists(yol_t):
        return f"Bulunamadı: {yol_t}"
    izin, neden = izinler.degisiklige_acik_mi(yol_t)
    if not izin:
        return f"Silinemez: {neden}"
    if izinler.kutuphane_koku_mu(yol_t) and not izinler.SINIRSIZ:
        return "Masaüstü, Belgeler, İndirilenler gibi ana klasörler silinemez."
    if os.path.isdir(yol_t):
        toplam, sayi, tam = _klasor_boyutu(yol_t)
        ayrinti = f"KLASÖR ve içindeki {'en az ' if not tam else ''}{sayi} dosya ({_boyut_metni(toplam)})"
    else:
        ayrinti = f"Dosya ({_boyut_metni(os.path.getsize(yol_t))})"
    if not izinler.onay_iste("Geri Dönüşüm Kutusu'na gönderilecek:", f"{yol_t}\n{ayrinti}", seviye=3):
        return izinler.RED_MESAJI
    try:
        _geri_donusume_gonder(yol_t)
        return f"Geri Dönüşüm Kutusu'na gönderildi (gerekirse oradan geri alınabilir): {yol_t}"
    except Exception as e:
        return f"Hata: {e}"


def _salt_okunur_sil(islev, yol, _):
    try:
        os.chmod(yol, stat.S_IWRITE)
        islev(yol)
    except OSError:
        pass


@tool
def dosya_kalici_sil(yol: str) -> str:
    """Bir dosya ya da klasörü KALICI siler (Geri Dönüşüm Kutusu'na gitmez, geri alınamaz). Geri alınabilir olması gerekiyorsa
    bunun yerine dosya_sil kullan. Yalnızca kullanıcı açıkça 'kalıcı sil' dediğinde ya da dosya_sil yetmediğinde kullan."""
    yol_t = izinler.yol_coz(yol)
    if not os.path.exists(yol_t):
        return f"Bulunamadı: {yol_t}"
    hata = _yazilabilir(yol_t)
    if hata:
        return hata
    if not getattr(izinler, "SINIRSIZ", False) and izinler.kutuphane_koku_mu(yol_t):
        return "Masaüstü, Belgeler, İndirilenler gibi ana klasörler silinemez."
    if os.path.splitdrive(yol_t)[1].strip("\\/") == "":
        return "Bir sürücünün kökü silinemez."
    if os.path.isdir(yol_t):
        sayi = sum(len(d) for _, _, d in os.walk(yol_t))
        ayrinti = f"KLASÖR ve içindeki {sayi} dosya"
    else:
        ayrinti = f"Dosya ({_boyut(os.path.getsize(yol_t))})"
    if not izinler.onay_iste("KALICI olarak silinecek (geri alınamaz):", f"{yol_t}\n{ayrinti}", seviye=3):
        return izinler.RED_MESAJI
    try:
        if os.path.isdir(yol_t) and not os.path.islink(yol_t):
            shutil.rmtree(yol_t, onerror=_salt_okunur_sil)
        else:
            os.chmod(yol_t, stat.S_IWRITE)
            os.remove(yol_t)
        return f"Kalıcı olarak silindi: {yol_t}" if not os.path.exists(yol_t) else f"Kısmen silindi, bazı öğeler kullanımda olabilir: {yol_t}"
    except Exception as e:
        return f"Hata: {e}"


# ============================================================
# DÜZENLEME VE TOPLU İŞLEMLER
# ============================================================


_KATEGORILER = {
    "Resimler": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".heic"},
    "Belgeler": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".odt", ".csv", ".md"},
    "Videolar": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm"},
    "Muzikler": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"},
    "Arsivler": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "Kurulumlar": {".exe", ".msi"},
    "Kodlar": {".py", ".js", ".html", ".css", ".json", ".java", ".cpp", ".c", ".ts"},
}


def _kategori(uzanti: str) -> str:
    for ad, kume in _KATEGORILER.items():
        if uzanti in kume:
            return ad
    return "Diger"


@tool
def klasor_duzenle(dizin: str) -> str:
    """Bir klasördeki dağınık dosyaları türüne göre alt klasörlere (Resimler, Belgeler vb.) düzenler (örn: 'masaüstü', 'indirilenler').
    Kullanıcı onayı gerekir, geri alınabilir."""
    try:
        dizin_t = izinler.yol_coz(dizin)
        if not os.path.isdir(dizin_t):
            return "Hata: Böyle bir klasör yok."
        izin, neden = izinler.degisiklige_acik_mi(dizin_t)
        if not izin:
            return f"Düzenlenemez: {neden}"

        plan = []
        for ad in os.listdir(dizin_t):
            tam = os.path.join(dizin_t, ad)
            uzanti = os.path.splitext(ad)[1].lower()
            if (not os.path.isfile(tam) or ad.startswith(".")
                    or ad.lower() in ("desktop.ini", "thumbs.db") or uzanti == ".lnk"):
                continue
            plan.append((ad, _kategori(uzanti)))
        if not plan:
            return "Düzenlenecek dosya bulunamadı."

        ozet = Counter(k for _, k in plan)
        ozet_metin = "\n".join(f"  {k}: {n} dosya" for k, n in ozet.items())
        if not izinler.onay_iste(f"'{dizin_t}' klasöründeki {len(plan)} dosya türüne göre taşınacak:",
                                 ozet_metin + "\n\nBu işlem geri alınabilir.", seviye=2):
            return izinler.RED_MESAJI

        hareketler, basarisiz = [], 0
        try:
            for ad, kategori in plan:
                try:
                    hedef_dizin = os.path.join(dizin_t, kategori)
                    os.makedirs(hedef_dizin, exist_ok=True)
                    kaynak = os.path.join(dizin_t, ad)
                    hedef = os.path.join(hedef_dizin, ad)
                    kok, uzanti = os.path.splitext(ad)
                    sayac = 1
                    while os.path.exists(hedef):
                        hedef = os.path.join(hedef_dizin, f"{kok} ({sayac}){uzanti}")
                        sayac += 1
                    shutil.move(kaynak, hedef)
                    hareketler.append({"kaynak": kaynak, "hedef": hedef})
                except Exception:
                    basarisiz += 1      # kilitli/kullanımdaki dosya tüm işlemi yarıda kesmesin
        finally:
            if hareketler:              # yarım kalsa bile yapılanlar geri alınabilsin
                with open(GERI_ALMA_DOSYASI, "w", encoding="utf-8") as f:
                    json.dump(hareketler, f, ensure_ascii=False, indent=2)

        sonuc = f"{len(hareketler)} dosya taşındı."
        if basarisiz:
            sonuc += f" {basarisiz} dosya taşınamadı (kullanımda olabilir)."
        return sonuc + " İstersen 'duzenlemeyi_geri_al' ile geri alabilirim."
    except Exception as e:
        return f"Hata: {e}"


@tool
def duzenlemeyi_geri_al(bos_girdi: str = "") -> str:
    """Son yapılan klasör düzenlemesini geri alır, dosyaları eski yerlerine taşır. Kullanıcı onayı gerekir."""
    try:
        if not os.path.exists(GERI_ALMA_DOSYASI):
            return "Geri alınacak bir düzenleme kaydı yok."
        with open(GERI_ALMA_DOSYASI, "r", encoding="utf-8") as f:
            hareketler = json.load(f)
        if not izinler.onay_iste(f"Son düzenlemedeki {len(hareketler)} dosya eski yerine geri taşınacak.", seviye=2):
            return izinler.RED_MESAJI
        geri = 0
        for h in hareketler:
            try:
                if not izinler.degisiklige_acik_mi(h["kaynak"])[0]:
                    continue
                if os.path.exists(h["hedef"]) and not os.path.exists(h["kaynak"]):
                    shutil.move(h["hedef"], h["kaynak"])
                    geri += 1
                    try:
                        os.rmdir(os.path.dirname(h["hedef"]))   # boşalan kategori klasörünü kaldır
                    except OSError:
                        pass
            except Exception:
                continue
        os.remove(GERI_ALMA_DOSYASI)
        return f"{geri} dosya eski yerine taşındı."
    except Exception as e:
        return f"Hata: {e}"


@tool
def toplu_yeniden_adlandir(dizin: str, bul: str, degistir: str = "", regex: bool = False, onizleme: bool = True) -> str:
    """Bir klasördeki dosya adlarında 'bul' ifadesini 'degistir' ile değiştirir (alt klasörlere girmez).
    regex=True ise 'bul' düzenli ifade olur (örn. bul='IMG_(\\d+)', degistir='Foto_\\1'). onizleme=True (varsayılan) yalnızca
    ne olacağını gösterir; gerçekten uygulamak için önce önizlemeyi kullanıcıya göster, sonra onizleme=False ile çağır."""
    kok = izinler.yol_coz(dizin)
    if not os.path.isdir(kok):
        return f"Klasör bulunamadı: {kok}"
    if not bul:
        return "Hata: 'bul' boş olamaz."
    try:
        kalip = re.compile(bul if regex else re.escape(bul))
    except re.error as e:
        return f"Hata: Geçersiz düzenli ifade: {e}"
    plan = []
    for ad in sorted(os.listdir(kok)):
        if not os.path.isfile(os.path.join(kok, ad)):
            continue
        yeni = kalip.sub(degistir or "", ad)
        if yeni != ad and yeni.strip():
            plan.append((ad, yeni))
    if not plan:
        return "Eşleşen dosya adı yok."
    if onizleme:
        return f"{len(plan)} dosya yeniden adlandırılacak (ÖNİZLEME, henüz uygulanmadı):\n" + \
               "\n".join(f"{a} → {y}" for a, y in plan[:40]) + ("\n..." if len(plan) > 40 else "")
    hata = _yazilabilir(kok)
    if hata:
        return hata
    if not izinler.onay_iste(f"{len(plan)} dosya yeniden adlandırılacak:", "\n".join(f"{a} → {y}" for a, y in plan[:15]), seviye=2):
        return izinler.RED_MESAJI
    basarili, atlanan = 0, 0
    for a, y in plan:
        hedef = os.path.join(kok, y)
        if os.path.exists(hedef):
            atlanan += 1
            continue
        try:
            os.rename(os.path.join(kok, a), hedef)
            basarili += 1
        except OSError:
            atlanan += 1
    return f"{basarili} dosya yeniden adlandırıldı." + (f" {atlanan} dosya atlandı (aynı ad var ya da kullanımda)." if atlanan else "")


# ============================================================
# ARŞİV VE VERİTABANI
# ============================================================


@tool
def arsiv_olustur(kaynak: str, hedef: str = "") -> str:
    """Bir dosya ya da klasörü zip arşivine sıkıştırır. hedef: oluşacak .zip yolu (boşsa kaynağın yanına)."""
    k = izinler.yol_coz(kaynak)
    if not os.path.exists(k):
        return f"Kaynak bulunamadı: {k}"
    h = izinler.yol_coz(hedef) if (hedef or "").strip() else k.rstrip("\\/") + ".zip"
    if not h.lower().endswith(".zip"):
        h += ".zip"
    h = _cakismasiz(h)
    hata = _yazilabilir(h)
    if hata:
        return hata
    if not izinler.onay_iste("Zip arşivi oluşturulacak:", f"{k}\n→ {h}", seviye=1):
        return izinler.RED_MESAJI
    try:
        sayi = 0
        with zipfile.ZipFile(h, "w", zipfile.ZIP_DEFLATED) as z:
            if os.path.isfile(k):
                z.write(k, os.path.basename(k))
                sayi = 1
            else:
                ana = os.path.dirname(k.rstrip("\\/"))
                for yol, _, dosyalar in os.walk(k):
                    for d in dosyalar:
                        tam = os.path.join(yol, d)
                        if os.path.abspath(tam) == os.path.abspath(h):
                            continue
                        try:
                            z.write(tam, os.path.relpath(tam, ana))
                            sayi += 1
                        except OSError:
                            continue
        return f"{sayi} dosya arşivlendi: {h} ({_boyut(os.path.getsize(h))})"
    except Exception as e:
        return f"Hata: {e}"


@tool
def arsiv_ac(arsiv: str, hedef: str = "") -> str:
    """Bir arşivi (zip, tar, tar.gz, tgz...) açar. hedef: açılacak klasör (boşsa arşivin yanında, arşiv adıyla yeni klasör)."""
    a = izinler.yol_coz(arsiv)
    if not os.path.isfile(a):
        return f"Arşiv bulunamadı: {a}"
    ad = os.path.basename(a)
    for uzanti in (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".zip", ".tar", ".gz"):
        if ad.lower().endswith(uzanti):
            ad = ad[:-len(uzanti)]
            break
    h = izinler.yol_coz(hedef) if (hedef or "").strip() else _cakismasiz(os.path.join(os.path.dirname(a), ad))
    hata = _yazilabilir(h)
    if hata:
        return hata
    if not izinler.onay_iste("Arşiv açılacak:", f"{a}\n→ {h}", seviye=2):
        return izinler.RED_MESAJI
    try:
        shutil.unpack_archive(a, h)
        sayi = sum(len(d) for _, _, d in os.walk(h))
        return f"Açıldı: {h} ({sayi} dosya)"
    except Exception as e:
        return f"Hata: Arşiv açılamadı: {e}"


@tool
def sqlite_sorgu(db_yolu: str, sql: str, adet: int = 50) -> str:
    """Bir SQLite veritabanında (.db, .sqlite) SQL çalıştırır (örn: sql='SELECT name FROM sqlite_master' ile tabloları listele).
    SELECT dışındaki komutlar veritabanını değiştirir. db_yolu: veritabanı dosyası."""
    yol_t = izinler.yol_coz(db_yolu)
    if not os.path.isfile(yol_t):
        return f"Veritabanı bulunamadı: {yol_t}"
    sql = (sql or "").strip()
    if not sql:
        return "Hata: SQL boş."
    degistirir = not re.match(r"(?i)^\s*(select|pragma|explain|with)\b", sql)
    if degistirir:
        hata = _yazilabilir(yol_t)
        if hata:
            return hata
        if not izinler.onay_iste("Veritabanını DEĞİŞTİREN SQL çalıştırılacak:", f"{yol_t}\n{sql[:600]}", seviye=2):
            return izinler.RED_MESAJI
    try:
        adet = max(1, min(int(adet), 200))
    except (TypeError, ValueError):
        adet = 50
    try:
        baglanti = sqlite3.connect(yol_t, timeout=10)
        try:
            try:
                imlec = baglanti.execute(sql)
            except (sqlite3.ProgrammingError, sqlite3.Warning) as e:
                if not degistirir or "one statement" not in str(e):
                    raise
                baglanti.executescript(sql)           # birden fazla komut ('CREATE ...; INSERT ...')
                return "Tamam, SQL komutları çalıştırıldı."
            if imlec.description:
                kolonlar = [d[0] for d in imlec.description]
                satirlar = imlec.fetchmany(adet)
                cikti = [" | ".join(kolonlar)] + [" | ".join(str(h)[:60] for h in s) for s in satirlar]
                return "\n".join(cikti)[:5000] if satirlar else "Sonuç yok."
            baglanti.commit()
            return f"Tamam, {imlec.rowcount} satır etkilendi."
        finally:
            baglanti.close()
    except sqlite3.Error as e:
        return f"SQL hatası: {e}"


ARACLAR = [
    dosya_listele, dosya_oku, dosya_ara, dosya_bilgisi, dosya_ac,
    klasor_ac, klasor_yolu_bul, klasor_olustur, dosya_yaz, dosya_kopyala,
    dosya_tasi, dosya_sil, dosya_kalici_sil, klasor_duzenle, duzenlemeyi_geri_al,
    klasor_boyutlari, yinelenen_dosyalar, dosya_hash, arsiv_olustur, arsiv_ac,
    toplu_yeniden_adlandir, sqlite_sorgu, dosya_yazdir,
]
