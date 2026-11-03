# MFY AI

MFY AI, Windows için geliştirilen Türkçe kişisel masaüstü asistanıdır. Yazılı ve sesli sohbeti, kalıcı hafızayı ve bilgisayar üzerinde işlem yapan araçları aynı arayüzde birleştirir.

Proje aktif geliştirme aşamasındadır. Kurulumun referans ortamı Windows ve Python 3.12'dir; diğer işletim sistemleri desteklenmez. Temiz bir bilgisayarda uçtan uca kurulum henüz doğrulanmamıştır.

## Özellikler

- PySide6 masaüstü arayüzü, sohbet oturumları, tema ve yazı boyutu ayarları.
- Groq, OpenAI, Gemini, Anthropic ve LM Studio sağlayıcıları için model fabrikası.
- Chroma ve Sentence Transformers ile geçmiş konuşmalardan ilgili bağlamı getirme.
- Kullanıcı profilini elle yönetme ve konuşmalardan otomatik bilgi öğrenme.
- Dosya, uygulama, sistem, pencere, medya, web ve hatırlatıcı araçları.
- Ekran görüntüsü üzerinden analiz, fare/klavye kontrolü ve Windows UI Automation.
- İsteğe bağlı Türkçe konuşma tanıma, sesli cevap, “Hey MFY” ve eller serbest kullanım.
- Araç seçimi, işlem günlüğü ve yapılandırılabilir onay katmanı.

## Kurulum

Python 3.12, Git ve Windows PowerShell gerekir. Bulut sağlayıcıları için ilgili API anahtarı; yerel sohbet için araç çağrısını destekleyen bir modelle çalışan LM Studio sunucusu gerekir.

Repoyu klonlayıp proje klasörüne geçtikten sonra PowerShell'de:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Son komutu yalnızca `.env` dosyanız yoksa çalıştırın. `.env` içinde sağlayıcınızı ve ona ait anahtarı ayarlayın. Gerçek anahtarları kaynak koda yazmayın.

```dotenv
MFY_SAGLAYICI=groq
GROQ_API_KEY=YOUR_API_KEY_HERE
```

Paket sürümleri mevcut geliştirme ortamından alınmıştır. `requirements.txt` doğrudan bağımlılıkları içerir; tüm dolaylı bağımlılıkları sabitleyen bir kilit dosyası değildir. Projeyle ilgisiz geliştirme araçlarını aynı sanal ortama kurmayın.

### Hafıza modelini ilk kez indirme

Uygulama, gömme modelinin önceden indirilmiş olduğunu varsayıp Hugging Face çevrimdışı modunu açar. İlk çalıştırmadan önce internet bağlantısıyla şu komutu çalıştırın:

```powershell
.\.venv\Scripts\python.exe -c "import os; os.environ.pop('HF_HUB_OFFLINE', None); from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
```

### Çalıştırma

```powershell
.\.venv\Scripts\python.exe arayuz.py
```

Terminal arayüzü için:

```powershell
.\.venv\Scripts\python.exe beyin.py
```

Terminal sohbetinden çıkmak için `kapat` yazın.

## Model yapılandırması

| Sağlayıcı | `MFY_SAGLAYICI` | Gereken ayar |
| --- | --- | --- |
| Groq | `groq` | `GROQ_API_KEY` |
| OpenAI | `openai` | `OPENAI_API_KEY` |
| Gemini | `gemini` | `GEMINI_API_KEY` |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` ve `langchain-anthropic` paketi |
| LM Studio | `lmstudio` | `config.py` içindeki `LMSTUDIO_URL` ve `LMSTUDIO_MODEL` |

Model kimlikleri, sıcaklık, hafıza sınırları ve ekran ajanı ayarları `config.py` içindedir. Model adlarının hesabınızda/sunucunuzda kullanılabilir olduğunu kontrol edin; kaynak koddaki adlar kullanılabilirlik garantisi değildir. Anthropic desteği temel bağımlılık listesine dahil değildir:

```powershell
.\.venv\Scripts\python.exe -m pip install langchain-anthropic
```

Ekran analizi için görüntü girdisini destekleyen model gerekir. `.env` içindeki `MFY_VIZYON_SAGLAYICI` ile ayrı sağlayıcı, `config.py` içindeki `VIZYON_MODEL` ile ayrı model seçilebilir. Boş bırakılırsa sohbet sağlayıcısı kullanılır.

## Sesli kullanım

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-voice.txt
.\.venv\Scripts\python.exe ses_kurulum.py
```

Kurulum betiğini arayüz kapalıyken çalıştırın. Betik model indirir, hoparlörden ses çalar ve isteğe bağlı mikrofon testi yapar. Model indirmeleri disk alanı ve internet bağlantısı gerektirir.

Konuşma tanıma faster-whisper, konuşma algılama Silero VAD (yoksa enerji tabanlı yedek), ses üretimi Pocket TTS Turkish kullanır. Cihaz, model ve ses seçenekleri `config.py` ve arayüz ayarları üzerinden yönetilir. Varsayılan işlem cihazı CPU'dur.

## İzinler ve veriler

**Varsayılan yapılandırma `GUVEN_MODU = "dengeli"` kullanır.** PowerShell ve Python araçları bilgisayarda gerçek işlemler yapabilir. `config.py` içindeki güven modu onay davranışını belirler; `sinirsiz` modu onay ve yol kısıtlarının çoğunu atlar. Bu katman işletim sistemi düzeyinde bir sandbox değildir.

| Mod | Onay davranışı |
| --- | --- |
| `siki` | Seviye 1, 2 ve 3 işlemlerde onay |
| `dengeli` | Seviye 2 ve 3 işlemlerde onay |
| `rahat` | Seviye 3 işlemlerde onay |
| `sinirsiz` | İzin katmanında onay yok; yol korumaları devre dışı |

Ekran/fare işlemlerinde sol üst köşe acil durdurma kontrolü bulunur. Bu kontrol tüm komut ve dosya işlemleri için genel bir iptal mekanizması değildir.

Yerel veriler:

| Konum | İçerik |
| --- | --- |
| `.env` | API anahtarları ve sağlayıcı seçimi |
| `chat_sessions.json` | Sohbet geçmişi |
| `profil.json` | Öğrenilen kullanıcı bilgileri |
| `ai_settings.json` | Arayüz ve ses tercihleri |
| `hatirlaticilar.json` | Hatırlatıcı kayıtları |
| `audit_log.jsonl` | Araç argümanları ve sonuç özetleri |
| `mfy_chroma_db/` | Kalıcı anlamsal hafıza |
| `calisma_alani/` | Üretilen dosyalar ve ekran hata ayıklama çıktıları |

Bu dosyalar kişisel veri içerebilir ve yeni Git eklemelerinden dışlanır. Önceden takip edilen dosyalar ve eski commit'ler `.gitignore` eklenince temizlenmez. Açık repo yayımlamadan önce geçmiş de kontrol edilmelidir.

Bulut sağlayıcısı kullanıldığında mesaj, ilgili hafıza ve araç sonuçları modele gönderilebilir. Bulut görüntü modeli kullanıldığında ekran görüntüsü de gönderilir. Yerel kayıt tutulması tüm işlemlerin çevrimdışı olduğu anlamına gelmez.

## Proje yapısı

```text
arayuz.py             PySide6 arayüzü ve Qt sinyalleri
ai_servisi.py         Arka planda AI yükleme ve cevap akışı
beyin.py              Ajan, prompt, RAG ve profil öğrenme
llm_factory.py        Sağlayıcı/model oluşturma
arac_secici.py        Mesaja göre araç gruplarını seçme
araclar/             Konulara ayrılmış Windows ve web araçları
izinler.py            Onay, yol politikası ve işlem günlüğü
hafiza.py             Kullanıcı profili ve hafıza filtreleri
depolama.py           Sohbet ve ayarların JSON depolaması
ses_giris.py          Mikrofon, VAD ve konuşma tanıma
ses_cikis.py          Ses üretimi ve oynatma kuyruğu
ses_yoneticisi.py     Sesli etkileşim koordinasyonu
konusma_stili.py      Sesli cevap metni ve cümle işleme
config.py             Uygulama yapılandırması
```

Yeni araç için ilgili `araclar/` modülüne `@tool` fonksiyonu ekleyin, modülün `ARACLAR` listesine dahil edin ve `arac_secici.py` içindeki uygun gruba kaydedin. Yeni bir modül, `ARACLAR` listesi tanımladığında otomatik keşfedilir.

## Kontroller ve bilinen sınırlar

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m araclar
```

İkinci komut araçları yükleyip envanter ve yükleme hatalarını gösterir; araç eylemlerini çalıştırmaz. Tam uygulama doğrulaması yerine geçmez.

- `arac_testi.py` ve `ekran_testi.py` elle çalıştırılan tanılama betikleridir; uygulama açabilir, model isteği yapabilir veya imleci hareket ettirebilir. İzole bir otomatik test paketi değildir.
- Araç seçimi anahtar kelimelere dayanır ve aynı istekte en fazla 30 araç sunar.
- `beyin.py` içe aktarılırken model, hafıza ve hatırlatıcılar başlatılır.
- Servis katmanındaki ortak durum eşzamanlı bağımsız istekler için tasarlanmamıştır; masaüstü arayüzü tek aktif cevapla çalışır.

## Lisans

Henüz bir açık kaynak lisansı seçilmemiştir. Public repo görünürlüğü, tek başına kullanım ve yeniden dağıtım için açık kaynak lisansı sağlamaz. Bağımlılıkların ve indirilen modellerin kendi lisansları ayrıca geçerlidir.
