"""
MFY AI - Sistem Araçları
Bilgisayarın kendisi: saat, donanım, pil, disk, ağ, ekran/yazıcı, güç ve Windows'un derin ayarları.

  GENEL         : get_time, get_system_status, get_detailed_hardware_info, wmi_sorgu
  PİL/DİSK/AĞ   : pil_durumu, disk_durumu, ag_durumu, ag_baglantilari, ag_trafigi
  EKRAN/YAZICI  : ekran_parlakligi, ekran_bilgisi, yazicilar_listele
  GÜÇ           : bilgisayari_kilitla, guc_islemi, guc_iptal
  WINDOWS       : servis_listele/servis_islem, kayit_defteri_oku/yaz/sil (otomatik .reg yedeği),
                  olay_gunlugu, zamanlanmis_gorevler/zamanli_gorev_olustur/zamanli_gorev_sil, ortam_degiskeni

Onaylar izinler.py üzerinden yürür (güven modu "sinirsiz" iken hiçbiri sormaz).
"""

import os
import re
import io
import csv
import time
import socket
import ctypes
import subprocess
from datetime import datetime

import psutil
import win32api
from langchain.tools import tool

import config
import izinler
from izinler import sade
from araclar.ortak import (NOWINDOW as _NOWINDOW, boyut_metni as _boyut, calistir as _calistir, coz as _coz,
                           ps as _ps, ps_stdout as _powershell, tk as _tk)

try:
    import winreg
except ImportError:  # pragma: no cover
    winreg = None


# ============================================================
# GENEL
# ============================================================


@tool
def get_time(query: str) -> str:
    """Bilgisayarın güncel tarih ve saatini döndürür."""
    simdi = datetime.now()
    gun = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"][simdi.weekday()]
    return f"Şu anki tarih ve saat: {simdi.strftime('%Y-%m-%d %H:%M:%S')} ({gun})"


@tool
def get_system_status(query: str) -> str:
    """Bilgisayarın güncel RAM ve CPU kullanım oranlarını döndürür."""
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory().percent
    return f"Sistem Durumu - CPU Kullanımı: %{cpu}, RAM Kullanımı: %{ram}"


@tool
def get_detailed_hardware_info(query: str) -> str:
    """Bilgisayarın donanım detaylarını (işlemci, ekran kartı, RAM) sorgular."""
    try:
        import pythoncom
        import wmi
    except ImportError:
        return "WMI için 'pip install wmi pywin32' gerekli."
    pythoncom.CoInitialize()
    try:
        c = wmi.WMI(namespace="root\\CIMV2")
        bilgi = []
        cpu = c.Win32_Processor()[0]
        bilgi.append(f"CPU: {cpu.Name} | Hız: {cpu.CurrentClockSpeed} MHz")
        gpu = c.Win32_VideoController()[0]
        bilgi.append(f"GPU: {gpu.Name} | Sürücü: {gpu.DriverVersion}")
        ram = c.Win32_ComputerSystem()[0]
        total_ram = int(int(ram.TotalPhysicalMemory) / (1024 ** 3))
        bilgi.append(f"Toplam RAM: {total_ram} GB")
        return " | ".join(bilgi)
    except Exception as e:
        return f"WMI erişim hatası: {str(e)}"
    finally:
        pythoncom.CoUninitialize()


@tool
def wmi_sorgu(sinif: str, alanlar: str = "*", kosul: str = "", adet: int = 10) -> str:
    """WMI ile donanım/Windows bilgisi sorgular. sinif örnekleri: Win32_BIOS, Win32_BaseBoard, Win32_PhysicalMemory,
    Win32_DiskDrive, Win32_PnPEntity (USB/aygıtlar), Win32_Battery, Win32_VideoController, Win32_OperatingSystem,
    Win32_NetworkAdapterConfiguration, Win32_Printer, Win32_StartupCommand. alanlar: 'Name,Status' ya da '*'.
    kosul: WHERE koşulu (örn. "Name LIKE '%USB%'"). adet: en fazla kaç kayıt."""
    sinif = (sinif or "").strip()
    alanlar = (alanlar or "*").strip() or "*"
    if not re.fullmatch(r"[A-Za-z0-9_]+", sinif):
        return "Hata: Geçersiz sınıf adı."
    if not re.fullmatch(r"[A-Za-z0-9_,\s\*]+", alanlar):
        return "Hata: alanlar yalnızca harf, rakam, virgül ya da * içerebilir."
    sorgu = f"SELECT {alanlar} FROM {sinif}" + (f" WHERE {kosul}" if (kosul or "").strip() else "")
    try:
        adet = max(1, min(int(adet), 50))
    except (TypeError, ValueError):
        adet = 10
    try:
        import pythoncom
        import wmi
    except ImportError:
        return "WMI için 'pip install wmi pywin32' gerekli."
    pythoncom.CoInitialize()
    try:
        sonuc = wmi.WMI().query(sorgu)
        if not sonuc:
            return "Sonuç yok."
        satirlar = [f"{len(sonuc)} kayıt" + (f" (ilk {adet} gösteriliyor)" if len(sonuc) > adet else "") + ":"]
        for o in sonuc[:adet]:
            ozellikler = []
            for ad in o.properties.keys():
                try:
                    v = getattr(o, ad)
                except Exception:
                    continue
                if v is None or v == "" or v == []:
                    continue
                ozellikler.append(f"{ad}={str(v)[:80]}")
            satirlar.append("- " + " | ".join(ozellikler)[:700])
        return "\n".join(satirlar)
    except Exception as e:
        return f"WMI hatası: {str(e)[:200]}"
    finally:
        pythoncom.CoUninitialize()


# ============================================================
# PİL, DİSK, AĞ
# ============================================================


@tool
def pil_durumu(bos_girdi: str = "") -> str:
    """Pil yüzdesini ve şarj durumunu söyler (dizüstü bilgisayarlar için)."""
    pil = psutil.sensors_battery()
    if pil is None:
        return "Bu bilgisayarda pil yok (masaüstü bilgisayar)."
    durum = "şarj oluyor" if pil.power_plugged else "pille çalışıyor"
    kalan = ""
    if not pil.power_plugged and pil.secsleft and pil.secsleft > 0:
        kalan = f", yaklaşık {pil.secsleft // 3600} sa {(pil.secsleft % 3600) // 60} dk kaldı"
    return f"Pil %{round(pil.percent)}, {durum}{kalan}."


@tool
def disk_durumu(bos_girdi: str = "") -> str:
    """Tüm disklerin boş/dolu alan bilgisini verir."""
    satirlar = []
    for parca in psutil.disk_partitions(all=False):
        try:
            k = psutil.disk_usage(parca.mountpoint)
        except OSError:
            continue
        satirlar.append(f"{parca.device}: {k.free / 1024 ** 3:.1f} GB boş / {k.total / 1024 ** 3:.1f} GB (%{k.percent:.0f} dolu)")
    return "\n".join(satirlar) if satirlar else "Disk bilgisi alınamadı."


@tool
def ag_durumu(bos_girdi: str = "") -> str:
    """İnternet bağlantısını, bağlı Wi-Fi ağını ve IP adresini kontrol eder."""
    satirlar = []
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=3).close()
        satirlar.append("İnternet: bağlı")
    except OSError:
        satirlar.append("İnternet: bağlantı YOK")
    try:
        cikti = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True,
                               errors="replace", timeout=8, creationflags=_NOWINDOW).stdout
        ssid = re.search(r"^\s*SSID\s*:\s*(.+)$", cikti, re.MULTILINE)
        if ssid:
            satirlar.append(f"Wi-Fi ağı: {ssid.group(1).strip()}")
    except Exception:
        pass
    for ad, adresler in psutil.net_if_addrs().items():
        for a in adresler:
            if a.family == socket.AF_INET and not a.address.startswith(("127.", "169.254.")):
                satirlar.append(f"IP ({ad}): {a.address}")
    return "\n".join(satirlar)


@tool
def ag_baglantilari(filtre: str = "") -> str:
    """Açık ağ bağlantılarını ve dinlenen portları, hangi programın kullandığıyla birlikte listeler.
    filtre: program adı, port numarası, adres ya da durum (LISTEN, ESTABLISHED) içinde geçen kelime."""
    hedef = sade(filtre).strip()
    adlar = {}
    for p in psutil.process_iter(["pid", "name"]):
        adlar[p.info["pid"]] = p.info["name"] or "?"
    try:
        baglantilar = psutil.net_connections(kind="inet")
    except Exception as e:
        return f"Hata: {e} (bazı bilgiler için yönetici yetkisi gerekebilir)"
    satirlar = []
    for c in baglantilar:
        yerel = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "-"
        uzak = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else "-"
        program = adlar.get(c.pid, "?")
        satir = f"{program} (PID {c.pid}) | {yerel} → {uzak} | {c.status}"
        if hedef and hedef not in sade(satir):
            continue
        satirlar.append(satir)
    if not satirlar:
        return "Eşleşen bağlantı yok."
    return f"{len(satirlar)} bağlantı:\n" + "\n".join(satirlar[:60]) + ("\n..." if len(satirlar) > 60 else "")


@tool
def ag_trafigi(bos_girdi: str = "") -> str:
    """Ağ adaptörlerinin şu anki indirme/yükleme hızını (1 saniyelik ölçümle) ve toplam trafiğini söyler."""
    onceki = psutil.net_io_counters(pernic=True)
    time.sleep(1.0)
    simdi = psutil.net_io_counters(pernic=True)
    satirlar = []
    for ad, s in simdi.items():
        o = onceki.get(ad)
        if not o or (s.bytes_recv + s.bytes_sent) == 0:
            continue
        satirlar.append(f"{ad}: ↓ {_boyut(s.bytes_recv - o.bytes_recv)}/sn · ↑ {_boyut(s.bytes_sent - o.bytes_sent)}/sn "
                        f"(toplam ↓ {_boyut(s.bytes_recv)} ↑ {_boyut(s.bytes_sent)})")
    return "\n".join(satirlar) if satirlar else "Trafik bilgisi alınamadı."


# ============================================================
# EKRAN VE YAZICI
# ============================================================


@tool
def ekran_parlakligi(seviye: int = -1) -> str:
    """Ekran parlaklığını okur ya da ayarlar (yalnızca dizüstü bilgisayar / dahili ekranlarda çalışır).
    seviye: 0-100 arası hedef yüzde. -1 verilirse sadece mevcut parlaklığı söyler."""
    try:
        seviye = int(seviye)
        if seviye >= 0:
            seviye = min(100, seviye)
            _powershell(
                "$m = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods; "
                f"Invoke-CimMethod -InputObject $m -MethodName WmiSetBrightness -Arguments @{{Timeout=1; Brightness={seviye}}} | Out-Null")
        mevcut = _powershell("(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness).CurrentBrightness")
        if not mevcut:
            return ("Bu bilgisayarda yazılımla parlaklık kontrolü desteklenmiyor (masaüstü monitörlerde bu normaldir; "
                    "monitörün kendi düğmelerini kullanmak gerekir).")
        return f"Ekran parlaklığı şu an %{mevcut.splitlines()[0].strip()}."
    except Exception as e:
        return f"Hata: Parlaklık ayarlanamadı: {e}"


@tool
def ekran_bilgisi(bos_girdi: str = "") -> str:
    """Bağlı monitörleri, çözünürlüklerini ve konumlarını listeler (hangisi ana ekran)."""
    try:
        satirlar = []
        for i, (hmon, _, _) in enumerate(win32api.EnumDisplayMonitors(), 1):
            b = win32api.GetMonitorInfo(hmon)
            sol, ust, sag, alt = b["Monitor"]
            satirlar.append(f"Monitör {i}: {sag - sol}x{alt - ust} piksel, konum ({sol}, {ust})"
                            f"{' · ANA EKRAN' if b.get('Flags') == 1 else ''} · {b.get('Device', '')}")
        return "\n".join(satirlar) if satirlar else "Monitör bilgisi alınamadı."
    except Exception as e:
        return f"Hata: {e}"


@tool
def yazicilar_listele(bos_girdi: str = "") -> str:
    """Kurulu yazıcıları listeler ve varsayılan yazıcıyı söyler."""
    try:
        import win32print
        varsayilan = ""
        try:
            varsayilan = win32print.GetDefaultPrinter()
        except Exception:
            pass
        yazicilar = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS, None, 2)
        satirlar = [f"{y.get('pPrinterName')} · port: {y.get('pPortName')}" + (" · VARSAYILAN" if y.get("pPrinterName") == varsayilan else "")
                    for y in yazicilar]
        return "\n".join(satirlar) if satirlar else "Kurulu yazıcı yok."
    except Exception as e:
        return f"Hata: {e}"


# ============================================================
# KİLİT VE GÜÇ
# ============================================================


@tool
def bilgisayari_kilitla(bos_girdi: str = "") -> str:
    """Windows oturumunu kilitler (ekran kilidi). Bilgisayarı KAPATMAZ."""
    if not izinler.onay_iste("Bilgisayarın ekranı kilitlenecek.", seviye=1):
        return izinler.RED_MESAJI
    try:
        ctypes.windll.user32.LockWorkStation()
        return "Ekran kilitlendi."
    except Exception as e:
        return f"Hata: Kilitlenemedi: {e}"


@tool
def guc_islemi(islem: str, bekleme_saniye: int = 30) -> str:
    """Bilgisayarın güç işlemini yapar. islem: 'kapat', 'yeniden_baslat', 'uyut' veya 'oturumu_kapat'.
    kapat/yeniden_baslat işlemlerinde bekleme_saniye kadar geri sayım olur ve guc_iptal ile durdurulabilir.
    Kullanıcıdan HER ZAMAN onay alınır."""
    k = sade(islem).strip().replace(" ", "_")
    try:
        bekleme = max(5, min(int(bekleme_saniye), 600))
    except (TypeError, ValueError):
        bekleme = 30
    komutlar = {
        "kapat": (["shutdown", "/s", "/t", str(bekleme), "/c", "MFY AI: bilgisayar kapatılıyor"], f"Bilgisayar {bekleme} saniye sonra KAPATILACAK"),
        "yeniden_baslat": (["shutdown", "/r", "/t", str(bekleme), "/c", "MFY AI: yeniden başlatılıyor"], f"Bilgisayar {bekleme} saniye sonra YENİDEN BAŞLATILACAK"),
        "uyut": (["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], "Bilgisayar UYKU moduna alınacak"),
        "oturumu_kapat": (["shutdown", "/l"], "Windows oturumu KAPATILACAK (açık uygulamalardaki kaydedilmemiş işler kaybolabilir)"),
    }
    esdeger = {"kapatma": "kapat", "yeniden_baslatma": "yeniden_baslat", "restart": "yeniden_baslat",
               "uyku": "uyut", "sleep": "uyut", "cikis": "oturumu_kapat", "logoff": "oturumu_kapat"}
    k = esdeger.get(k, k)
    if k not in komutlar:
        return "Hata: islem 'kapat', 'yeniden_baslat', 'uyut' veya 'oturumu_kapat' olmalı."
    komut, aciklama = komutlar[k]
    if not izinler.onay_iste(aciklama + ".", "Açık uygulamalarındaki kaydedilmemiş çalışmalar kaybolabilir.", seviye=3):
        return izinler.RED_MESAJI
    try:
        subprocess.Popen(komut, creationflags=_NOWINDOW)
        if k in ("kapat", "yeniden_baslat"):
            return f"{aciklama}. Vazgeçmek için guc_iptal aracını çalıştırabilirim."
        return f"{aciklama}."
    except Exception as e:
        return f"Hata: Güç işlemi başlatılamadı: {e}"


@tool
def guc_iptal(bos_girdi: str = "") -> str:
    """Başlatılmış kapatma / yeniden başlatma geri sayımını iptal eder."""
    try:
        sonuc = subprocess.run(["shutdown", "/a"], capture_output=True, text=True, errors="replace",
                               timeout=10, creationflags=_NOWINDOW)
        if sonuc.returncode == 0:
            return "Kapatma/yeniden başlatma iptal edildi."
        return "İptal edilecek bekleyen bir kapatma işlemi yok."
    except Exception as e:
        return f"Hata: {e}"


# ============================================================
# HİZMETLER
# ============================================================


@tool
def servis_listele(filtre: str = "", durum: str = "") -> str:
    """Windows hizmetlerini (servisleri) listeler. filtre: ad ya da görünen adda geçen kelime.
    durum: 'running' (çalışan), 'stopped' (durmuş) ya da boş (hepsi)."""
    hedef, d = sade(filtre).strip(), sade(durum).strip()
    satirlar = []
    try:
        for s in psutil.win_service_iter():
            try:
                b = s.as_dict()
            except Exception:
                continue
            ad, gorunen = b.get("name", ""), b.get("display_name", "")
            if hedef and hedef not in sade(ad) and hedef not in sade(gorunen):
                continue
            if d and sade(b.get("status", "")) != d:
                continue
            satirlar.append(f"{ad} | {gorunen} | {b.get('status')} | başlangıç: {b.get('start_type')}")
    except Exception as e:
        return f"Hata: {e}"
    if not satirlar:
        return "Eşleşen hizmet yok."
    return f"{len(satirlar)} hizmet:\n" + "\n".join(satirlar[:60]) + ("\n..." if len(satirlar) > 60 else "")


@tool
def servis_islem(servis_adi: str, islem: str) -> str:
    """Bir Windows hizmetini yönetir. servis_adi: hizmetin kısa adı (servis_listele ile bul, örn. 'Spooler').
    islem: 'baslat', 'durdur', 'yeniden_baslat', 'devre_disi', 'otomatik' veya 'elle'. Çoğu işlem yönetici yetkisi ister."""
    ad = (servis_adi or "").strip()
    if not re.fullmatch(r"[\w .\-$]+", ad):
        return "Hata: Geçersiz hizmet adı."
    k = sade(islem).strip().replace(" ", "_")
    komutlar = {
        "baslat": "Start-Service -Name {a}", "durdur": "Stop-Service -Name {a} -Force",
        "yeniden_baslat": "Restart-Service -Name {a} -Force",
        "devre_disi": "Set-Service -Name {a} -StartupType Disabled",
        "otomatik": "Set-Service -Name {a} -StartupType Automatic", "elle": "Set-Service -Name {a} -StartupType Manual",
    }
    if k not in komutlar:
        return "Hata: islem 'baslat', 'durdur', 'yeniden_baslat', 'devre_disi', 'otomatik' veya 'elle' olmalı."
    if not izinler.onay_iste(f"'{ad}' hizmetine '{k}' işlemi uygulanacak.", seviye=3 if k in ("durdur", "devre_disi") else 2):
        return izinler.RED_MESAJI
    cikti = _ps(komutlar[k].format(a=_tk(ad)) + "; Get-Service -Name " + _tk(ad) +
                " | Format-List Name,Status,StartType", 60)
    return cikti + ("\n(Erişim hatası aldıysan yonetici_olarak_calistir ile dene.)" if "denied" in cikti.lower() or "erişim" in cikti.lower() else "")


# ============================================================
# KAYIT DEFTERİ (REGISTRY)
# ============================================================


_KOKLER = {}


_UZUN_KOKLER = {"HKEY_CURRENT_USER": "HKCU", "HKEY_LOCAL_MACHINE": "HKLM", "HKEY_CLASSES_ROOT": "HKCR",
                "HKEY_USERS": "HKU", "HKEY_CURRENT_CONFIG": "HKCC"}


_TUR_ADLARI = {1: "REG_SZ", 2: "REG_EXPAND_SZ", 3: "REG_BINARY", 4: "REG_DWORD", 7: "REG_MULTI_SZ", 11: "REG_QWORD"}


def _kayit_ayir(yol: str):
    """'HKCU\\Software\\X' ya da 'HKEY_CURRENT_USER:\\Software\\X' -> ('HKCU', 'Software\\X')"""
    y = (yol or "").strip().replace("/", "\\")
    parca = y.split("\\", 1)
    kok = parca[0].rstrip(":").upper()
    kok = _UZUN_KOKLER.get(kok, kok)
    if kok not in _KOKLER:
        raise ValueError("Yol HKCU, HKLM, HKCR, HKU ya da HKCC ile başlamalı (örn. HKCU\\Software\\Microsoft).")
    return kok, (parca[1].strip("\\") if len(parca) > 1 else "")


def _kayit_yedekle(kok: str, alt: str) -> str:
    """Değiştirmeden önce anahtarı .reg dosyasına yedekler. Döner: yedek yolu ('' ise alınamadı)."""
    try:
        klasor = os.path.join(config.CALISMA_ALANI, "kayit_yedek")
        os.makedirs(klasor, exist_ok=True)
        dosya = os.path.join(klasor, datetime.now().strftime("yedek_%Y%m%d_%H%M%S.reg"))
        _calistir(["reg", "export", f"{kok}\\{alt}" if alt else kok, dosya, "/y"], 30)
        return dosya if os.path.exists(dosya) else ""
    except Exception:
        return ""


@tool
def kayit_defteri_oku(yol: str, deger: str = "") -> str:
    """Windows kayıt defterini okur. yol: örn. 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run'.
    deger verilirse o değeri, boşsa anahtarın alt anahtarlarını ve değerlerini listeler."""
    try:
        kok, alt = _kayit_ayir(yol)
    except ValueError as e:
        return f"Hata: {e}"
    try:
        with winreg.OpenKey(_KOKLER[kok], alt, 0, winreg.KEY_READ) as k:
            if deger:
                veri, tur = winreg.QueryValueEx(k, deger)
                return f"{kok}\\{alt} → {deger} = {veri!r} ({_TUR_ADLARI.get(tur, tur)})"
            alt_anahtarlar, degerler, i = [], [], 0
            while len(alt_anahtarlar) < 50:
                try:
                    alt_anahtarlar.append(winreg.EnumKey(k, i))
                    i += 1
                except OSError:
                    break
            i = 0
            while len(degerler) < 50:
                try:
                    ad, v, t = winreg.EnumValue(k, i)
                    degerler.append(f"{ad or '(varsayılan)'} = {str(v)[:120]!r} ({_TUR_ADLARI.get(t, t)})")
                    i += 1
                except OSError:
                    break
    except FileNotFoundError:
        return "Anahtar ya da değer bulunamadı."
    except PermissionError:
        return "Erişim reddedildi (yönetici yetkisi gerekebilir; yonetici_olarak_calistir ile 'reg query' dene)."
    except OSError as e:
        return f"Hata: {e}"
    cikti = [f"{kok}\\{alt}"]
    cikti.append("Alt anahtarlar: " + (", ".join(alt_anahtarlar) if alt_anahtarlar else "(yok)"))
    cikti.append("Değerler:\n" + ("\n".join("  " + d for d in degerler) if degerler else "  (yok)"))
    return "\n".join(cikti)


@tool
def kayit_defteri_yaz(yol: str, deger: str, veri: str, tur: str = "REG_SZ") -> str:
    """Kayıt defterine değer yazar (anahtar yoksa oluşturur). tur: REG_SZ (metin, varsayılan), REG_DWORD (sayı), REG_QWORD,
    REG_EXPAND_SZ veya REG_MULTI_SZ (satırları '|' ile ayır). Yazmadan önce anahtarın .reg yedeği otomatik alınır."""
    try:
        kok, alt = _kayit_ayir(yol)
    except ValueError as e:
        return f"Hata: {e}"
    turler = {"REG_SZ": winreg.REG_SZ, "REG_DWORD": winreg.REG_DWORD, "REG_QWORD": winreg.REG_QWORD,
              "REG_EXPAND_SZ": winreg.REG_EXPAND_SZ, "REG_MULTI_SZ": winreg.REG_MULTI_SZ}
    tur = (tur or "REG_SZ").strip().upper()
    if tur not in turler:
        return "Hata: tur " + ", ".join(turler) + " olmalı."
    try:
        if tur in ("REG_DWORD", "REG_QWORD"):
            veri_d = int(str(veri), 0)
        elif tur == "REG_MULTI_SZ":
            veri_d = str(veri).split("|")
        else:
            veri_d = str(veri)
    except ValueError:
        return "Hata: Bu tür için veri sayı olmalı."
    if not izinler.onay_iste(f"Kayıt defterine yazılacak: {kok}\\{alt}", f"{deger or '(varsayılan)'} = {veri} ({tur})",
                             seviye=3 if kok != "HKCU" else 2):
        return izinler.RED_MESAJI
    yedek = _kayit_yedekle(kok, alt)
    try:
        with winreg.CreateKeyEx(_KOKLER[kok], alt, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, deger, 0, turler[tur], veri_d)
    except PermissionError:
        return "Erişim reddedildi: bu anahtar yönetici yetkisi ister (yonetici_olarak_calistir ile 'reg add' kullan)."
    except OSError as e:
        return f"Hata: {e}"
    return f"Yazıldı: {kok}\\{alt} → {deger or '(varsayılan)'} = {veri}" + (f"\nYedek: {yedek}" if yedek else "")


@tool
def kayit_defteri_sil(yol: str, deger: str = "") -> str:
    """Kayıt defterinden bir değeri (deger verilirse) ya da anahtarın TAMAMINI (alt anahtarlarıyla, deger boşsa) siler.
    Silmeden önce .reg yedeği otomatik alınır; yedek dosyasına çift tıklanarak geri yüklenebilir."""
    try:
        kok, alt = _kayit_ayir(yol)
    except ValueError as e:
        return f"Hata: {e}"
    if not alt:
        return "Hata: Bir kök anahtarın kendisi silinemez."
    if not izinler.onay_iste(f"Kayıt defterinden silinecek: {kok}\\{alt}",
                             f"Değer: {deger}" if deger else "Anahtarın TAMAMI alt anahtarlarıyla silinecek.", seviye=3):
        return izinler.RED_MESAJI
    yedek = _kayit_yedekle(kok, alt)
    arglar = ["reg", "delete", f"{kok}\\{alt}"] + (["/v", deger] if deger else []) + ["/f"]
    sonuc = _calistir(arglar, 30)
    return sonuc + (f"\nYedek: {yedek}" if yedek else "")


# ============================================================
# OLAY GÜNLÜĞÜ, ZAMANLANMIŞ GÖREVLER, ORTAM
# ============================================================


@tool
def olay_gunlugu(gunluk: str = "System", adet: int = 15, seviye: str = "") -> str:
    """Windows olay günlüğünü okur (çökme, sürücü, hata kayıtları). gunluk: 'System', 'Application' veya 'Security'.
    seviye: 'hata' (kritik+hata), 'uyari', 'bilgi' ya da boş (hepsi). En yeni kayıtlar önce."""
    if not re.fullmatch(r"[A-Za-z0-9\-/ ]+", (gunluk or "").strip()):
        return "Hata: Geçersiz günlük adı."
    try:
        adet = max(1, min(int(adet), 50))
    except (TypeError, ValueError):
        adet = 15
    seviyeler = {"hata": "Level=1,2", "uyari": "Level=3", "bilgi": "Level=4"}
    ek = seviyeler.get(sade(seviye).strip(), "")
    filtre = "@{LogName=" + _tk(gunluk.strip()) + (";" + ek if ek else "") + "}"
    betik = ("Get-WinEvent -FilterHashtable " + filtre + f" -MaxEvents {adet} -ErrorAction SilentlyContinue | "
             r'ForEach-Object { "{0:dd.MM HH:mm} [{1}] {2}: {3}" -f $_.TimeCreated,$_.LevelDisplayName,$_.ProviderName,'
             r'(([string]$_.Message -split "\r?\n")[0]) }')
    cikti = _ps(betik, 45)
    return cikti if cikti.strip() and cikti != "(çıktı yok)" else "Kayıt bulunamadı (Security günlüğü için yönetici yetkisi gerekir)."


@tool
def zamanlanmis_gorevler(filtre: str = "") -> str:
    """Windows Görev Zamanlayıcı'daki görevleri listeler. filtre boşsa Microsoft'un kendi sistem görevleri gizlenir."""
    ham = subprocess.run(["schtasks", "/Query", "/FO", "CSV", "/NH"], capture_output=True, timeout=30, creationflags=_NOWINDOW)
    metin = _coz(ham.stdout)
    hedef, satirlar = sade(filtre).strip(), []
    for satir in csv.reader(io.StringIO(metin)):
        if len(satir) < 3:
            continue
        ad, sonraki, durum = satir[0], satir[1], satir[2]
        if hedef:
            if hedef not in sade(ad):
                continue
        elif ad.startswith("\\Microsoft\\"):
            continue
        satirlar.append(f"{ad} | sonraki: {sonraki} | {durum}")
    if not satirlar:
        return "Eşleşen zamanlanmış görev yok."
    return f"{len(satirlar)} görev:\n" + "\n".join(satirlar[:50]) + ("\n..." if len(satirlar) > 50 else "")


@tool
def zamanli_gorev_olustur(ad: str, komut: str, zaman: str = "", tekrar: str = "bir_kez") -> str:
    """Windows Görev Zamanlayıcı'ya görev ekler (program kapalıyken de çalışır). ad: görev adı. komut: çalışacak komut/program.
    zaman: 'SS:DD' (örn. '09:00'). tekrar: 'bir_kez', 'her_gun', 'her_hafta', 'her_saat', 'her_dakika', 'oturum_acilinca'."""
    ad, komut = (ad or "").strip(), (komut or "").strip()
    if not ad or not komut:
        return "Hata: ad ve komut gerekli."
    harita = {"bir_kez": "ONCE", "her_gun": "DAILY", "her_hafta": "WEEKLY", "her_saat": "HOURLY", "her_dakika": "MINUTE",
              "oturum_acilinca": "ONLOGON"}
    t = sade(tekrar).strip().replace(" ", "_")
    if t not in harita:
        return "Hata: tekrar " + ", ".join(harita) + " olmalı."
    if t != "oturum_acilinca" and not re.fullmatch(r"\d{1,2}:\d{2}", (zaman or "").strip()) and t in ("bir_kez", "her_gun", "her_hafta"):
        return "Hata: zaman 'SS:DD' biçiminde olmalı (örn. 09:00)."
    if not izinler.onay_iste(f"Zamanlanmış görev oluşturulacak: {ad}", f"{komut}\nZaman: {zaman or '-'} · Tekrar: {t}", seviye=3):
        return izinler.RED_MESAJI
    arglar = ["schtasks", "/Create", "/TN", ad, "/TR", komut, "/SC", harita[t], "/F"]
    if t in ("bir_kez", "her_gun", "her_hafta", "her_saat", "her_dakika") and (zaman or "").strip():
        arglar += ["/ST", zaman.strip().zfill(5)]
    return _calistir(arglar, 30)


@tool
def zamanli_gorev_sil(ad: str) -> str:
    """Windows Görev Zamanlayıcı'dan bir görevi siler. ad: zamanlanmis_gorevler çıktısındaki görev adı."""
    ad = (ad or "").strip()
    if not ad:
        return "Hata: Görev adı boş."
    if not izinler.onay_iste(f"Zamanlanmış görev silinecek: {ad}", seviye=2):
        return izinler.RED_MESAJI
    return _calistir(["schtasks", "/Delete", "/TN", ad, "/F"], 30)


@tool
def ortam_degiskeni(ad: str = "", deger: str = "", kalici: bool = False) -> str:
    """Ortam değişkenlerini yönetir. Hiçbir şey verilmezse tüm adları listeler; yalnızca ad verilirse değerini söyler;
    ad ve deger verilirse ayarlar. kalici=True ise kullanıcı için kalıcı yapar (yeni açılan programlarda geçerli olur)."""
    ad = (ad or "").strip()
    if not ad:
        return ", ".join(sorted(os.environ))[:3000]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", ad):
        return "Hata: Geçersiz değişken adı."
    if not deger:
        v = os.environ.get(ad)
        return f"{ad} = {v}" if v is not None else f"'{ad}' tanımlı değil."
    if not izinler.onay_iste(f"Ortam değişkeni ayarlanacak: {ad}", f"{deger[:200]} ({'kalıcı' if kalici else 'yalnızca bu oturum'})", seviye=2):
        return izinler.RED_MESAJI
    os.environ[ad] = deger
    if kalici:
        return f"{ad} kalıcı olarak ayarlandı. " + _calistir(["setx", ad, deger], 15)
    return f"{ad} bu oturum için ayarlandı."


ARACLAR = [
    get_time, get_system_status, get_detailed_hardware_info, wmi_sorgu, pil_durumu,
    disk_durumu, ag_durumu, ag_baglantilari, ag_trafigi, ekran_parlakligi,
    ekran_bilgisi, yazicilar_listele, bilgisayari_kilitla, guc_islemi, guc_iptal,
    servis_listele, servis_islem, kayit_defteri_oku, kayit_defteri_yaz, kayit_defteri_sil,
    olay_gunlugu, zamanlanmis_gorevler, zamanli_gorev_olustur, zamanli_gorev_sil, ortam_degiskeni,
]
