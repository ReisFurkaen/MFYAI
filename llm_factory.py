"""
MFY AI - Model Fabrikası
config.SAGLAYICI değerine göre doğru modeli üretir.
Yeni bir sağlayıcı eklemek istersen buraya bir elif eklemen yeterli.

llm_olustur()                       -> sohbet/ajan modeli (config.SAGLAYICI)
llm_olustur("openai", "gpt-4o")     -> belirli sağlayıcı/model (ekran analizi için ayrı model kullanılabilir)
"""
import os
import config


def llm_olustur(saglayici=None, model=None):
    saglayici = (saglayici or config.SAGLAYICI).lower()

    if saglayici == "lmstudio":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            base_url=config.LMSTUDIO_URL,
            api_key="lm-studio",
            model=model or config.LMSTUDIO_MODEL,
            temperature=config.SICAKLIK,
        )

    if saglayici == "openai":
        from langchain_openai import ChatOpenAI
        anahtar = os.getenv("OPENAI_API_KEY")
        if not anahtar:
            raise RuntimeError("OPENAI_API_KEY ortam değişkeni tanımlı değil.")
        return ChatOpenAI(
            api_key=anahtar,
            model=model or config.OPENAI_MODEL,
            temperature=config.SICAKLIK,
        )

    if saglayici == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError:
            raise RuntimeError("Önce şunu çalıştır: pip install langchain-anthropic")
        anahtar = os.getenv("ANTHROPIC_API_KEY")
        if not anahtar:
            raise RuntimeError("ANTHROPIC_API_KEY ortam değişkeni tanımlı değil.")
        return ChatAnthropic(
            api_key=anahtar,
            model=model or config.ANTHROPIC_MODEL,
            temperature=config.SICAKLIK,
            max_tokens=2000,
        )

    if saglayici == "gemini":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError:
            raise RuntimeError("Lütfen önce şunu çalıştırın: pip install langchain-google-genai")

        anahtar = getattr(config, "GEMINI_API_KEY", None) or os.getenv("GEMINI_API_KEY")
        if not anahtar:
            raise RuntimeError("GEMINI_API_KEY bulunamadı. config.py içinde tanımlayın veya ortam değişkeni atayın.")

        return ChatGoogleGenerativeAI(
            model=model or getattr(config, "GEMINI_MODEL", "gemini-1.5-flash"),
            google_api_key=anahtar,
            temperature=config.SICAKLIK,
        )

    if saglayici == "groq":
        from langchain_openai import ChatOpenAI
        anahtar = getattr(config, "GROQ_API_KEY", None) or os.getenv("GROQ_API_KEY")
        if not anahtar:
            raise RuntimeError("GROQ_API_KEY bulunamadı. config.py içinde tanımlayın veya ortam değişkeni atayın.")

        return ChatOpenAI(
            base_url=getattr(config, "GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            api_key=anahtar,
            model=model or getattr(config, "GROQ_MODEL", "llama-3.3-70b-versatile"),
            temperature=config.SICAKLIK,
        )

    raise ValueError(f"Bilinmeyen sağlayıcı: {saglayici}")
