"""
MFY AI - Program ve İşlem Araçları
  UYGULAMALAR : uygulama_ac (Win32 + Mağaza), kurulu_programlar, baslangic_programlari
  İŞLEMLER    : islemler_listele, islem_detay, islem_kontrol (askıya al / öncelik / kapat / zorla kapat)
  KOMUT/KOD   : powershell_calistir, yonetici_olarak_calistir (UAC penceresi çıkar), run_python_code, calculator
Onaylar izinler.py üzerinden yürür.
"""

import os
import re
import ast
import json
import math
import time
import uuid
import base64
import difflib
import operator
import tempfile
import threading
import subprocess
from datetime import datetime

import psutil
import win32api
from langchain.tools import tool

import config
import izinler
from izinler import sade
from araclar.ortak import NOWINDOW as _NOWINDOW, boyut_metni as _boyut, tk as _tk

try:
    import winreg
except ImportError:  # pragma: no cover
    winreg = None


# ============================================================
# UYGULAMA AÇMA
# ============================================================


BILINEN_UYGULAMALAR = {
    "not defteri": "notepad.exe", "notepad": "notepad.exe",
    "hesap makinesi": "calc.exe", "hesap makinası": "calc.exe", "calculator": "calc.exe",
    "dosya gezgini": "explorer.exe", "gezgin": "explorer.exe", "explorer": "explorer.exe",
    "görev yöneticisi": "taskmgr.exe", "gorev yoneticisi": "taskmgr.exe",
    "paint": "mspaint.exe",
    "komut istemi": "cmd.exe", "cmd": "cmd.exe",
    "ayarlar": "ms-settings:",
    "chrome": "chrome", "google chrome": "chrome",
    "edge": "msedge", "firefox": "firefox",
    "vscode": "code", "visual studio code": "code",
    "spotify": "spotify", "discord": "discord",
}


_TR_TABLO = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def _sade(metin: str) -> str:
    return metin.translate(_TR_TABLO).lower().strip()


def _bilinen_bul(ad: str):
    """'Not Defterini', 'notepad', 'chrome u' gibi çekimli adları da bilinen uygulamayla eşleştirir."""
    sade = _sade(ad)
    for anahtar, hedef in BILINEN_UYGULAMALAR.items():          # önce tam eşleşme
        if _sade(anahtar) == sade:
            return hedef
    uzunlar = sorted(BILINEN_UYGULAMALAR.items(), key=lambda x: -len(x[0]))
    for anahtar, hedef in uzunlar:                              # sonra içinde geçme (en az 4 harfli anahtarlar)
        sade_anahtar = _sade(anahtar)
        if len(sade_anahtar) >= 4 and sade_anahtar in sade:
            return hedef
    return None


_YASAK_KARAKTERLER = set('&|<>^%"')


_indeks = None


_indeks_kilidi = threading.Lock()


def _baslat_uygulamalari(yenile: bool = False) -> list:
    global _indeks
    with _indeks_kilidi:
        if _indeks and not yenile:
            return _indeks
        try:
            sonuc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
                 "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=30, creationflags=_NOWINDOW)
            veri = json.loads(sonuc.stdout) if sonuc.stdout.strip() else []
            if isinstance(veri, dict):
                veri = [veri]
            liste = [{"ad": v["Name"], "id": v["AppID"]} for v in veri if v.get("Name") and v.get("AppID")]
            if liste:
                _indeks = liste
            return liste
        except Exception:
            return []


def _sadelestir(metin: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", sade(metin)).strip()


def _uygulama_bul(ad: str):
    """Başlat menüsündeki uygulamalar arasında en iyi eşleşmeyi bulur."""
    adaylar = _baslat_uygulamalari()
    if not adaylar:
        return None
    hedef = _sadelestir(ad)
    if not hedef:
        return None
    sadeler = [(_sadelestir(a["ad"]), a) for a in adaylar]

    for s, a in sadeler:                                   # 1) tam eşleşme
        if s == hedef:
            return a
    icerenler = [a for s, a in sadeler if hedef in s]      # 2) girdi uygulama adının içinde geçiyor
    if icerenler:
        return min(icerenler, key=lambda a: len(a["ad"]))
    kelimeler = [k for k in hedef.split() if len(k) >= 3]  # 3) tüm kelimeler uygulama adında geçiyor
    if kelimeler:
        kapsayanlar = [a for s, a in sadeler if all(k in s for k in kelimeler)]
        if kapsayanlar:
            return min(kapsayanlar, key=lambda a: len(a["ad"]))
    ters = [a for s, a in sadeler if len(s) >= 4 and s in hedef]   # 4) uygulama adı girdinin içinde ("chrome u")
    if ters:
        return max(ters, key=lambda a: len(a["ad"]))
    yakin = difflib.get_close_matches(hedef, [s for s, _ in sadeler], n=1, cutoff=0.72)   # 5) yazım hatası
    if yakin:
        return next(a for s, a in sadeler if s == yakin[0])
    return None


def _baslat(hedef: str):
    if hedef.endswith(":"):
        os.startfile(hedef)
    else:
        subprocess.Popen(["cmd", "/c", "start", "", hedef], creationflags=_NOWINDOW)


# Açılışta Başlat menüsü dizinini arka planda hazırla (ilk uygulama açma isteği hızlı olsun)
threading.Thread(target=_baslat_uygulamalari, daemon=True).start()


@tool
def uygulama_ac(uygulama_adi: str) -> str:
    """Bilgisayarda kurulu bir uygulamayı açar (örn: not defteri, chrome, spotify, discord, steam, word, excel, ayarlar, hesap makinesi).
    Başlat menüsündeki tüm uygulamaları bulabilir. Bir sitede bir şey açmak için bunu DEĞİL site_ac veya youtube_ac kullan."""
    ad = (uygulama_adi or "").strip()
    if not ad or any(k in _YASAK_KARAKTERLER for k in ad):
        return "Hata: Geçersiz uygulama adı."

    hedef = _bilinen_bul(ad)
    try:
        if hedef and (hedef.endswith(".exe") or hedef.endswith(":")):   # not defteri, hesap makinesi, ayarlar gibi sistem uygulamaları
            _baslat(hedef)
            return f"'{ad}' açıldı (komut gönderildi)."

        uygulama = _uygulama_bul(ad)
        if uygulama:
            os.startfile("shell:AppsFolder\\" + uygulama["id"])
            return f"'{uygulama['ad']}' uygulaması açılıyor."

        if hedef:
            _baslat(hedef)
            return f"'{ad}' için açma komutu gönderildi (uygulamanın açıldığını doğrulayamadım)."
    except Exception as e:
        return f"Hata: Uygulama açılamadı: {e}"
    return (f"'{ad}' adında kurulu bir uygulama bulamadım. kurulu_programlar aracıyla "
            f"bilgisayardaki uygulamaları listeleyebilirim.")


# ============================================================
# KURULU PROGRAMLAR VE BAŞLANGIÇ
# ============================================================


def _kayit_programlari(hedef: str) -> dict:
    """Denetim Masası kayıtlarındaki programlar: {sade_ad: 'Ad Sürüm · Yayıncı'}"""
    if not winreg:
        return {}
    kaynaklar = [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                 (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                 (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall")]
    bulunan = {}
    for kok, yol in kaynaklar:
        try:
            with winreg.OpenKey(kok, yol) as ana:
                i = 0
                while True:
                    try:
                        alt_ad = winreg.EnumKey(ana, i)
                        i += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(ana, alt_ad) as alt:
                            def deger(n):
                                try:
                                    return str(winreg.QueryValueEx(alt, n)[0])
                                except OSError:
                                    return ""
                            ad = deger("DisplayName")
                            if not ad or (hedef and hedef not in sade(ad)):
                                continue
                            bulunan.setdefault(sade(ad), f"{ad} {deger('DisplayVersion')} · {deger('Publisher')}".strip(" ·"))
                    except OSError:
                        continue
        except OSError:
            continue
    return bulunan


@tool
def kurulu_programlar(filtre: str = "") -> str:
    """Bilgisayarda kurulu programları ve uygulamaları listeler (masaüstü programları + Mağaza uygulamaları; mümkünse sürüm ve
    yayıncıyla). filtre: ada göre süzmek için kelime (örn. 'office', 'nvidia')."""
    hedef = sade(filtre).strip()
    bulunan = {}
    for a in _baslat_uygulamalari():                 # Başlat menüsü: masaüstü + Mağaza uygulamaları
        if not hedef or hedef in sade(a["ad"]):
            bulunan.setdefault(sade(a["ad"]), a["ad"])
    bulunan.update(_kayit_programlari(hedef))        # Denetim Masası kayıtları sürüm/yayıncı bilgisiyle daha zengindir
    if not bulunan:
        return f"'{filtre}' ile eşleşen kurulu program bulunamadı." if hedef else "Program listesi alınamadı."
    adlar = sorted(bulunan.values(), key=str.lower)
    return f"{len(adlar)} program:\n" + "\n".join(adlar[:80]) + ("\n..." if len(adlar) > 80 else "")


@tool
def baslangic_programlari(bos_girdi: str = "") -> str:
    """Windows açılışında otomatik başlayan programları listeler (Run kayıtları ve Başlangıç klasörleri)."""
    satirlar = []
    if winreg:
        for etiket, kok, yol in (("Kullanıcı", winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
                                 ("Sistem", winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run")):
            try:
                with winreg.OpenKey(kok, yol) as k:
                    i = 0
                    while True:
                        try:
                            ad, veri, _ = winreg.EnumValue(k, i)
                            satirlar.append(f"[{etiket}] {ad} → {str(veri)[:150]}")
                            i += 1
                        except OSError:
                            break
            except OSError:
                continue
    for klasor in (os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"),
                   os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs\StartUp")):
        try:
            for ad in os.listdir(klasor):
                if ad.lower() != "desktop.ini":
                    satirlar.append(f"[Klasör] {ad}  ({klasor})")
        except OSError:
            continue
    return "\n".join(satirlar) if satirlar else "Başlangıç programı bulunamadı."


# ============================================================
# İŞLEMLER
# ============================================================


KORUNAN_ISLEMLER = {
    "system", "system idle process", "registry", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe",
    "services.exe", "lsass.exe", "svchost.exe", "explorer.exe", "dwm.exe", "fontdrvhost.exe",
    "msmpeng.exe", "audiodg.exe", "spoolsv.exe", "sihost.exe", "ctfmon.exe", "taskhostw.exe",
    "runtimebroker.exe", "searchhost.exe", "startmenuexperiencehost.exe", "shellexperiencehost.exe",
}


_KRITIK_ISLEMLER = {"system", "registry", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe", "lsass.exe"}


def _islemleri_bul(hedef: str) -> list:
    h = (hedef or "").strip()
    if h.isdigit():
        try:
            return [psutil.Process(int(h))]
        except psutil.Error:
            return []
    ad = h.lower()
    if not ad.endswith(".exe"):
        ad += ".exe"
    return [p for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == ad]


@tool
def islemler_listele(adet: int = 8) -> str:
    """En çok bellek (RAM) kullanan programları listeler."""
    try:
        adet = max(1, min(int(adet), 30))
    except (TypeError, ValueError):
        adet = 8
    toplam = {}
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            ad = p.info["name"] or "?"
            bellek = p.info["memory_info"].rss if p.info["memory_info"] else 0
            toplam[ad] = toplam.get(ad, 0) + bellek
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    en_cok = sorted(toplam.items(), key=lambda x: x[1], reverse=True)[:adet]
    return "\n".join(f"{ad}: {b / (1024 ** 2):.0f} MB" for ad, b in en_cok)


@tool
def islem_detay(hedef: str) -> str:
    """Bir işlemin (program) ayrıntılarını verir: dosya yolu, komut satırı, kullanıcı, CPU/RAM, iş parçacığı, ana işlem,
    açık dosyalar, ağ bağlantıları. hedef: işlem adı (örn. 'chrome') ya da PID numarası."""
    bulunan = _islemleri_bul(hedef)
    if not bulunan:
        return f"'{hedef}' ile eşleşen işlem bulunamadı."
    satirlar = [f"{len(bulunan)} işlem eşleşti" + (" (ilk 3 gösteriliyor)" if len(bulunan) > 3 else "") + ":"]
    for p in bulunan[:3]:
        def al(f, varsayilan="?"):
            try:
                return f()
            except Exception:
                return varsayilan
        with p.oneshot():
            ana = al(lambda: psutil.Process(p.ppid()).name())
            satirlar.append(
                f"- {al(p.name)} (PID {p.pid}) · ana işlem: {ana}\n"
                f"  Yol: {al(p.exe)}\n  Komut: {' '.join(al(p.cmdline, []))[:300]}\n"
                f"  Kullanıcı: {al(p.username)} · Durum: {al(p.status)} · İş parçacığı: {al(p.num_threads)}\n"
                f"  CPU: %{al(lambda: p.cpu_percent(0.2))} · RAM: {_boyut(al(lambda: p.memory_info().rss, 0))} · "
                f"Başlangıç: {al(lambda: datetime.fromtimestamp(p.create_time()).strftime('%d.%m.%Y %H:%M'))}")
            dosyalar = al(lambda: [f.path for f in p.open_files()][:8], [])
            if dosyalar:
                satirlar.append("  Açık dosyalar: " + "; ".join(dosyalar))
            baglantilar = al(lambda: p.net_connections() if hasattr(p, "net_connections") else p.connections(), [])
            if baglantilar:
                satirlar.append(f"  Ağ bağlantısı: {len(baglantilar)} adet")
    return "\n".join(satirlar)


@tool
def islem_kontrol(hedef: str, islem: str) -> str:
    """Bir işlemi yönetir. hedef: işlem adı ya da PID. islem: 'askiya_al' (dondurur), 'devam_ettir', 'oncelik_dusur',
    'oncelik_normal', 'oncelik_yukselt', 'sonlandir' ya da 'kapat' (programı kapatır; örn. hedef='chrome') veya 'zorla_sonlandir'."""
    k = sade(islem).strip().replace(" ", "_")
    k = {"kapat": "sonlandir", "oldur": "zorla_sonlandir"}.get(k, k)
    gecerli = ("askiya_al", "devam_ettir", "oncelik_dusur", "oncelik_normal", "oncelik_yukselt", "sonlandir", "zorla_sonlandir")
    if k not in gecerli:
        return "Hata: islem " + ", ".join(gecerli) + " olmalı."
    bulunan = [p for p in _islemleri_bul(hedef) if p.pid != os.getpid()]
    if not bulunan:
        return f"'{hedef}' ile eşleşen işlem bulunamadı (asistanın kendisi hariç)."
    # Sınırsız modda yalnızca Windows'u çökerten çekirdek işlemler korunur; diğer modlarda explorer, svchost vb. de korunur
    korunan = (_KRITIK_ISLEMLER if (getattr(izinler, "SINIRSIZ", False) or "sonlandir" not in k)
               else (_KRITIK_ISLEMLER | KORUNAN_ISLEMLER))
    kritik = [p for p in bulunan if (p.name() or "").lower() in korunan]
    if kritik:
        return "Bu işlem Windows'un çökmesine yol açar, dokunulmadı: " + ", ".join(p.name() for p in kritik)
    if not izinler.onay_iste(f"{len(bulunan)} işleme '{k}' uygulanacak: {bulunan[0].name()}",
                             "PID: " + ", ".join(str(p.pid) for p in bulunan[:10]),
                             seviye=3 if "sonlandir" in k else 2):
        return izinler.RED_MESAJI
    oncelikler = {"oncelik_dusur": psutil.BELOW_NORMAL_PRIORITY_CLASS, "oncelik_normal": psutil.NORMAL_PRIORITY_CLASS,
                  "oncelik_yukselt": psutil.ABOVE_NORMAL_PRIORITY_CLASS} if hasattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS") else {}
    basarili, hatalar = 0, []
    for p in bulunan:
        try:
            if k == "askiya_al":
                p.suspend()
            elif k == "devam_ettir":
                p.resume()
            elif k in oncelikler:
                p.nice(oncelikler[k])
            elif k == "sonlandir":
                p.terminate()
            else:
                p.kill()
            basarili += 1
        except Exception as e:
            hatalar.append(f"{p.pid}: {type(e).__name__}")
    return f"{basarili}/{len(bulunan)} işleme '{k}' uygulandı." + (f" Hatalar: {', '.join(hatalar[:5])}" if hatalar else "")


# ============================================================
# KOMUT VE KOD ÇALIŞTIRMA
# ============================================================


_TEHLIKELI_KALIPLAR = [
    r"format\s+[a-z]:", r"\bdiskpart\b", r"\bbcdedit\b", r"vssadmin\s+delete", r"cipher\s+/w",
    r"(rd|rmdir|del|erase|remove-item)\b.*(/s|-recurse).*\b[a-z]:\\?(\s|$)",
    r"reg\s+delete\s+hk(lm|cr)", r"clear-disk", r"remove-partition", r"set-mppreference.*disable",
    r"(iex|invoke-expression)\b.*(downloadstring|invoke-webrequest|iwr)", r"(invoke-webrequest|iwr|curl|wget).*\|\s*(iex|invoke-expression)",
    r"net\s+user\s+.*\s/add", r"schtasks\s+/create", r"reg\s+add\s+.*\\run\b", r"new-service", r"\bsc(\.exe)?\s+create\b",
]


def _tehlikeli_mi(komut: str):
    s = " ".join(sade(komut).split())
    for kalip in _TEHLIKELI_KALIPLAR:
        if re.search(kalip, s):
            return kalip
    return None


@tool
def powershell_calistir(komut: str, zaman_asimi: int = 60) -> str:
    """Bilgisayarda bir PowerShell komutu çalıştırır ve çıktısını döndürür (örn: ipconfig, Get-Process, winget list).
    Başka hiçbir araç işi yapamıyorsa kullan. Uzun işler (kurulum vb.) için zaman_asimi saniye verilebilir (en fazla 1800). Onay, güven moduna göre istenir."""
    komut = (komut or "").strip()
    if not komut:
        return "Hata: Boş komut."
    kalip = None if izinler.SINIRSIZ else _tehlikeli_mi(komut)
    try:
        sure = max(5, min(int(zaman_asimi), 1800))
    except (TypeError, ValueError):
        sure = 60
    if kalip:
        return ("Bu komut sistemi geri dönülemez biçimde etkileyebileceği için (disk biçimlendirme, toplu silme, kalıcı "
                "değişiklik vb.) çalıştırılmadı. Kullanıcıya nedenini açıkla.")
    if not izinler.onay_iste("PowerShell komutu çalıştırılacak:", komut[:1200], seviye=3):
        return izinler.RED_MESAJI
    try:
        sonuc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
             "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + komut],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=sure, creationflags=_NOWINDOW)
        cikti = (sonuc.stdout or "").strip()
        hata = (sonuc.stderr or "").strip()
        metin = cikti + (("\n[HATA ÇIKTISI]\n" + hata) if hata else "")
        if not metin:
            metin = "(komut çıktı üretmedi)"
        if sonuc.returncode != 0:
            metin = f"[Çıkış kodu: {sonuc.returncode}]\n" + metin
        return metin[:3000] + ("\n...(kesildi)" if len(metin) > 3000 else "")
    except subprocess.TimeoutExpired:
        return f"Komut {sure} saniyede tamamlanmadığı için durduruldu."
    except Exception as e:
        return f"Hata: {e}"


@tool
def yonetici_olarak_calistir(komut: str, zaman_asimi: int = 60) -> str:
    """PowerShell komutunu YÖNETİCİ yetkisiyle çalıştırır ve çıktısını döndürür. Windows'un UAC penceresi çıkar;
    kullanıcının 'Evet' demesi gerekir (Windows bunu atlatmaya izin vermez). Servis, kayıt defteri (HKLM) ve sistem
    ayarı gibi yönetici gerektiren işler için kullan."""
    komut = (komut or "").strip()
    if not komut:
        return "Hata: Boş komut."
    if not izinler.onay_iste("Yönetici yetkisiyle PowerShell komutu çalıştırılacak:", komut[:1200], seviye=3):
        return izinler.RED_MESAJI
    try:
        sure = max(10, min(int(zaman_asimi), 1800))
    except (TypeError, ValueError):
        sure = 60
    cikti_yolu = os.path.join(tempfile.gettempdir(), f"mfy_admin_{uuid.uuid4().hex[:8]}.txt")
    bitti = cikti_yolu + ".bitti"
    betik = ("& { " + komut + " } *>&1 | Out-File -FilePath " + _tk(cikti_yolu) + " -Encoding utf8; "
             "'bitti' | Out-File -FilePath " + _tk(bitti))
    kodlu = base64.b64encode(betik.encode("utf-16-le")).decode("ascii")
    try:
        win32api.ShellExecute(0, "runas", "powershell.exe",
                              f"-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -EncodedCommand {kodlu}", None, 0)
    except Exception as e:
        return f"Yönetici yetkisi alınamadı (UAC penceresi reddedilmiş ya da başlatılamadı): {str(e)[:120]}"
    bitis = time.time() + sure
    while time.time() < bitis and not os.path.exists(bitti):
        time.sleep(0.5)
    if not os.path.exists(bitti):
        return f"Komut {sure} saniyede bitmedi (arka planda çalışmaya devam ediyor olabilir)."
    try:
        with open(cikti_yolu, "r", encoding="utf-8-sig", errors="replace") as f:
            metin = f.read().strip()
    except OSError:
        metin = ""
    for yol in (cikti_yolu, bitti):
        try:
            os.remove(yol)
        except OSError:
            pass
    return (metin or "(komut çıktı üretmedi)")[:4000]


_python_repl = None


@tool
def run_python_code(code: str) -> str:
    """Bilgisayarda Python kodu çalıştırır ve çıktısını döndürür (sonucu görmek için print kullan). Onay, güven moduna göre istenir."""
    global _python_repl
    if getattr(config, "KOD_CALISTIRMA_ONAYI", True):
        if not izinler.onay_iste("Python kodu çalıştırılacak:", (code or "")[:800], seviye=3):
            return izinler.RED_MESAJI
    try:
        if _python_repl is None:
            from langchain_experimental.utilities import PythonREPL
            _python_repl = PythonREPL()
        return _python_repl.run(code)
    except Exception as e:
        return f"Hata: {e}"


# ============================================================
# HESAP MAKİNESİ
# ============================================================


# --- Güvenli hesap makinesi (eval yerine) ---
_ISLEMLER = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}


def _hesapla(node):
    if isinstance(node, ast.Expression):
        return _hesapla(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ISLEMLER:
        sol, sag = _hesapla(node.left), _hesapla(node.right)
        if isinstance(node.op, ast.Pow) and abs(sag) > 1000:
            raise ValueError("Üs çok büyük.")
        return _ISLEMLER[type(node.op)](sol, sag)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        deger = _hesapla(node.operand)
        return -deger if isinstance(node.op, ast.USub) else deger
    if isinstance(node, ast.Name) and node.id in ("pi", "e", "tau"):
        return getattr(math, node.id)
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and callable(getattr(math, node.func.id, None))):
        return getattr(math, node.func.id)(*[_hesapla(a) for a in node.args])
    raise ValueError("Desteklenmeyen ifade.")


@tool
def calculator(expression: str) -> str:
    """Matematiksel işlemleri yapar (Örn: 2**10, sin(pi/2), sqrt(144))."""
    try:
        return str(_hesapla(ast.parse(expression.strip(), mode="eval")))
    except Exception as e:
        return f"Hesaplama hatası: {e}"


ARACLAR = [
    uygulama_ac, kurulu_programlar, baslangic_programlari, islemler_listele, islem_detay,
    islem_kontrol, powershell_calistir, yonetici_olarak_calistir, run_python_code, calculator,
]
