"""
İzmir Outreach Pipeline — Konfigürasyon
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import os
import json
import logging
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logger = logging.getLogger(__name__)

class Config:
    """Environment variable tabanlı konfigürasyon."""

    @classmethod
    def load_base64_google_auth(cls):
        import base64
        cred_b64 = os.environ.get("GOOGLE_CREDENTIALS_B64")
        if cred_b64 and not os.path.exists(cls.GOOGLE_CREDENTIALS_PATH):
            with open(cls.GOOGLE_CREDENTIALS_PATH, "wb") as f:
                f.write(base64.b64decode(cred_b64))
        
        token_b64 = os.environ.get("GOOGLE_TOKEN_B64")
        if token_b64 and not os.path.exists(cls.GOOGLE_TOKEN_PATH):
            with open(cls.GOOGLE_TOKEN_PATH, "wb") as f:
                f.write(base64.b64decode(token_b64))

    # ── GENEL ────────────────────────────────────────────────────
    PROJECT_NAME = "Izmir_Outreach"
    DAILY_LEAD_COUNT = int(os.environ.get("DAILY_LEAD_COUNT", "10"))  # toplam = klinik 5 + güzellik 5
    DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"

    # ── HEDEF BÖLGE ──────────────────────────────────────────────
    TARGET_CITY = os.environ.get("TARGET_CITY", "İzmir")

    # ── SEKTÖR KATEGORİLERİ (2 branch: Klinik + Güzellik) ──────────
    KLINIK_CATEGORIES = [
        "özel diş kliniği",
        "özel çocuk hastalıkları kliniği",
        "özel dermatoloji kliniği",
        "özel göz kliniği",
        "özel ortopedi kliniği",
        "özel plastik cerrahi kliniği",
        "özel dahiliye kliniği",
        "özel kadın doğum kliniği",
    ]

    GUZELLIK_CATEGORIES = [
        "güzellik merkezi",
        "tırnak bakım salonu",
        "bayan kuaför",
        "kuaför salonu",
        "estetik güzellik salonu",
    ]

    # Geriye dönük uyumluluk için birleşik liste
    SEARCH_CATEGORIES = KLINIK_CATEGORIES + GUZELLIK_CATEGORIES

    # Her segment için gönderilecek mail sayısı (toplam = 2 × bu değer)
    DAILY_LEAD_COUNT_PER_SEGMENT = int(os.environ.get("DAILY_LEAD_COUNT_PER_SEGMENT", "5"))

    # ── TELEGRAM ─────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
    JINA_API_KEY = os.environ.get("JINA_API_KEY", "")

    # ── GMAIL ────────────────────────────────────────────────────
    SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "rumaysoft@gmail.com")
    GOOGLE_CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), "credentials.json")
    GOOGLE_TOKEN_PATH = os.path.join(os.path.dirname(__file__), "token.json")

    # ── LLM ──────────────────────────────────────────────────────
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    KIMI_API_KEY = os.environ.get("KIMI_API_KEY", "")
    LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "kimi")

    # ── VERİ DOSYALARI ───────────────────────────────────────────
    DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
    LEADS_HISTORY_FILE = os.path.join(DATA_DIR, "leads_history.json")
    SENT_EMAILS_FILE = os.path.join(DATA_DIR, "sent_emails.json")
    ROTATION_STATE_FILE = os.path.join(DATA_DIR, "rotation_state.json")

    @classmethod
    def validate(cls):
        """Zorunlu konfigürasyon değerlerini kontrol eder."""
        warnings = []
        if not cls.TELEGRAM_BOT_TOKEN:
            warnings.append("TELEGRAM_BOT_TOKEN tanımlı değil")
        
        os.makedirs(cls.DATA_DIR, exist_ok=True)
        for w in warnings:
            logger.warning(f"⚠️ {w}")
        return True

    @classmethod
    def get_todays_category_index(cls):
        # Artık kullanılmıyor, main.py tüm listeyi tarayacak.
        return 0

    @classmethod
    def advance_rotation(cls):
        # Artık kullanılmıyor, main.py tüm listeyi tarayacak.
        pass

Config.load_base64_google_auth()
