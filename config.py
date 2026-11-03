
import os
from dotenv import load_dotenv

load_dotenv()

# API ANAHTARLARI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# MODEL SAĞLAYICI
SAGLAYICI = os.getenv("MFY_SAGLAYICI", "groq").lower()

# LM STUDIO
LMSTUDIO_URL = "http://127.0.0.1:1234/v1"
LMSTUDIO_MODEL = "local-model"

# OPENAI
OPENAI_MODEL = "gpt-4o-mini"

# ANTHROPIC
ANTHROPIC_MODEL = "claude-sonnet-5-5"

# GEMINI
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# GROQ
GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# MODEL AYARLARI
SICAKLIK = 0.3

# ------------------------------------------------------------
# YOLLAR
# ------------------------------------------------------------
PROJE_DIZINI = os.path.dirname(os.path.abspath(__file__))
CHROMA_YOLU = os.path.join(PROJE_DIZINI, "mfy_chroma_db")

# Üretilen dosyalar için varsayılan klasör; izinler.py ayrıca yol politikasını uygular.
CALISMA_ALANI = os.path.join(PROJE_DIZINI, "calisma_alani")
os.makedirs(CALISMA_ALANI, exist_ok=True)

# ------------------------------------------------------------
# HAFIZA
# ------------------------------------------------------------
KISA_HAFIZA_MESAJ = 10        # Aynı sohbetten modele verilecek son mesaj sayısı
RAG_KOSINUS_ESIGI = 0.35     # 0-1 arası kosinüs benzerliği; altındaki hafıza parçaları alınmaz
RAG_K = 8                     # Uzun süreli hafızadan getirilecek parça sayısı
RAG_CHUNK_SIZE = 500
RAG_CHUNK_OVERLAP = 50
RAG_MAKS_KARAKTER = 1800      # Modele verilecek hafıza metninin üst sınırı
OTOMATIK_PROFIL = True        # Sohbetten kendiliğinden kullanıcı bilgisi öğren

# ------------------------------------------------------------
# GÜVENLİK
# ------------------------------------------------------------
KOD_CALISTIRMA_ONAYI = False   # Python kodu çalıştırmadan önce sor
DOSYA_YAZMA_ONAYI = False      # Dosya oluşturmadan önce sor

# Güven Modu: siki | dengeli | rahat | sinirsiz
GUVEN_MODU = "dengeli"

SES_TTS_SES = "male_1"  # varsayılan ses
SES_TTS_CIHAZ = "cpu"  # ses üretimi (8 GB ekran kartını sohbet modeline bırakmak için cpu)
SES_STT_MODEL = "large-v3-turbo"  # yavaş gelirse "small" dene
SES_STT_CIHAZ = "cpu"
SES_SESSIZLIK_MS = 700  # cümle ortasında kesiliyorsan 900 yap
SES_TTS_HIZ = 1.0

SES_STT_HESAP = "int8"      # cpu için "int8" (GPU kullanımında otomatik int8_float16)
SES_UYANDIRMA_ESIK = 0.67   # "Hey MFY" benzerlik eşiği (tetiklenmiyorsa 0.6 dene)

# ------------------------------------------------------------
# EKRAN GÖRME / PC AJANI
# ------------------------------------------------------------
# Ekran analizi için görüntü destekli bir model gerekir. Boş bırakırsan sohbet modeliyle (SAGLAYICI) aynı kullanılır.
# Yerel modelin görüntü desteklemiyorsa: VIZYON_SAGLAYICI = "openai" ya da "anthropic" yap (API anahtarı gerekir).
VIZYON_SAGLAYICI = os.getenv("MFY_VIZYON_SAGLAYICI", "")   # "" | "lmstudio" | "openai" | "anthropic"
VIZYON_MODEL = ""             # boş = sağlayıcının varsayılan modeli
VIZYON_MAKS_KENAR = 1568      # görüntünün uzun kenarı (px). Yerel model yavaşsa 1024 dene
VIZYON_DOGRULA = True         # bulunan konumu yakından kırpıp tekrar kontrol eder (daha doğru, 1 model çağrısı fazla)
VIZYON_IZGARA = False         # zayıf modellerde koordinat doğruluğu için görüntüye ızgara çizer
AJAN_MAKS_ADIM = 30           # ekran/fare görevlerinde modelin en fazla kaç araç çağrısı yapabileceği
AJAN_MAKS_EYLEM = 60          # bir istekte en fazla fare eylemi sayısı
VIZYON_DEBUG = False         # True: öğe bulma cevaplarını yazdırır, tahmini işaretli görüntüyü calisma_alani/ekran_debug/ içine kaydeder
