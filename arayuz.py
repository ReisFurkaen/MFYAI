"""
MFY AI - Masaüstü Arayüzü (PySide6 / Qt)
Bu dosya SADECE arayüzle ilgilenir. Yapay zeka mantığı ai_servisi.py + beyin.py'de,
dosya kaydetme işleri depolama.py'de bulunur.

Kurulum:  pip install PySide6
"""
import re
import sys
import threading
import webbrowser
from string import Template

from PySide6.QtCore import Qt, QTimer, Signal, Property, QPropertyAnimation
from PySide6.QtGui import QColor, QFont, QPainter, QPalette, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QListWidget, QListWidgetItem, QScrollArea, QStackedWidget,
    QTextEdit, QSlider, QMessageBox, QInputDialog, QMenu, QAbstractButton,
    QAbstractItemView, QGraphicsOpacityEffect, QSizePolicy, QButtonGroup, QLineEdit, QComboBox,
)

import config
from ai_servisi import AIServisi, dusunceyi_temizle
from depolama import OturumDeposu, AyarDeposu
from hafiza import profil, hassas_mi
import arac_secici
from ses_yoneticisi import SesYoneticisi
from ses_cikis import SES_ADLARI

# ============================================================
# AYARLAR
# ============================================================
EKRANDA_MAKS_MESAJ = 120     # Bir sohbet açılırken ekrana çizilecek en fazla mesaj (hız için)
ICERIK_GENISLIGI = 920       # Sohbet sütununun en fazla genişliği (px)

ONERILER = [
    "YouTube'da rahatlatıcı bir şarkı aç",
    "Bilgisayarımın durumu nasıl?",
    "Masaüstündeki klasörleri düzenle",
    "Ekranıma bakıp ne yaptığımı anlat",
]

# ============================================================
# TEMALAR
# ============================================================
TEMALAR = {
    "light": dict(
        bg="#f3f5fa", panel="#ffffff", kart="#ffffff", kart2="#eef1f8", sinir="#e1e5ef",
        metin="#1a1f2c", soluk="#6a7387", vurgu="#2a7fff", vurgu_h="#1f6ed4", vurgu_metin="#ffffff",
        kullanici="#2a7fff", kullanici_metin="#ffffff", secili="#e6efff",
        scroll="#cbd1de", scroll_h="#aab2c6",
        hata="#d9534f", basari="#1e9e4f", uyari="#c98a00",
    ),
    "dark": dict(
        bg="#0e1116", panel="#12151b", kart="#171b22", kart2="#1f242d", sinir="#272d38",
        metin="#e7eaf0", soluk="#8b94a6", vurgu="#3d8bff", vurgu_h="#5c9fff", vurgu_metin="#ffffff",
        kullanici="#2f6fe0", kullanici_metin="#ffffff", secili="#1c2636",
        scroll="#2d3441", scroll_h="#3b4455",
        hata="#ef6b66", basari="#3ccf7a", uyari="#f0b429",
    ),
}

TEMA = dict(TEMALAR["light"])  # şu an aktif tema (özel çizilen widget'lar buradan okur)


def _rgba(hex_renk: str, yuzde: int) -> str:
    c = QColor(hex_renk)
    return f"rgba({c.red()},{c.green()},{c.blue()},{yuzde}%)"


QSS_SABLON = Template("""
QMainWindow { background: ${bg}; }
QWidget#kok { background: ${bg}; }

/* ---------- Kaydırma çubuğu ---------- */
QScrollArea, QScrollArea > QWidget, #mesajAlani { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: ${scroll}; border-radius: 4px; min-height: 36px; }
QScrollBar::handle:vertical:hover { background: ${scroll_h}; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { height: 0; }

/* ---------- Yan menü ---------- */
#kenar { background: ${panel}; border-right: 1px solid ${sinir}; }
QLabel#logo { color: ${vurgu}; font-size: 24px; font-weight: 700; background: transparent; }
QLabel#logoAlt { color: ${soluk}; font-size: 12px; background: transparent; }
QLabel#bolumEtiketi { color: ${soluk}; font-size: 11px; font-weight: 700; background: transparent; padding-left: 6px; }
QPushButton#yeniSohbet { background: ${vurgu}; color: ${vurgu_metin}; border: none; border-radius: 12px;
    padding: 12px; font-size: 14px; font-weight: 600; }
QPushButton#yeniSohbet:hover { background: ${vurgu_h}; }
QListWidget#gecmis { background: transparent; border: none; outline: none; }
QListWidget#gecmis::item { color: ${metin}; padding: 10px 12px; border-radius: 10px; margin: 1px 0; font-size: 13px; }
QListWidget#gecmis::item:hover { background: ${kart2}; }
QListWidget#gecmis::item:selected, QListWidget#gecmis::item:selected:!active { background: ${secili}; color: ${vurgu}; }
QPushButton#kenarDugme { background: transparent; color: ${metin}; border: none; border-radius: 10px;
    padding: 11px 12px; text-align: left; font-size: 13px; font-weight: 600; }
QPushButton#kenarDugme:hover { background: ${kart2}; }
QPushButton#kenarDugme:checked { background: ${secili}; color: ${vurgu}; }

/* ---------- Üst çubuk ---------- */
QLabel#sohbetBasligi { color: ${metin}; font-size: 16px; font-weight: 600; background: transparent; }
QLabel#durum { padding: 5px 13px; border-radius: 13px; font-size: 12px; font-weight: 600; }
QLabel#durum[durum="yukleniyor"] { color: ${uyari}; background: ${uyari_bg}; }
QLabel#durum[durum="hazir"] { color: ${basari}; background: ${basari_bg}; }
QLabel#durum[durum="dusunuyor"] { color: ${vurgu}; background: ${vurgu_bg}; }
QLabel#durum[durum="hata"] { color: ${hata}; background: ${hata_bg}; }

/* ---------- Hoş geldin ekranı ---------- */
QLabel#hosgeldinBaslik { color: ${metin}; font-size: 32px; font-weight: 700; background: transparent; }
QLabel#hosgeldinAlt { color: ${soluk}; font-size: 14px; background: transparent; }
QPushButton#oneri { background: ${kart}; color: ${metin}; border: 1px solid ${sinir}; border-radius: 14px;
    padding: 14px 18px; font-size: 13px; text-align: left; }
QPushButton#oneri:hover { border-color: ${vurgu}; color: ${vurgu}; }

/* ---------- Mesajlar ---------- */
#kullaniciBalon { background: ${kullanici}; border-radius: 18px; }
#kullaniciBalon QLabel { color: ${kullanici_metin}; background: transparent; font-size: ${punto}px; }
#aiBalon { background: ${kart}; border: 1px solid ${sinir}; border-radius: 18px; }
#aiBalon QLabel#mesajMetni { color: ${metin}; background: transparent; font-size: ${punto}px; }
QLabel#gonderen { color: ${vurgu}; font-size: 11px; font-weight: 700; background: transparent; }
QPushButton#kopyala { background: transparent; color: ${soluk}; border: none; border-radius: 6px;
    font-size: 11px; padding: 3px 8px; }
QPushButton#kopyala:hover { color: ${vurgu}; background: ${kart2}; }

/* ---------- Giriş alanı ---------- */
QFrame#girisKapsayici { background: ${kart}; border: 1px solid ${sinir}; border-radius: 24px; }
QFrame#girisKapsayici[odak="evet"] { border: 1px solid ${vurgu}; }
QTextEdit#giris { background: transparent; border: none; color: ${metin}; font-size: ${punto}px;
    selection-background-color: ${vurgu}; selection-color: #ffffff; }
QPushButton#gonder { background: ${vurgu}; color: ${vurgu_metin}; border: none; border-radius: 19px;
    font-size: 19px; font-weight: 700; }
QPushButton#gonder:hover { background: ${vurgu_h}; }
QPushButton#gonder:disabled { background: ${sinir}; color: ${soluk}; }

/* ---------- Ayarlar sayfası ---------- */
QLabel#sayfaBasligi { color: ${metin}; font-size: 28px; font-weight: 700; background: transparent; }
QFrame#ayarKarti { background: ${kart}; border: 1px solid ${sinir}; border-radius: 16px; }
QLabel#ayarEtiket { color: ${metin}; font-size: 14px; font-weight: 600; background: transparent; }
QLabel#ayarAciklama { color: ${soluk}; font-size: 12px; background: transparent; }
QLabel#ayarDeger { color: ${vurgu}; font-size: 13px; font-weight: 700; background: transparent; }
QPushButton#temaDugme { background: ${kart2}; color: ${metin}; border: 1px solid ${sinir}; border-radius: 10px;
    padding: 9px 22px; font-size: 13px; }
QPushButton#temaDugme:checked { background: ${vurgu}; color: ${vurgu_metin}; border-color: ${vurgu}; }
QSlider::groove:horizontal { height: 6px; background: ${sinir}; border-radius: 3px; }
QSlider::sub-page:horizontal { background: ${vurgu}; border-radius: 3px; }
QSlider::handle:horizontal { background: #ffffff; border: 2px solid ${vurgu}; width: 16px; height: 16px;
    margin: -7px 0; border-radius: 10px; }

/* ---------- Sesli konuşma ---------- */
QLabel#durum[durum="dinliyor"] { color: ${basari}; background: ${basari_bg}; }
QLabel#durum[durum="cozumluyor"] { color: ${uyari}; background: ${uyari_bg}; }
QLabel#durum[durum="konusuyor"] { color: ${vurgu}; background: ${vurgu_bg}; }
QPushButton#mikrofon { background: ${kart2}; color: ${metin}; border: 1px solid ${sinir}; border-radius: 19px; font-size: 16px; }
QPushButton#mikrofon:hover { border-color: ${vurgu}; }
QPushButton#mikrofon[aktif="evet"] { background: ${hata}; color: #ffffff; border-color: ${hata}; }
QPushButton#sustur { background: transparent; color: ${soluk}; border: 1px solid ${sinir}; border-radius: 19px; font-size: 14px; }
QPushButton#sustur:hover { color: ${hata}; border-color: ${hata}; }
QPushButton#ellerSerbest { background: transparent; color: ${soluk}; border: 1px solid ${sinir}; border-radius: 13px;
    padding: 5px 14px; font-size: 12px; font-weight: 600; }
QPushButton#ellerSerbest:hover { border-color: ${vurgu}; color: ${vurgu}; }
QPushButton#ellerSerbest:checked { background: ${basari_bg}; color: ${basari}; border-color: ${basari}; }
QComboBox { background: ${kart2}; color: ${metin}; border: 1px solid ${sinir}; border-radius: 8px; padding: 7px 12px;
    min-width: 230px; font-size: 13px; }
QComboBox:hover { border-color: ${vurgu}; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: ${kart}; color: ${metin}; border: 1px solid ${sinir};
    selection-background-color: ${secili}; selection-color: ${vurgu}; outline: none; }

/* ---------- Hafıza sayfası ---------- */
QFrame#bilgiSatiri { background: ${kart}; border: 1px solid ${sinir}; border-radius: 14px; }
QLabel#bilgiKonu { color: ${vurgu}; font-size: 12px; font-weight: 700; background: transparent; }
QLabel#bilgiDeger { color: ${metin}; font-size: 14px; background: transparent; }
QLabel#bilgiAlt { color: ${soluk}; font-size: 11px; background: transparent; }
QPushButton#silDugme { background: transparent; color: ${soluk}; border: 1px solid ${sinir}; border-radius: 8px;
    padding: 6px 14px; font-size: 12px; }
QPushButton#silDugme:hover { color: ${hata}; border-color: ${hata}; }
QPushButton#ekleDugme { background: ${vurgu}; color: ${vurgu_metin}; border: none; border-radius: 10px;
    padding: 9px 22px; font-size: 13px; font-weight: 600; }
QPushButton#ekleDugme:hover { background: ${vurgu_h}; }

/* ---------- Bildirim, menü, pencereler ---------- */
QLabel#toast { background: ${vurgu}; color: #ffffff; border-radius: 18px; padding: 10px 22px;
    font-size: 13px; font-weight: 600; }
QLabel#toast[hata="evet"] { background: ${hata}; }
QMenu { background: ${kart}; color: ${metin}; border: 1px solid ${sinir}; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 8px 22px; border-radius: 6px; }
QMenu::item:selected { background: ${secili}; color: ${vurgu}; }
QMessageBox, QInputDialog, QDialog { background: ${kart}; }
QMessageBox QLabel, QInputDialog QLabel { color: ${metin}; background: transparent; }
QDialog QPushButton { background: ${kart2}; color: ${metin}; border: 1px solid ${sinir}; border-radius: 8px;
    padding: 7px 18px; min-width: 76px; }
QDialog QPushButton:hover { border-color: ${vurgu}; }
QLineEdit { background: ${kart2}; color: ${metin}; border: 1px solid ${sinir}; border-radius: 8px; padding: 6px 10px; }
QToolTip { background: ${kart}; color: ${metin}; border: 1px solid ${sinir}; padding: 4px 8px; }
""")


def stil_olustur(t: dict, punto: int) -> str:
    degerler = dict(t)
    degerler["punto"] = punto
    degerler["basari_bg"] = _rgba(t["basari"], 14)
    degerler["uyari_bg"] = _rgba(t["uyari"], 14)
    degerler["vurgu_bg"] = _rgba(t["vurgu"], 14)
    degerler["hata_bg"] = _rgba(t["hata"], 14)
    return QSS_SABLON.safe_substitute(**degerler)


# ============================================================
# YARDIMCI FONKSİYONLAR
# ============================================================
def md_hazirla(metin: str) -> str:
    """Tek satır sonlarını gerçek satır sonu yapar (sohbet metinleri için daha doğal görünür)."""
    return re.sub(r"(?<!\n)\n(?!\n)", "  \n", metin)


def baglanti_ac(url: str):
    if url.startswith(("http://", "https://")):
        webbrowser.open(url)


def ortala(icerik: QWidget, maks_genislik: int) -> QWidget:
    """İçeriği ortalar ve genişliğini sınırlar."""
    kap = QWidget()
    duzen = QHBoxLayout(kap)
    duzen.setContentsMargins(0, 0, 0, 0)
    duzen.setSpacing(0)
    icerik.setMaximumWidth(maks_genislik)
    duzen.addStretch(1)
    duzen.addWidget(icerik, 1000)
    duzen.addStretch(1)
    return kap


# ============================================================
# ÖZEL WIDGET'LAR
# ============================================================
class Anahtar(QAbstractButton):
    """Animasyonlu açma/kapama anahtarı (toggle switch)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._konum = 0.0
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(48, 26)
        self._anim = QPropertyAnimation(self, b"konum", self)
        self._anim.setDuration(150)
        self.toggled.connect(self._animasyon)

    def _konum_al(self):
        return self._konum

    def _konum_ayarla(self, deger):
        self._konum = deger
        self.update()

    konum = Property(float, _konum_al, _konum_ayarla)

    def _animasyon(self, acik):
        self._anim.stop()
        self._anim.setStartValue(self._konum)
        self._anim.setEndValue(1.0 if acik else 0.0)
        self._anim.start()

    def paintEvent(self, olay):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        kapali, acik = QColor(TEMA["sinir"]), QColor(TEMA["vurgu"])
        k = self._konum
        renk = QColor(
            int(kapali.red() + (acik.red() - kapali.red()) * k),
            int(kapali.green() + (acik.green() - kapali.green()) * k),
            int(kapali.blue() + (acik.blue() - kapali.blue()) * k),
        )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(renk)
        h = self.height()
        p.drawRoundedRect(self.rect(), h / 2, h / 2)
        cap = h - 6
        x = 3 + (self.width() - cap - 6) * k
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(int(x), 3, cap, cap)


class Toast(QLabel):
    """Ekranın altında kısa süre görünen bildirim."""

    def __init__(self, ebeveyn):
        super().__init__(ebeveyn)
        self.setObjectName("toast")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._efekt = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._efekt)
        self._anim = QPropertyAnimation(self._efekt, b"opacity", self)
        self._anim.setDuration(220)
        self._anim.finished.connect(self._animasyon_bitti)
        self._kapaniyor = False
        self._zamanlayici = QTimer(self)
        self._zamanlayici.setSingleShot(True)
        self._zamanlayici.timeout.connect(self._gizle)
        self.hide()

    def goster(self, metin: str, hata: bool = False):
        self.setProperty("hata", "evet" if hata else "hayir")
        self.style().unpolish(self)
        self.style().polish(self)
        self.setText(metin)
        self.adjustSize()
        ebeveyn = self.parentWidget()
        self.move((ebeveyn.width() - self.width()) // 2, ebeveyn.height() - self.height() - 125)
        self._kapaniyor = False
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self.show()
        self.raise_()
        self._zamanlayici.start(2600)

    def _gizle(self):
        self._kapaniyor = True
        self._anim.stop()
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _animasyon_bitti(self):
        if self._kapaniyor:
            self.hide()


class GirisKutusu(QTextEdit):
    """Yazdıkça uzayan mesaj kutusu. Enter gönderir, Shift+Enter alt satıra geçer."""
    gonder_istendi = Signal()
    odak_degisti = Signal(bool)

    def __init__(self):
        super().__init__()
        self.setObjectName("giris")
        self.setAcceptRichText(False)
        self.setPlaceholderText("Bir mesaj yaz…")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.enter_gonderir = True
        self.document().documentLayout().documentSizeChanged.connect(self._boyutla)
        self._boyutla()

    def _boyutla(self, *args):
        yukseklik = int(self.document().size().height()) + 16
        self.setFixedHeight(max(40, min(yukseklik, 170)))

    def keyPressEvent(self, olay):
        enter = olay.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        shift = bool(olay.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if enter and not shift and self.enter_gonderir:
            self.gonder_istendi.emit()
            return
        super().keyPressEvent(olay)

    def focusInEvent(self, olay):
        self.odak_degisti.emit(True)
        super().focusInEvent(olay)

    def focusOutEvent(self, olay):
        self.odak_degisti.emit(False)
        super().focusOutEvent(olay)


class MesajSatiri(QWidget):
    """Tek bir mesaj balonu (kullanıcı ya da asistan)."""

    def __init__(self, metin: str, ai_mi: bool, akiyor: bool = False):
        super().__init__()
        self.ai_mi = ai_mi
        self.ham_metin = metin

        satir = QHBoxLayout(self)
        satir.setContentsMargins(0, 0, 0, 0)
        satir.setSpacing(0)

        self.balon = QFrame()
        self.balon.setObjectName("aiBalon" if ai_mi else "kullaniciBalon")
        self.balon.setMaximumWidth(ICERIK_GENISLIGI if ai_mi else 680)
        ic = QVBoxLayout(self.balon)
        ic.setContentsMargins(18, 12, 18, 10 if ai_mi else 12)
        ic.setSpacing(4)

        if ai_mi:
            self.balon.setMinimumWidth(130)
            baslik = QLabel("MFY AI")
            baslik.setObjectName("gonderen")
            ic.addWidget(baslik)

        self.etiket = QLabel()
        self.etiket.setObjectName("mesajMetni")
        self.etiket.setWordWrap(True)
        self.etiket.setTextFormat(Qt.TextFormat.MarkdownText if ai_mi else Qt.TextFormat.PlainText)
        self.etiket.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse |
                                            Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.etiket.setOpenExternalLinks(False)
        self.etiket.linkActivated.connect(baglanti_ac)
        self.etiket.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        ic.addWidget(self.etiket)

        self.kopyala_dugmesi = None
        if ai_mi:
            self.kopyala_dugmesi = QPushButton("Kopyala")
            self.kopyala_dugmesi.setObjectName("kopyala")
            self.kopyala_dugmesi.setCursor(Qt.CursorShape.PointingHandCursor)
            self.kopyala_dugmesi.clicked.connect(self._kopyala)
            self.kopyala_dugmesi.setVisible(not akiyor)
            ic.addWidget(self.kopyala_dugmesi, 0, Qt.AlignmentFlag.AlignRight)

        if ai_mi:
            satir.addWidget(self.balon)
            satir.addStretch(1)
        else:
            satir.addStretch(1)
            satir.addWidget(self.balon)

        self.metni_ayarla(metin)

    def metni_ayarla(self, metin: str):
        self.ham_metin = metin
        self.etiket.setText(md_hazirla(metin) if self.ai_mi else metin)

    def tamamla(self):
        """Akış bittiğinde kopyala düğmesini gösterir."""
        if self.kopyala_dugmesi is not None:
            self.kopyala_dugmesi.setVisible(True)

    def _kopyala(self):
        QApplication.clipboard().setText(self.ham_metin)
        self.kopyala_dugmesi.setText("Kopyalandı ✓")
        QTimer.singleShot(1400, self._kopya_sifirla)

    def _kopya_sifirla(self):
        try:
            self.kopyala_dugmesi.setText("Kopyala")
        except RuntimeError:
            pass  # widget bu arada silinmiş olabilir


class Hosgeldin(QWidget):
    """Boş sohbet ekranı: karşılama ve öneri düğmeleri."""
    oneri_secildi = Signal(str)

    def __init__(self):
        super().__init__()
        duzen = QVBoxLayout(self)
        duzen.setContentsMargins(40, 0, 40, 40)
        duzen.addStretch(3)

        baslik = QLabel("Merhaba, ben MFY AI")
        baslik.setObjectName("hosgeldinBaslik")
        baslik.setAlignment(Qt.AlignmentFlag.AlignCenter)
        duzen.addWidget(baslik)

        self.alt = QLabel("Bilgisayarını senin için yönetmeye hazırım. Ne yapmamı istersin?")
        self.alt.setObjectName("hosgeldinAlt")
        self.alt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.alt.setWordWrap(True)
        duzen.addWidget(self.alt)
        duzen.addSpacing(26)

        izgara_kap = QWidget()
        izgara = QGridLayout(izgara_kap)
        izgara.setContentsMargins(0, 0, 0, 0)
        izgara.setSpacing(12)
        for i, metin in enumerate(ONERILER):
            dugme = QPushButton(metin)
            dugme.setObjectName("oneri")
            dugme.setCursor(Qt.CursorShape.PointingHandCursor)
            dugme.clicked.connect(lambda _=False, m=metin: self.oneri_secildi.emit(m))
            izgara.addWidget(dugme, i // 2, i % 2)
        duzen.addWidget(ortala(izgara_kap, 620))
        duzen.addStretch(4)

    def alt_metin_ayarla(self, metin: str):
        self.alt.setText(metin)


# ============================================================
# ANA PENCERE
# ============================================================
class AnaPencere(QMainWindow):
    # Arka plan thread'lerinden arayüze güvenli geçiş için sinyaller
    sig_hazir = Signal()
    sig_yukleme_hatasi = Signal(str)
    sig_token = Signal(str)
    sig_cevap = Signal(str, str)
    sig_hata = Signal(str, str)
    sig_onay = Signal(str, object)
    sig_bildirim = Signal(str)
    sig_ses_durum = Signal(str, str)
    sig_ses_metin = Signal(str)
    sig_ses_bilgi = Signal(str)
    sig_ses_hata = Signal(str)
    sig_ses_hazir = Signal()
    sig_ses_eller_serbest = Signal(bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MFY AI - Akıllı Asistan")
        self.resize(1280, 840)
        self.setMinimumSize(920, 620)

        # --- Ayarlar ve depolar ---
        self.ayarlar = AyarDeposu()
        tema = self.ayarlar.al("appearance_mode")
        self.ayar_tema = tema if tema in TEMALAR else "light"
        try:
            self.ayar_punto = max(10, min(24, int(float(self.ayarlar.al("font_size")))))
        except (TypeError, ValueError):
            self.ayar_punto = 14
        self.enter_gonderir = bool(self.ayarlar.al("enter_gonderir"))
        self.oturumlar = OturumDeposu()

        # --- Sesli konuşma ayarları ve durumu ---
        self.ayar_ses_cevap = bool(self.ayarlar.al("ses_her_cevap"))
        self.ayar_kulaklik = bool(self.ayarlar.al("ses_kulaklik"))
        self.ayar_ses = str(self.ayarlar.al("ses_ses") or "female_2")
        self.ayar_mikrofon = str(self.ayarlar.al("ses_mikrofon") or "")
        try:
            self.ayar_ses_seviye = max(0, min(100, int(float(self.ayarlar.al("ses_seviye")))))
        except (TypeError, ValueError):
            self.ayar_ses_seviye = 90
        self.ses = None                 # SesYoneticisi: ilk kullanımda yüklenir
        self.ses_hazir = False
        self.ses_yukleniyor = False
        self._ses_bekleyen = []         # ses hazır olunca çalıştırılacak işler
        self._eller_serbest = False     # gizlilik: mikrofon açılışta ASLA kendiliğinden açılmaz
        self._son_sesli = False         # son mesaj mikrofonla mı geldi?

        # --- Durum ---
        self.aktif_oturum = None
        self.dusunuyor = False
        self._akis_oturum = None
        self._akis_metin = ""
        self._akis_satiri = None
        self._token_tamponu = []
        self._nokta = 0
        self._alta_yapis = True

        # --- Zamanlayıcılar ---
        self._flush = QTimer(self)               # token'ları toplu olarak ekrana basar (akıcılık için)
        self._flush.setInterval(33)
        self._flush.timeout.connect(self._akis_isle)
        self._nokta_z = QTimer(self)             # "Düşünüyor..." animasyonu
        self._nokta_z.setInterval(400)
        self._nokta_z.timeout.connect(self._nokta_isle)
        self._stil_z = QTimer(self)              # yazı boyutu değişince stili geciktirerek uygular
        self._stil_z.setSingleShot(True)
        self._stil_z.setInterval(120)
        self._stil_z.timeout.connect(self._punto_uygula)
        self._ayar_kaydet_z = QTimer(self)       # ses seviyesi gibi sık değişen ayarları geciktirerek kaydeder
        self._ayar_kaydet_z.setSingleShot(True)
        self._ayar_kaydet_z.setInterval(500)
        self._ayar_kaydet_z.timeout.connect(self._ayarlari_kaydet)

        # --- Yapay zeka servisi ---
        self.ai = AIServisi()
        self.ai.onay_fonksiyonu_ayarla(self._onay_sor)
        self.ai.bildirim_fonksiyonu_ayarla(self.sig_bildirim.emit)
        self.sig_hazir.connect(self._ai_hazir)
        self.sig_yukleme_hatasi.connect(self._ai_yukleme_hatasi)
        self.sig_token.connect(self._token_geldi)
        self.sig_cevap.connect(self._cevap_geldi)
        self.sig_hata.connect(self._hata_geldi)
        self.sig_onay.connect(self._onay_goster)
        self.sig_bildirim.connect(self._bildirim_geldi)
        self.sig_ses_durum.connect(self._ses_durum_geldi)
        self.sig_ses_metin.connect(self._ses_metin_geldi)
        self.sig_ses_bilgi.connect(self._ses_bilgi_geldi)
        self.sig_ses_hata.connect(self._ses_hata_geldi)
        self.sig_ses_hazir.connect(self._ses_hazir_oldu)
        self.sig_ses_eller_serbest.connect(self._ses_eller_serbest_degisti)

        # --- Arayüz ---
        self._arayuzu_kur()
        self._stili_uygula()
        self._gecmis_yenile()
        self._yeni_sohbet()
        self._gonder_dugmesi_guncelle()

        # Pencere açıldıktan sonra arka planda yüklemeye başla
        self.ai.yukle(on_hazir=self.sig_hazir.emit, on_hata=self.sig_yukleme_hatasi.emit)

    # ============================================================
    # ARAYÜZ KURULUMU
    # ============================================================
    def _arayuzu_kur(self):
        kok = QWidget()
        kok.setObjectName("kok")
        self.setCentralWidget(kok)
        ana = QHBoxLayout(kok)
        ana.setContentsMargins(0, 0, 0, 0)
        ana.setSpacing(0)

        ana.addWidget(self._kenar_cubugu_kur())

        self.sayfalar = QStackedWidget()
        self.sayfalar.addWidget(self._sohbet_sayfasi_kur())    # 0
        self.sayfalar.addWidget(self._ayarlar_sayfasi_kur())   # 1
        self.sayfalar.addWidget(self._hafiza_sayfasi_kur())    # 2
        ana.addWidget(self.sayfalar, 1)

        self.toast = Toast(kok)

        self._kisayol_mikrofon = QShortcut(QKeySequence("F9"), self)
        self._kisayol_mikrofon.activated.connect(self._mikrofon_tikla)
        self._kisayol_sustur = QShortcut(QKeySequence("Escape"), self)
        self._kisayol_sustur.activated.connect(self._sustur)

    def _kenar_cubugu_kur(self) -> QWidget:
        kenar = QFrame()
        kenar.setObjectName("kenar")
        kenar.setFixedWidth(280)
        duzen = QVBoxLayout(kenar)
        duzen.setContentsMargins(16, 24, 16, 16)
        duzen.setSpacing(8)

        logo = QLabel("MFY AI")
        logo.setObjectName("logo")
        duzen.addWidget(logo)
        logo_alt = QLabel("Kişisel bilgisayar asistanı")
        logo_alt.setObjectName("logoAlt")
        duzen.addWidget(logo_alt)
        duzen.addSpacing(14)

        yeni = QPushButton("＋  Yeni Sohbet")
        yeni.setObjectName("yeniSohbet")
        yeni.setCursor(Qt.CursorShape.PointingHandCursor)
        yeni.setMinimumHeight(46)
        yeni.clicked.connect(self._yeni_sohbet)
        duzen.addWidget(yeni)
        duzen.addSpacing(10)

        etiket = QLabel("SOHBETLER")
        etiket.setObjectName("bolumEtiketi")
        duzen.addWidget(etiket)

        self.gecmis = QListWidget()
        self.gecmis.setObjectName("gecmis")
        self.gecmis.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.gecmis.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.gecmis.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.gecmis.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.gecmis.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.gecmis.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.gecmis.customContextMenuRequested.connect(self._gecmis_menusu)
        self.gecmis.itemClicked.connect(self._gecmis_tiklandi)
        duzen.addWidget(self.gecmis, 1)

        self.hafiza_dugmesi = QPushButton("🧠   Hafıza")
        self.hafiza_dugmesi.setObjectName("kenarDugme")
        self.hafiza_dugmesi.setCheckable(True)
        self.hafiza_dugmesi.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hafiza_dugmesi.clicked.connect(self._hafiza_dugmesi_tiklandi)
        duzen.addWidget(self.hafiza_dugmesi)

        self.ayar_dugmesi = QPushButton("⚙   Ayarlar")
        self.ayar_dugmesi.setObjectName("kenarDugme")
        self.ayar_dugmesi.setCheckable(True)
        self.ayar_dugmesi.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ayar_dugmesi.clicked.connect(self._ayar_dugmesi_tiklandi)
        duzen.addWidget(self.ayar_dugmesi)
        return kenar

    def _sohbet_sayfasi_kur(self) -> QWidget:
        sayfa = QWidget()
        duzen = QVBoxLayout(sayfa)
        duzen.setContentsMargins(0, 0, 0, 0)
        duzen.setSpacing(0)

        # Üst çubuk
        ust = QWidget()
        ust_duzen = QHBoxLayout(ust)
        ust_duzen.setContentsMargins(32, 20, 32, 10)
        self.baslik_etiketi = QLabel("Yeni sohbet")
        self.baslik_etiketi.setObjectName("sohbetBasligi")
        ust_duzen.addWidget(self.baslik_etiketi)
        ust_duzen.addStretch(1)
        self.uyandirma_dugmesi = QPushButton("🗣  Hey MFY")
        self.uyandirma_dugmesi.setObjectName("ellerSerbest")
        self.uyandirma_dugmesi.setCheckable(True)
        self.uyandirma_dugmesi.setCursor(Qt.CursorShape.PointingHandCursor)
        self.uyandirma_dugmesi.setToolTip("Sürekli dinler; yalnızca “Hey MFY” dediğinde komutunu alır")
        self.uyandirma_dugmesi.clicked.connect(self._uyandirma_tikla)
        ust_duzen.addWidget(self.uyandirma_dugmesi)
        self.eller_serbest_dugmesi = QPushButton("🎧  Eller serbest")
        self.eller_serbest_dugmesi.setObjectName("ellerSerbest")
        self.eller_serbest_dugmesi.setCheckable(True)
        self.eller_serbest_dugmesi.setCursor(Qt.CursorShape.PointingHandCursor)
        self.eller_serbest_dugmesi.setToolTip("Sürekli dinler; konuşunca otomatik anlar ve cevap verir")
        self.eller_serbest_dugmesi.clicked.connect(self._eller_serbest_tikla)
        ust_duzen.addWidget(self.eller_serbest_dugmesi)
        self.durum_etiketi = QLabel()
        self.durum_etiketi.setObjectName("durum")
        ust_duzen.addWidget(self.durum_etiketi)
        duzen.addWidget(ust)
        self._durum("yukleniyor", "Yükleniyor…")

        # İçerik: hoş geldin ekranı / mesajlar
        self.icerik_yigini = QStackedWidget()
        self.hosgeldin = Hosgeldin()
        self.hosgeldin.oneri_secildi.connect(self._gonder)
        self.icerik_yigini.addWidget(self.hosgeldin)           # 0

        self.kaydirma = QScrollArea()
        self.kaydirma.setWidgetResizable(True)
        self.kaydirma.setFrameShape(QFrame.Shape.NoFrame)
        self.kaydirma.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sutun = QWidget()
        self.mesaj_duzeni = QVBoxLayout(sutun)
        self.mesaj_duzeni.setContentsMargins(24, 12, 24, 20)
        self.mesaj_duzeni.setSpacing(14)
        self.mesaj_duzeni.addStretch(1)
        govde = ortala(sutun, ICERIK_GENISLIGI)
        govde.setObjectName("mesajAlani")
        self.kaydirma.setWidget(govde)
        sb = self.kaydirma.verticalScrollBar()
        sb.rangeChanged.connect(self._aralik_degisti)
        sb.valueChanged.connect(self._kayma_degisti)
        self.icerik_yigini.addWidget(self.kaydirma)            # 1
        duzen.addWidget(self.icerik_yigini, 1)

        # Giriş alanı
        giris_alani = QWidget()
        giris_duzen = QVBoxLayout(giris_alani)
        giris_duzen.setContentsMargins(24, 6, 24, 22)

        self.giris_kapsayici = QFrame()
        self.giris_kapsayici.setObjectName("girisKapsayici")
        self.giris_kapsayici.setProperty("odak", "hayir")
        kap_duzen = QHBoxLayout(self.giris_kapsayici)
        kap_duzen.setContentsMargins(20, 7, 8, 7)
        kap_duzen.setSpacing(8)

        self.giris = GirisKutusu()
        self.giris.enter_gonderir = self.enter_gonderir
        self.giris.gonder_istendi.connect(self._gonder)
        self.giris.odak_degisti.connect(self._giris_odagi)
        kap_duzen.addWidget(self.giris, 1, Qt.AlignmentFlag.AlignBottom)

        self.sustur_dugmesi = QPushButton("■")
        self.sustur_dugmesi.setObjectName("sustur")
        self.sustur_dugmesi.setFixedSize(38, 38)
        self.sustur_dugmesi.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sustur_dugmesi.setToolTip("Asistanı sustur (Esc)")
        self.sustur_dugmesi.clicked.connect(self._sustur)
        self.sustur_dugmesi.setVisible(False)
        kap_duzen.addWidget(self.sustur_dugmesi, 0, Qt.AlignmentFlag.AlignBottom)

        self.mikrofon_dugmesi = QPushButton("🎤")
        self.mikrofon_dugmesi.setObjectName("mikrofon")
        self.mikrofon_dugmesi.setProperty("aktif", "hayir")
        self.mikrofon_dugmesi.setFixedSize(38, 38)
        self.mikrofon_dugmesi.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mikrofon_dugmesi.setToolTip("Konuş (F9)")
        self.mikrofon_dugmesi.clicked.connect(self._mikrofon_tikla)
        kap_duzen.addWidget(self.mikrofon_dugmesi, 0, Qt.AlignmentFlag.AlignBottom)

        self.gonder_dugmesi = QPushButton("↑")
        self.gonder_dugmesi.setObjectName("gonder")
        self.gonder_dugmesi.setFixedSize(38, 38)
        self.gonder_dugmesi.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gonder_dugmesi.clicked.connect(lambda: self._gonder())
        kap_duzen.addWidget(self.gonder_dugmesi, 0, Qt.AlignmentFlag.AlignBottom)

        giris_duzen.addWidget(ortala(self.giris_kapsayici, ICERIK_GENISLIGI))
        duzen.addWidget(giris_alani)
        return sayfa

    def _ayarlar_sayfasi_kur(self) -> QWidget:
        sayfa = QWidget()
        duzen = QVBoxLayout(sayfa)
        duzen.setContentsMargins(48, 36, 48, 36)
        duzen.setSpacing(16)

        baslik = QLabel("Ayarlar")
        baslik.setObjectName("sayfaBasligi")
        duzen.addWidget(baslik)
        duzen.addSpacing(6)

        # Kartlar çok olduğu için kaydırılabilir alan (bundan sonra 'duzen' bu iç düzene işaret eder)
        dis_duzen = duzen
        kaydirma_ayar = QScrollArea()
        kaydirma_ayar.setWidgetResizable(True)
        kaydirma_ayar.setFrameShape(QFrame.Shape.NoFrame)
        kaydirma_ayar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        ic_govde = QWidget()
        ic_govde.setObjectName("mesajAlani")
        duzen = QVBoxLayout(ic_govde)
        duzen.setContentsMargins(0, 0, 12, 0)
        duzen.setSpacing(16)
        kaydirma_ayar.setWidget(ic_govde)
        dis_duzen.addWidget(kaydirma_ayar, 1)

        # Tema
        tema_kap = QWidget()
        tema_duzen = QHBoxLayout(tema_kap)
        tema_duzen.setContentsMargins(0, 0, 0, 0)
        tema_duzen.setSpacing(8)
        self.tema_grubu = QButtonGroup(self)
        self.tema_grubu.setExclusive(True)
        self.tema_dugmeleri = {}
        for kod, ad in (("light", "Açık"), ("dark", "Koyu")):
            d = QPushButton(ad)
            d.setObjectName("temaDugme")
            d.setCheckable(True)
            d.setCursor(Qt.CursorShape.PointingHandCursor)
            d.setChecked(kod == self.ayar_tema)
            d.clicked.connect(lambda _=False, k=kod: self._tema_sec(k))
            self.tema_grubu.addButton(d)
            tema_duzen.addWidget(d)
            self.tema_dugmeleri[kod] = d
        duzen.addWidget(self._ayar_karti("Görünüm", "Açık veya koyu tema arasında geçiş yap.", tema_kap))

        # Yazı boyutu
        boyut_kap = QWidget()
        boyut_duzen = QHBoxLayout(boyut_kap)
        boyut_duzen.setContentsMargins(0, 0, 0, 0)
        boyut_duzen.setSpacing(12)
        self.punto_slider = QSlider(Qt.Orientation.Horizontal)
        self.punto_slider.setRange(10, 24)
        self.punto_slider.setValue(self.ayar_punto)
        self.punto_slider.setFixedWidth(220)
        self.punto_degeri = QLabel(f"{self.ayar_punto} px")
        self.punto_degeri.setObjectName("ayarDeger")
        self.punto_degeri.setMinimumWidth(40)
        self.punto_slider.valueChanged.connect(self._punto_degisti)
        boyut_duzen.addWidget(self.punto_slider)
        boyut_duzen.addWidget(self.punto_degeri)
        duzen.addWidget(self._ayar_karti("Metin boyutu", "Sohbetteki yazıların boyutunu ayarla.", boyut_kap))

        # Enter ile gönder
        self.enter_anahtari = Anahtar()
        self.enter_anahtari.setChecked(self.enter_gonderir)
        self.enter_anahtari.toggled.connect(self._enter_degisti)
        duzen.addWidget(self._ayar_karti("Enter ile gönder",
                                         "Kapalıysa Enter alt satıra geçer, gönderme düğmesini kullanırsın. "
                                         "Shift+Enter her zaman alt satıra geçer.", self.enter_anahtari))

        # --- Sesli konuşma ---
        self.ses_cevap_anahtari = Anahtar()
        self.ses_cevap_anahtari.setChecked(self.ayar_ses_cevap)
        self.ses_cevap_anahtari.toggled.connect(self._ses_cevap_degisti)
        duzen.addWidget(self._ayar_karti("Her cevabı sesli oku",
                                         "Kapalıyken asistan yalnızca mikrofonla konuştuğunda sesli cevap verir.",
                                         self.ses_cevap_anahtari))

        self.kulaklik_anahtari = Anahtar()
        self.kulaklik_anahtari.setChecked(self.ayar_kulaklik)
        self.kulaklik_anahtari.toggled.connect(self._kulaklik_degisti)
        duzen.addWidget(self._ayar_karti("Kulaklık kullanıyorum",
                                         "Açıkken asistan konuşurken araya girip lafını kesebilirsin. Hoparlör kullanıyorsan "
                                         "kapalı bırak, yoksa asistan kendi sesini duyup kendiyle konuşabilir.",
                                         self.kulaklik_anahtari))

        ses_kap = QWidget()
        ses_duzen = QHBoxLayout(ses_kap)
        ses_duzen.setContentsMargins(0, 0, 0, 0)
        ses_duzen.setSpacing(10)
        self.ses_combo = QComboBox()
        for kod, ad in SES_ADLARI.items():
            self.ses_combo.addItem(ad, kod)
        indeks = self.ses_combo.findData(self.ayar_ses)
        self.ses_combo.setCurrentIndex(indeks if indeks >= 0 else 1)
        self.ses_combo.currentIndexChanged.connect(self._ses_secildi)
        dene = QPushButton("Dene")
        dene.setObjectName("ekleDugme")
        dene.setCursor(Qt.CursorShape.PointingHandCursor)
        dene.clicked.connect(self._ses_dene)
        ses_duzen.addWidget(self.ses_combo)
        ses_duzen.addWidget(dene)
        duzen.addWidget(self._ayar_karti("Asistanın sesi", "Konuşma sesini seç ve 'Dene' ile dinle.", ses_kap))

        self.mikrofon_combo = QComboBox()
        self._mikrofonlari_doldur()
        self.mikrofon_combo.currentIndexChanged.connect(self._mikrofon_secildi)
        duzen.addWidget(self._ayar_karti("Mikrofon", "Konuşmak için kullanılacak mikrofon.", self.mikrofon_combo))

        seviye_kap = QWidget()
        seviye_duzen = QHBoxLayout(seviye_kap)
        seviye_duzen.setContentsMargins(0, 0, 0, 0)
        seviye_duzen.setSpacing(12)
        self.ses_seviye_slider = QSlider(Qt.Orientation.Horizontal)
        self.ses_seviye_slider.setRange(0, 100)
        self.ses_seviye_slider.setValue(self.ayar_ses_seviye)
        self.ses_seviye_slider.setFixedWidth(220)
        self.ses_seviye_degeri = QLabel(f"%{self.ayar_ses_seviye}")
        self.ses_seviye_degeri.setObjectName("ayarDeger")
        self.ses_seviye_degeri.setMinimumWidth(40)
        self.ses_seviye_slider.valueChanged.connect(self._ses_seviye_degisti)
        seviye_duzen.addWidget(self.ses_seviye_slider)
        seviye_duzen.addWidget(self.ses_seviye_degeri)
        duzen.addWidget(self._ayar_karti("Asistanın ses seviyesi", "Yalnızca asistanın konuşma sesini etkiler (Windows sesini değil).", seviye_kap))

        # Hakkında
        hakkinda = QLabel(f"MFY AI  ·  Model sağlayıcı: {config.SAGLAYICI}")
        hakkinda.setObjectName("ayarAciklama")
        duzen.addWidget(self._ayar_karti("Hakkında",
                                         "Yerel modeller ve LangChain ile çalışan, kişisel kullanım için "
                                         "geliştirilmiş bilgisayar asistanı.", hakkinda))
        duzen.addStretch(1)
        return sayfa

    # ============================================================
    # HAFIZA SAYFASI (asistanın senin hakkında bildikleri)
    # ============================================================
    def _hafiza_sayfasi_kur(self) -> QWidget:
        sayfa = QWidget()
        duzen = QVBoxLayout(sayfa)
        duzen.setContentsMargins(48, 36, 48, 28)
        duzen.setSpacing(14)

        baslik = QLabel("Hafıza")
        baslik.setObjectName("sayfaBasligi")
        duzen.addWidget(baslik)
        aciklama = QLabel("MFY AI'nın senin hakkında bildikleri. Sohbet ettikçe kendiliğinden öğrenir; "
                          "istediğini silebilir ya da kendin ekleyebilirsin.")
        aciklama.setObjectName("ayarAciklama")
        aciklama.setWordWrap(True)
        duzen.addWidget(aciklama)

        ekle_kart = QFrame()
        ekle_kart.setObjectName("ayarKarti")
        ekle_duzen = QHBoxLayout(ekle_kart)
        ekle_duzen.setContentsMargins(18, 14, 14, 14)
        ekle_duzen.setSpacing(10)
        self.hafiza_konu_girisi = QLineEdit()
        self.hafiza_konu_girisi.setPlaceholderText("Konu (örn. yaşadığım şehir)")
        self.hafiza_konu_girisi.setMaximumWidth(280)
        self.hafiza_bilgi_girisi = QLineEdit()
        self.hafiza_bilgi_girisi.setPlaceholderText("Bilgi (örn. İstanbul)")
        self.hafiza_bilgi_girisi.returnPressed.connect(self._bilgi_ekle)
        ekle_dugme = QPushButton("Ekle")
        ekle_dugme.setObjectName("ekleDugme")
        ekle_dugme.setCursor(Qt.CursorShape.PointingHandCursor)
        ekle_dugme.clicked.connect(self._bilgi_ekle)
        ekle_duzen.addWidget(self.hafiza_konu_girisi, 1)
        ekle_duzen.addWidget(self.hafiza_bilgi_girisi, 2)
        ekle_duzen.addWidget(ekle_dugme)
        duzen.addWidget(ekle_kart)

        self.hafiza_kaydirma = QScrollArea()
        self.hafiza_kaydirma.setWidgetResizable(True)
        self.hafiza_kaydirma.setFrameShape(QFrame.Shape.NoFrame)
        self.hafiza_kaydirma.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        liste_govde = QWidget()
        liste_govde.setObjectName("mesajAlani")
        self.hafiza_liste = QVBoxLayout(liste_govde)
        self.hafiza_liste.setContentsMargins(0, 4, 8, 4)
        self.hafiza_liste.setSpacing(8)
        self.hafiza_liste.addStretch(1)
        self.hafiza_kaydirma.setWidget(liste_govde)
        duzen.addWidget(self.hafiza_kaydirma, 1)

        self.hafiza_durum = QLabel()
        self.hafiza_durum.setObjectName("ayarAciklama")
        duzen.addWidget(self.hafiza_durum)
        return sayfa

    def _bilgi_satiri(self, kayit: dict) -> QFrame:
        satir = QFrame()
        satir.setObjectName("bilgiSatiri")
        duzen = QHBoxLayout(satir)
        duzen.setContentsMargins(18, 12, 12, 12)
        duzen.setSpacing(12)

        metinler = QVBoxLayout()
        metinler.setSpacing(2)
        konu = QLabel(kayit.get("konu", "?"))
        konu.setObjectName("bilgiKonu")
        bilgi = QLabel(kayit.get("bilgi", ""))
        bilgi.setObjectName("bilgiDeger")
        bilgi.setWordWrap(True)
        bilgi.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        kaynak = "kendiliğinden öğrendim" if kayit.get("kaynak") == "otomatik" else "sen ekledin"
        alt = QLabel(f"{kaynak} · {kayit.get('zaman', '')}")
        alt.setObjectName("bilgiAlt")
        metinler.addWidget(konu)
        metinler.addWidget(bilgi)
        metinler.addWidget(alt)
        duzen.addLayout(metinler, 1)

        sil = QPushButton("Sil")
        sil.setObjectName("silDugme")
        sil.setCursor(Qt.CursorShape.PointingHandCursor)
        sil.clicked.connect(lambda _=False, a=kayit.get("anahtar"): self._bilgi_sil(a))
        duzen.addWidget(sil, 0, Qt.AlignmentFlag.AlignVCenter)
        return satir

    def _hafiza_yenile(self):
        while self.hafiza_liste.count() > 1:
            oge = self.hafiza_liste.takeAt(0)
            w = oge.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        kayitlar = profil.tumu()
        if not kayitlar:
            bos = QLabel("Henüz kayıtlı bir bilgi yok. Sohbet ettikçe seni tanımaya başlarım.")
            bos.setObjectName("ayarAciklama")
            bos.setWordWrap(True)
            self.hafiza_liste.insertWidget(0, bos)
        for kayit in reversed(kayitlar):   # en yeni en üstte
            self.hafiza_liste.insertWidget(self.hafiza_liste.count() - 1, self._bilgi_satiri(kayit))

        sohbet_hafizasi = "model yüklenince görünür"
        if self.ai.hazir:
            try:
                sohbet_hafizasi = f"{self.ai.backend.vektor_veritabani._collection.count()} parça"
            except Exception:
                sohbet_hafizasi = "okunamadı"
        self.hafiza_durum.setText(f"{len(kayitlar)} kalıcı bilgi  ·  Sohbet hafızası: {sohbet_hafizasi}")

    def _bilgi_ekle(self):
        konu = self.hafiza_konu_girisi.text().strip()
        bilgi = self.hafiza_bilgi_girisi.text().strip()
        if not konu or not bilgi:
            self.toast.goster("Konu ve bilgi boş olamaz", hata=True)
            return
        if hassas_mi(f"{konu} {bilgi}"):
            self.toast.goster("Şifre, anahtar gibi hassas bilgiler kaydedilmez", hata=True)
            return
        sonuc = profil.ekle(konu, bilgi, kaynak="kullanici")
        if sonuc in ("gecersiz", "dolu"):
            self.toast.goster("Bilgi kaydedilemedi (çok uzun ya da hafıza dolu)", hata=True)
            return
        self.hafiza_konu_girisi.clear()
        self.hafiza_bilgi_girisi.clear()
        self._hafiza_yenile()
        self.toast.goster({"eklendi": "Kaydedildi", "guncellendi": "Güncellendi", "ayni": "Bunu zaten biliyordum"}[sonuc])

    def _bilgi_sil(self, anahtar: str):
        if profil.sil(anahtar):
            self._hafiza_yenile()
            self.toast.goster("Unuttum")

    def _bildirim_geldi(self, metin: str):
        """Asistanın kendiliğinden verdiği haberler (örn. 'Öğrendim: ...')."""
        self.toast.goster(metin)
        if self.sayfalar.currentIndex() == 2:
            self._hafiza_yenile()
        # Hatırlatmalar sesli de okunur (sesli mod açıksa)
        if (self.ses_hazir and self.ses.cikis_hazir and (self.ayar_ses_cevap or self._eller_serbest)
                and metin.startswith(("Hatırlatma", "(Kaçırıldı)"))):
            self.ses.konus_dogrudan(metin)

    def _ayar_karti(self, baslik: str, aciklama: str, sag: QWidget) -> QFrame:
        kart = QFrame()
        kart.setObjectName("ayarKarti")
        duzen = QHBoxLayout(kart)
        duzen.setContentsMargins(22, 18, 22, 18)
        duzen.setSpacing(20)
        sol = QVBoxLayout()
        sol.setSpacing(4)
        b = QLabel(baslik)
        b.setObjectName("ayarEtiket")
        a = QLabel(aciklama)
        a.setObjectName("ayarAciklama")
        a.setWordWrap(True)
        sol.addWidget(b)
        sol.addWidget(a)
        duzen.addLayout(sol, 1)
        duzen.addWidget(sag, 0, Qt.AlignmentFlag.AlignVCenter)
        return kart

    # ============================================================
    # TEMA VE STİL
    # ============================================================
    def _stili_uygula(self):
        TEMA.clear()
        TEMA.update(TEMALAR[self.ayar_tema])
        uygulama = QApplication.instance()
        uygulama.setStyleSheet(stil_olustur(TEMA, self.ayar_punto))
        palet = uygulama.palette()
        palet.setColor(QPalette.ColorRole.PlaceholderText, QColor(TEMA["soluk"]))
        uygulama.setPalette(palet)
        try:  # Windows başlık çubuğunu temayla uyumlu yapar (Qt 6.8+)
            uygulama.styleHints().setColorScheme(
                Qt.ColorScheme.Dark if self.ayar_tema == "dark" else Qt.ColorScheme.Light)
        except Exception:
            pass
        self.enter_anahtari.update()
        self.ses_cevap_anahtari.update()
        self.kulaklik_anahtari.update()

    def _tema_sec(self, kod: str):
        self.ayar_tema = kod
        self._ayarlari_kaydet()
        self._stili_uygula()

    def _punto_degisti(self, deger: int):
        self.ayar_punto = deger
        self.punto_degeri.setText(f"{deger} px")
        self._stil_z.start()

    def _punto_uygula(self):
        self._stili_uygula()
        self._ayarlari_kaydet()

    def _enter_degisti(self, acik: bool):
        self.enter_gonderir = acik
        self.giris.enter_gonderir = acik
        self._ayarlari_kaydet()

    def _ayarlari_kaydet(self):
        self.ayarlar.toplu_kaydet({
            "font_size": self.ayar_punto,
            "appearance_mode": self.ayar_tema,
            "enter_gonderir": self.enter_gonderir,
            "ses_her_cevap": self.ayar_ses_cevap,
            "ses_kulaklik": self.ayar_kulaklik,
            "ses_ses": self.ayar_ses,
            "ses_mikrofon": self.ayar_mikrofon,
            "ses_seviye": self.ayar_ses_seviye,
        })

    # ============================================================
    # DURUM GÖSTERGELERİ
    # ============================================================
    def _durum(self, kod: str, metin: str):
        self.durum_etiketi.setProperty("durum", kod)
        self.durum_etiketi.setText(metin)
        stil = self.durum_etiketi.style()
        stil.unpolish(self.durum_etiketi)
        stil.polish(self.durum_etiketi)

    def _gonder_dugmesi_guncelle(self):
        self.gonder_dugmesi.setEnabled(self.ai.hazir and not self.dusunuyor)

    def _giris_odagi(self, odakta: bool):
        self.giris_kapsayici.setProperty("odak", "evet" if odakta else "hayir")
        stil = self.giris_kapsayici.style()
        stil.unpolish(self.giris_kapsayici)
        stil.polish(self.giris_kapsayici)

    def _ai_hazir(self):
        self._durum("hazir", "Hazır")
        self._gonder_dugmesi_guncelle()
        self.toast.goster("Model hazır")

    def _ai_yukleme_hatasi(self, mesaj: str):
        self._durum("hata", "Yükleme hatası")
        self.durum_etiketi.setToolTip(mesaj)
        self.hosgeldin.alt_metin_ayarla(f"Yapay zeka yüklenemedi: {mesaj[:200]}")
        self.toast.goster(f"Hata: {mesaj[:90]}", hata=True)

    # ============================================================
    # ONAY PENCERESİ (yapay zeka riskli işlem yapmadan önce sorar)
    # ============================================================
    def _onay_sor(self, aciklama: str) -> bool:
        """Arka plan thread'inden çağrılır; kullanıcı cevap verene kadar bekler."""
        sonuc = {"cevap": False}
        bitti = threading.Event()
        self.sig_onay.emit(aciklama, (sonuc, bitti))
        bitti.wait()
        return sonuc["cevap"]

    def _onay_goster(self, aciklama: str, ek):
        sonuc, bitti = ek
        try:
            if self.isMinimized():      # ekran ajanı pencereyi küçültmüş olabilir: onay kutusu görünsün
                self.showNormal()
            self.activateWindow()
            self.raise_()
            self._ses_dolgu("onay")
            sonuc["cevap"] = self._soru_kutusu("Onay gerekiyor", "MFY AI bir işlem yapmak istiyor.",
                                               aciklama[:1500], "Onayla", "Reddet")
        except Exception:
            sonuc["cevap"] = False
        finally:
            bitti.set()

    def _soru_kutusu(self, baslik, ana_metin, detay="", evet="Evet", hayir="Vazgeç") -> bool:
        kutu = QMessageBox(self)
        kutu.setWindowTitle(baslik)
        kutu.setIcon(QMessageBox.Icon.Warning)
        kutu.setText(ana_metin)
        if detay:
            kutu.setInformativeText(detay)
        dugme_evet = kutu.addButton(evet, QMessageBox.ButtonRole.AcceptRole)
        dugme_hayir = kutu.addButton(hayir, QMessageBox.ButtonRole.RejectRole)
        kutu.setDefaultButton(dugme_hayir)
        kutu.exec()
        return kutu.clickedButton() is dugme_evet

    # ============================================================
    # SAYFA VE SOHBET GEÇMİŞİ
    # ============================================================
    def _sayfa_goster(self, indeks: int):
        self.sayfalar.setCurrentIndex(indeks)
        self.ayar_dugmesi.setChecked(indeks == 1)
        self.hafiza_dugmesi.setChecked(indeks == 2)

    def _ayar_dugmesi_tiklandi(self):
        self._sayfa_goster(0 if self.sayfalar.currentIndex() == 1 else 1)

    def _hafiza_dugmesi_tiklandi(self):
        if self.sayfalar.currentIndex() == 2:
            self._sayfa_goster(0)
        else:
            self._hafiza_yenile()
            self._sayfa_goster(2)

    def _gecmis_yenile(self):
        self.gecmis.blockSignals(True)
        self.gecmis.clear()
        secili_satir = -1
        for i, (sid, baslik) in enumerate(self.oturumlar.liste()):
            oge = QListWidgetItem(baslik)
            oge.setData(Qt.ItemDataRole.UserRole, sid)
            oge.setToolTip(baslik)
            self.gecmis.addItem(oge)
            if sid == self.aktif_oturum:
                secili_satir = i
        self.gecmis.setCurrentRow(secili_satir)
        self.gecmis.blockSignals(False)

    def _gecmis_tiklandi(self, oge: QListWidgetItem):
        sid = oge.data(Qt.ItemDataRole.UserRole)
        if sid == self.aktif_oturum and self.sayfalar.currentIndex() == 0:
            return
        self._oturum_yukle(sid)

    def _gecmis_menusu(self, pozisyon):
        oge = self.gecmis.itemAt(pozisyon)
        if oge is None:
            return
        sid = oge.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        eylem_ad = menu.addAction("Yeniden adlandır")
        eylem_sil = menu.addAction("Sil")
        secim = menu.exec(self.gecmis.viewport().mapToGlobal(pozisyon))
        if secim is eylem_ad:
            yeni, tamam = QInputDialog.getText(self, "Yeniden adlandır", "Yeni başlık:",
                                               text=self.oturumlar.baslik_al(sid))
            if tamam and yeni.strip():
                self.oturumlar.yeniden_adlandir(sid, yeni.strip())
                self._gecmis_yenile()
                if sid == self.aktif_oturum:
                    self.baslik_etiketi.setText(yeni.strip())
        elif secim is eylem_sil:
            if self.dusunuyor and sid == self._akis_oturum:
                self.toast.goster("Cevap verilirken bu sohbet silinemez", hata=True)
                return
            if self._soru_kutusu("Sohbeti sil", "Bu sohbet kalıcı olarak silinecek.",
                                 self.oturumlar.baslik_al(sid), "Sil", "Vazgeç"):
                self.oturumlar.sil(sid)
                if sid == self.aktif_oturum:
                    self._yeni_sohbet()
                self._gecmis_yenile()

    def _yeni_sohbet(self):
        self.aktif_oturum = None
        self._mesajlari_temizle()
        self.icerik_yigini.setCurrentIndex(0)
        self.baslik_etiketi.setText("Yeni sohbet")
        self._sayfa_goster(0)
        self.gecmis.blockSignals(True)
        self.gecmis.setCurrentRow(-1)
        self.gecmis.blockSignals(False)
        self.giris.setFocus()

    def _oturum_yukle(self, sid: str):
        self.aktif_oturum = sid
        self._sayfa_goster(0)
        self._mesajlari_temizle()
        self.icerik_yigini.setCurrentIndex(1)
        self._alta_yapis = True

        govde = self.kaydirma.widget()
        govde.setUpdatesEnabled(False)
        for m in self.oturumlar.mesajlar(sid)[-EKRANDA_MAKS_MESAJ:]:
            self._mesaj_ekle(m.get("text", ""), bool(m.get("is_ai")))
        # Bu sohbet için cevap hâlâ yazılıyorsa canlı balonu yeniden oluştur
        if self.dusunuyor and self._akis_oturum == sid:
            gorunen = dusunceyi_temizle(self._akis_metin) or "_Düşünüyor…_"
            self._akis_satiri = self._mesaj_ekle(gorunen, True, akiyor=True)
        govde.setUpdatesEnabled(True)

        self.baslik_etiketi.setText(self.oturumlar.baslik_al(sid))
        self.gecmis.blockSignals(True)
        for i in range(self.gecmis.count()):
            if self.gecmis.item(i).data(Qt.ItemDataRole.UserRole) == sid:
                self.gecmis.setCurrentRow(i)
                break
        self.gecmis.blockSignals(False)
        self.giris.setFocus()

    # ============================================================
    # MESAJ ALANI
    # ============================================================
    def _mesaj_ekle(self, metin: str, ai_mi: bool, akiyor: bool = False) -> MesajSatiri:
        satir = MesajSatiri(metin, ai_mi, akiyor)
        self.mesaj_duzeni.insertWidget(self.mesaj_duzeni.count() - 1, satir)
        return satir

    def _mesajlari_temizle(self):
        self._akis_satiri = None
        while self.mesaj_duzeni.count() > 1:
            oge = self.mesaj_duzeni.takeAt(0)
            w = oge.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _aralik_degisti(self, minimum, maksimum):
        if self._alta_yapis:
            self.kaydirma.verticalScrollBar().setValue(maksimum)

    def _kayma_degisti(self, deger):
        sb = self.kaydirma.verticalScrollBar()
        self._alta_yapis = (sb.maximum() - deger) < 48

    # ============================================================
    # MESAJ GÖNDERME VE CANLI AKIŞ
    # ============================================================
    def _gonder(self, hazir_metin=None, sesli: bool = False):
        if not self.ai.hazir:
            self.toast.goster("Yapay zeka henüz yüklenmedi, lütfen bekle…", hata=True)
            return
        if self.dusunuyor:
            self.toast.goster("Asistan hâlâ cevap veriyor, lütfen bekle…", hata=True)
            return

        metin = hazir_metin if isinstance(hazir_metin, str) else self.giris.toPlainText()
        mesaj = metin.strip()
        if not mesaj:
            return

        self._sayfa_goster(0)
        if self.aktif_oturum is None:
            self.aktif_oturum = self.oturumlar.yeni_oturum(mesaj)
            self.baslik_etiketi.setText(self.oturumlar.baslik_al(self.aktif_oturum))
            self._gecmis_yenile()
        self.icerik_yigini.setCurrentIndex(1)
        sid = self.aktif_oturum

        if not sesli and hazir_metin is None:
            self.giris.clear()       # yazılı taslak, sesli mesajla silinmesin
        self._alta_yapis = True
        self._mesaj_ekle(mesaj, ai_mi=False)
        self.oturumlar.mesaj_ekle(sid, "Sen", mesaj, False)
        gecmis = self.oturumlar.mesajlar(sid)[:-1]   # şimdi yazılan mesaj hariç

        # Canlı cevap balonu
        self._akis_oturum = sid
        self._akis_metin = ""
        self._token_tamponu.clear()
        self._nokta = 0
        self._akis_satiri = self._mesaj_ekle("_Düşünüyor._", True, akiyor=True)

        self.dusunuyor = True
        self._durum("dusunuyor", "Düşünüyor…")
        self._gonder_dugmesi_guncelle()
        self._flush.start()
        self._nokta_z.start()

        # Sesli cevap: mikrofonla geldiyse ya da "her cevabı sesli oku" açıksa
        self._son_sesli = sesli
        sesli_cevap = bool(self.ses_hazir and self.ses.cikis_hazir and (sesli or self.ayar_ses_cevap))
        if self.ses_hazir:
            self.ses.yanit_basladi(eylem=arac_secici.eylem_mesaji_mi(mesaj), sesli_cevap=sesli_cevap)

        self.ai.sor(
            mesaj, gecmis,
            on_token=self.sig_token.emit,
            on_cevap=lambda yanit: self.sig_cevap.emit(yanit, sid),
            on_hata=lambda hata: self.sig_hata.emit(hata, sid),
            ses_modu=sesli_cevap,
        )

    def _token_geldi(self, token: str):
        self._token_tamponu.append(token)
        if self.ses_hazir:
            self.ses.token_ver(token)

    def _akis_isle(self):
        """Biriken token'ları tek seferde ekrana basar (saniyede ~30 güncelleme)."""
        if not self._token_tamponu:
            return
        self._akis_metin += "".join(self._token_tamponu)
        self._token_tamponu.clear()
        if self._akis_satiri is not None:
            gorunen = dusunceyi_temizle(self._akis_metin)
            if gorunen:
                self._akis_satiri.metni_ayarla(gorunen)

    def _nokta_isle(self):
        """İlk token gelene kadar 'Düşünüyor...' animasyonu."""
        if self._akis_satiri is None or dusunceyi_temizle(self._akis_metin):
            return
        self._nokta = (self._nokta + 1) % 3
        self._akis_satiri.metni_ayarla("_Düşünüyor" + "." * (self._nokta + 1) + "_")

    def _akisi_bitir(self):
        self._flush.stop()
        self._nokta_z.stop()
        self._token_tamponu.clear()
        self.dusunuyor = False
        self._akis_oturum = None
        self._akis_metin = ""
        self._bosta_durumunu_goster()
        self._gonder_dugmesi_guncelle()

    def _cevap_geldi(self, yanit: str, sid: str):
        if self.ses_hazir:
            self.ses.yanit_bitti(dusunceyi_temizle(yanit))
        yanit = dusunceyi_temizle(yanit) or "(Boş cevap)"
        satir = self._akis_satiri
        self._akis_satiri = None
        self._akisi_bitir()

        self.oturumlar.mesaj_ekle(sid, "MFY AI", yanit, True)
        if self.aktif_oturum == sid:
            if satir is not None:
                try:
                    satir.metni_ayarla(yanit)
                    satir.tamamla()
                    return
                except RuntimeError:
                    pass  # balon bu arada silinmiş
            self._mesaj_ekle(yanit, True)

    def _hata_geldi(self, hata: str, sid: str):
        if self.ses_hazir:
            self.ses.yanit_iptal()
        satir = self._akis_satiri
        self._akis_satiri = None
        self._akisi_bitir()
        metin = f"**Hata:** {hata}"
        if self.aktif_oturum == sid:
            if satir is not None:
                try:
                    satir.metni_ayarla(metin)
                    satir.tamamla()
                except RuntimeError:
                    self._mesaj_ekle(metin, True)
            else:
                self._mesaj_ekle(metin, True)
        self.toast.goster("Bir hata oluştu", hata=True)

    # ============================================================
    # SESLİ KONUŞMA
    # ============================================================
    def _ses_hazirla(self, sonra=None):
        """Ses sistemini (konuşma tanıma + konuşma sesi) ilk kullanımda arka planda yükler."""
        if sonra is not None:
            self._ses_bekleyen.append(sonra)
        if self.ses_hazir:
            self._ses_bekleyenleri_calistir()
            return
        if self.ses_yukleniyor:
            return
        self.ses_yukleniyor = True
        self.toast.goster("Ses sistemi hazırlanıyor… (ilk seferde biraz sürebilir)")
        self.ses = SesYoneticisi(ses=self.ayar_ses, seviye=self.ayar_ses_seviye / 100.0,
                                 mikrofon=self.ayar_mikrofon, kulaklik=self.ayar_kulaklik)
        self.ses.on_durum = self.sig_ses_durum.emit
        self.ses.on_metin = self.sig_ses_metin.emit
        self.ses.on_bilgi = self.sig_ses_bilgi.emit
        self.ses.on_hata = self.sig_ses_hata.emit
        self.ses.on_hazir = self.sig_ses_hazir.emit
        self.ses.on_eller_serbest = self.sig_ses_eller_serbest.emit
        self.ses.yukle()

    def _ses_hazir_oldu(self):
        self.ses_hazir = True
        self.ses_yukleniyor = False
        if self.ses.giris_hazir and self.ses.cikis_hazir:
            self.toast.goster("Ses sistemi hazır. Mikrofon düğmesine ya da F9'a bas.")
        self._ses_bekleyenleri_calistir()

    def _ses_bekleyenleri_calistir(self):
        isler, self._ses_bekleyen = self._ses_bekleyen, []
        for is_ in isler:
            try:
                is_()
            except Exception as e:
                print(f"Ses işi çalıştırılamadı: {e}")

    def _ses_hata_geldi(self, metin: str):
        self.ses_yukleniyor = False
        print(f"🎙️ Ses hatası: {metin}")
        self.toast.goster(metin[:150], hata=True)

    def _ses_bilgi_geldi(self, metin: str):
        self.toast.goster(metin)

    def _ses_eller_serbest_degisti(self, acik: bool):
        self._eller_serbest = acik
        self.eller_serbest_dugmesi.setChecked(acik)
        if not acik:
            self.uyandirma_dugmesi.setChecked(False)
        if not acik:
            self.toast.goster("Eller serbest kapandı", hata=True)

    def _mikrofon_gorunumu(self, aktif: bool):
        self.mikrofon_dugmesi.setProperty("aktif", "evet" if aktif else "hayir")
        stil = self.mikrofon_dugmesi.style()
        stil.unpolish(self.mikrofon_dugmesi)
        stil.polish(self.mikrofon_dugmesi)

    def _bosta_durumunu_goster(self):
        """Yapay zeka işi bitince durum rozetini sesli durumla uyumlu göster."""
        if self.ses_hazir and self.ses.konusuyor:
            self._durum("konusuyor", "Konuşuyor…")
        elif self.ses_hazir and self._eller_serbest and self.ses.dinliyor_mu():
            self._durum("dinliyor", "Dinliyor…")
        else:
            self._durum("hazir", "Hazır")

    def _ses_durum_geldi(self, kod: str, metin: str):
        self._mikrofon_gorunumu(kod == "dinliyor")
        self.sustur_dugmesi.setVisible(kod == "konusuyor")
        if self.dusunuyor and kod in ("hazir", "dinliyor"):
            self._durum("dusunuyor", "Düşünüyor…")
        elif kod in ("dinliyor", "cozumluyor", "konusuyor"):
            self._durum(kod, metin)
        elif kod == "hazir" and self.ai.hazir:
            self._durum("hazir", "Hazır")

    def _mikrofon_tikla(self):
        """Mikrofon düğmesi / F9: bir cümle dinler. Dinliyorsa iptal eder, konuşuyorsa susturur."""
        if not self.ai.hazir:
            self.toast.goster("Yapay zeka henüz yüklenmedi, lütfen bekle…", hata=True)
            return
        if not self.ses_hazir:
            self._ses_hazirla(sonra=self._mikrofon_tikla)
            return
        if not self.ses.giris_hazir:
            self.toast.goster("Konuşma tanıma yüklenemedi. Ayrıntı için terminale bak.", hata=True)
            return
        if self._eller_serbest:
            self.ses.sustur()                 # eller serbest açıkken düğme: konuşan asistanı sustur
            return
        if self.ses.dinliyor_mu():
            self.ses.dinlemeyi_iptal()
            return
        if self.ses.konusuyor:
            self.ses.sustur()
        if self.dusunuyor:
            self.toast.goster("Asistan hâlâ cevap veriyor, bitince konuşabilirsin.", hata=True)
            return
        self.ses.dinle()

    def _uyandirma_tikla(self):
        """'Hey MFY' modu: sürekli dinler, yalnızca seslenince komut alır."""
        if not self.uyandirma_dugmesi.isChecked():
            if self.ses is not None:
                self.ses.uyandirma_ayarla(False)
            self._eller_serbest = False
            self.toast.goster("“Hey MFY” kapalı")
            return
        if not self.ai.hazir:
            self.uyandirma_dugmesi.setChecked(False)
            self.toast.goster("Yapay zeka henüz yüklenmedi, lütfen bekle…", hata=True)
            return
        self.eller_serbest_dugmesi.setChecked(False)      # iki sürekli mod birlikte açık olmaz
        if not self.ses_hazir:
            self._ses_hazirla(sonra=self._uyandirma_baslat)
            return
        self._uyandirma_baslat()

    def _uyandirma_baslat(self):
        if not self.uyandirma_dugmesi.isChecked():
            return                                        # yükleme sırasında kullanıcı vazgeçti
        if self.ses is None or not self.ses.giris_hazir:
            self.uyandirma_dugmesi.setChecked(False)
            self.toast.goster("Konuşma tanıma yüklenemedi. Ayrıntı için terminale bak.", hata=True)
            return
        if self.ses.uyandirma_ayarla(True):
            self._eller_serbest = True                    # sürekli dinleme açık (susturma, hatırlatma okuma vb. için)
            ek = "" if self.ayar_kulaklik else " (hoparlör kullanıyorsan kulaklık önerilir)"
            self.toast.goster("“Hey MFY” dinleniyor: seslenince dinlemeye başlarım" + ek)
        else:
            self.uyandirma_dugmesi.setChecked(False)

    def _eller_serbest_tikla(self):
        if not self.eller_serbest_dugmesi.isChecked():
            if self.ses is not None:
                self.ses.eller_serbest_ayarla(False)
            self._eller_serbest = False
            self.toast.goster("Eller serbest kapalı")
            return
        if not self.ai.hazir:
            self.eller_serbest_dugmesi.setChecked(False)
            self.toast.goster("Yapay zeka henüz yüklenmedi, lütfen bekle…", hata=True)
            return
        if not self.ses_hazir:
            self._ses_hazirla(sonra=self._eller_serbest_baslat)
            return
        self._eller_serbest_baslat()

    def _eller_serbest_baslat(self):
        if not self.eller_serbest_dugmesi.isChecked():
            return                              # yükleme sırasında kullanıcı vazgeçti
        if self.ses is None or not self.ses.giris_hazir:
            self.eller_serbest_dugmesi.setChecked(False)
            self.toast.goster("Konuşma tanıma yüklenemedi. Ayrıntı için terminale bak.", hata=True)
            return
        if self.ses.eller_serbest_ayarla(True):
            self.uyandirma_dugmesi.setChecked(False)
            self._eller_serbest = True
            ek = "" if self.ayar_kulaklik else " (hoparlör kullanıyorsan kulaklık önerilir)"
            self.toast.goster("Eller serbest açık: seni dinliyorum" + ek)
        else:
            self.eller_serbest_dugmesi.setChecked(False)

    def _sustur(self):
        """Esc / ■ düğmesi: konuşan asistanı susturur; tek seferlik dinlemeyi iptal eder."""
        if self.ses is None or not self.ses_hazir:
            return
        if self.ses.konusuyor:
            self.ses.sustur()
        elif self.ses.dinliyor_mu() and not self._eller_serbest:
            self.ses.dinlemeyi_iptal()

    def _ses_metin_geldi(self, metin: str):
        """Mikrofonla söylenip yazıya çevrilen cümle: normal mesaj gibi gönderilir."""
        self._gonder(metin, sesli=True)

    def _ses_dolgu(self, kategori: str):
        if self.ses_hazir and self.ses.cikis_hazir and (self._son_sesli or self.ayar_ses_cevap or self._eller_serbest):
            self.ses.dolgu_cal(kategori)

    # --- ses ayarları ---
    def _mikrofonlari_doldur(self):
        self.mikrofon_combo.blockSignals(True)
        self.mikrofon_combo.clear()
        self.mikrofon_combo.addItem("Varsayılan mikrofon", "")
        try:
            import sounddevice as sd
            gorulen = set()
            for cihaz in sd.query_devices():
                ad = cihaz.get("name", "")
                if cihaz.get("max_input_channels", 0) > 0 and ad and ad not in gorulen:
                    gorulen.add(ad)
                    self.mikrofon_combo.addItem(ad, ad)
        except Exception:
            pass
        indeks = self.mikrofon_combo.findData(self.ayar_mikrofon)
        self.mikrofon_combo.setCurrentIndex(indeks if indeks >= 0 else 0)
        self.mikrofon_combo.blockSignals(False)

    def _ses_cevap_degisti(self, acik: bool):
        self.ayar_ses_cevap = acik
        self._ayarlari_kaydet()
        if acik and not self.ses_hazir:
            self._ses_hazirla()

    def _kulaklik_degisti(self, acik: bool):
        self.ayar_kulaklik = acik
        self._ayarlari_kaydet()
        if self.ses is not None:
            self.ses.ayarla(kulaklik=acik)

    def _ses_secildi(self, indeks: int):
        self.ayar_ses = self.ses_combo.itemData(indeks) or "female_2"
        self._ayarlari_kaydet()
        if self.ses is not None:
            self.ses.ayarla(ses=self.ayar_ses)

    def _ses_dene(self):
        self._ses_hazirla(sonra=lambda: self.ses.ornek_cal(
            "Merhaba! Ben MFY AI. Bugün sana nasıl yardımcı olabilirim?"))

    def _mikrofon_secildi(self, indeks: int):
        self.ayar_mikrofon = self.mikrofon_combo.itemData(indeks) or ""
        self._ayarlari_kaydet()
        if self.ses is not None:
            self.ses.ayarla(mikrofon=self.ayar_mikrofon)

    def _ses_seviye_degisti(self, deger: int):
        self.ayar_ses_seviye = deger
        self.ses_seviye_degeri.setText(f"%{deger}")
        if self.ses is not None:
            self.ses.ayarla(seviye=deger / 100.0)
        self._ayar_kaydet_z.start()

    def closeEvent(self, olay):
        self._flush.stop()
        self._nokta_z.stop()
        if self.ses is not None:
            self.ses.kapat()
        super().closeEvent(olay)


def main():
    uygulama = QApplication(sys.argv)
    uygulama.setStyle("Fusion")
    uygulama.setApplicationName("MFY AI")
    uygulama.setFont(QFont("Segoe UI", 10))
    pencere = AnaPencere()
    pencere.show()
    sys.exit(uygulama.exec())


if __name__ == "__main__":
    main()
