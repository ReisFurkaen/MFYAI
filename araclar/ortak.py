"""
MFY AI - Araçların ortak yardımcıları
Birden fazla araç dosyasının kullandığı küçük fonksiyonlar burada tek kopya olarak durur;
araç dosyaları birbirini içe aktarmaz, ortak ihtiyaçlarını buradan alır.
"""
import os
import subprocess

NOWINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def boyut_metni(bayt: float) -> str:
    """1536 -> '1.5 KB'"""
    for birim in ("B", "KB", "MB", "GB", "TB"):
        if bayt < 1024 or birim == "TB":
            return f"{bayt:.0f} {birim}" if birim == "B" else f"{bayt:.1f} {birim}"
        bayt /= 1024


def cakismasiz(hedef: str) -> str:
    """Hedef zaten varsa 'ad (1).uzanti' gibi boş bir ad bulur (üzerine yazmamak için)."""
    if not os.path.exists(hedef):
        return hedef
    kok, uzanti = os.path.splitext(hedef)
    sayac = 1
    while os.path.exists(f"{kok} ({sayac}){uzanti}"):
        sayac += 1
    return f"{kok} ({sayac}){uzanti}"


def klasor_boyutu(yol: str, sinir_dosya: int = 20000, sinir_sn: float = 3.0):
    """(toplam_bayt, dosya_sayisi, tamamlandi_mi)"""
    import time
    toplam, sayi, bas = 0, 0, time.time()
    for kok, _, dosyalar in os.walk(yol):
        for d in dosyalar:
            try:
                toplam += os.path.getsize(os.path.join(kok, d))
            except OSError:
                pass
            sayi += 1
            if sayi >= sinir_dosya or time.time() - bas > sinir_sn:
                return toplam, sayi, False
    return toplam, sayi, True


def coz(*parcalar) -> str:
    """Komut çıktısını (bytes) metne çevirir: önce UTF-8, olmazsa Windows konsol kod sayfaları."""
    cikti = []
    for b in parcalar:
        if not b:
            continue
        metin = None
        for kodlama in ("utf-8", "oem", "cp1254"):
            try:
                metin = b.decode(kodlama)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        cikti.append((metin if metin is not None else b.decode("utf-8", "replace")).strip())
    return "\n".join(c for c in cikti if c)


def calistir(arglar: list, zaman_asimi: int = 30, maks: int = 6000) -> str:
    """Komutu (liste olarak, kabuk kullanmadan) çalıştırır; stdout + stderr birleşik döner."""
    try:
        s = subprocess.run(arglar, capture_output=True, timeout=zaman_asimi, creationflags=NOWINDOW)
    except subprocess.TimeoutExpired:
        return f"Komut {zaman_asimi} saniyede bitmedi."
    except Exception as e:
        return f"Hata: {e}"
    return (coz(s.stdout, s.stderr) or "(çıktı yok)")[:maks]


def ps(betik: str, zaman_asimi: int = 30, maks: int = 6000) -> str:
    """PowerShell betiği çalıştırır; stdout + stderr birleşik döner."""
    return calistir(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
                     "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + betik], zaman_asimi, maks)


def ps_stdout(betik: str, zaman_asimi: int = 20) -> str:
    """PowerShell betiği çalıştırır; yalnızca stdout döner (boş = çıktı yok)."""
    sonuc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + betik],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=zaman_asimi, creationflags=NOWINDOW)
    return (sonuc.stdout or "").strip()


def tk(metin) -> str:
    """PowerShell tek tırnaklı metin."""
    return "'" + str(metin).replace("'", "''") + "'"
