"""
İzmir Outreach — Ana Orkestrasyon Modülü (main.py)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tüm pipeline'ı sırasıyla çalıştıran ve Cron Job (Railway vb.) 
tarafından her gün tetiklenecek olan ana betik.
"""
import sys
import io
import logging

import time
import schedule
from config import Config
from lead_finder import find_leads
from lead_analyzer import analyze_leads
from email_composer import compose_emails
from email_sender import send_emails
from telegram_notifier import send_daily_report, send_telegram_message
from reply_checker import check_replies

# Türkçe karakter sorunlarını çözmek için
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

def _is_valid_email(email: str) -> bool:
    """Temel e-posta format doğrulaması. Açık sahte/hatalı adresleri filtreler."""
    import re
    if not email or "@" not in email:
        return False
    pattern = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False
    # Kesinlikle geçersiz domainleri reddet
    invalid_domains = [
        "example.com", "test.com", "domain.com", "yoursite.com",
        "email.com", "mail.com", "noreply", "no-reply",
        "sentry.io", "wixpress.com", "wordpress.com",
    ]
    email_lower = email.lower()
    if any(d in email_lower for d in invalid_domains):
        return False
    # Nokta ile biten veya @ ile başlayan adresler geçersiz
    local, domain = email.rsplit("@", 1)
    if not local or not domain or domain.startswith(".") or domain.endswith("."):
        return False
    return True


def run_pipeline():
    logger.info("==================================================")
    logger.info("🚀 RUMAYSOFT İZMİR OUTREACH BAŞLIYOR (v2 — 2 Branch)")
    logger.info("==================================================")

    # Konfigürasyon kontrolü
    if not Config.validate():
        logger.error("❌ Konfigürasyon hatalı, işlem durduruluyor.")
        sys.exit(1)

    if Config.DRY_RUN:
        logger.info("⚠️ DİKKAT: Sistem DRY-RUN (Test) modunda çalışıyor. Gerçek mail GÖNDERİLMEYECEK.")

    per_segment = Config.DAILY_LEAD_COUNT_PER_SEGMENT  # varsayılan 5

    # ── BRANCH 1: Özel Klinikler ──────────────────────────────────
    logger.info(f"🏥 Branch 1 — Özel Klinikler taranıyor (hedef: {per_segment})...")
    klinik_leads = find_leads(count=per_segment, categories=Config.KLINIK_CATEGORIES)
    for lead in klinik_leads:
        lead["segment"] = "klinik"

    # ── BRANCH 2: Güzellik / Kuaför / Tırnak Bakım ───────────────
    logger.info(f"✨ Branch 2 — Güzellik & Kuaför taranıyor (hedef: {per_segment})...")
    guzellik_leads = find_leads(count=per_segment, categories=Config.GUZELLIK_CATEGORIES)
    for lead in guzellik_leads:
        lead["segment"] = "guzellik"

    # ── Son güvenlik filtresi: ikinci kez geçersiz email kontrolü ──
    # (birincil filtre zaten lead_finder.py içinde yapılıyor)
    all_raw = klinik_leads + guzellik_leads
    seen_emails_final = set()
    leads = []
    for lead in all_raw:
        email = lead.get("email", "").lower().strip()
        if not _is_valid_email(email):
            logger.warning(f"  ⚠️ Son filtre — Geçersiz e-posta atlandı: '{email}' ({lead.get('business_name')})")
            continue
        if email in seen_emails_final:
            logger.warning(f"  ⚠️ Son filtre — Mükerrer e-posta atlandı: '{email}'")
            continue
        seen_emails_final.add(email)
        leads.append(lead)

    if not leads:
        logger.warning("Bugün için geçerli e-postası olan hiçbir firma bulunamadı.")
        send_telegram_message(
            "⚠️ <b>Rumaysoft İzmir Outreach</b>\n"
            "Bugün her iki branch tarandı ancak geçerli e-postası olan hiçbir firma bulunamadı."
        )
        sys.exit(0)

    klinik_count = sum(1 for l in leads if l.get("segment") == "klinik")
    guzellik_count = sum(1 for l in leads if l.get("segment") == "guzellik")
    logger.info(f"📊 Toplam {len(leads)} geçerli lead: 🏥 Klinik={klinik_count}, ✨ Güzellik={guzellik_count}")

    # ── AI ile Analiz ─────────────────────────────────────────────
    analyzed_leads = analyze_leads(leads)

    # ── Kişiselleştirilmiş Mailleri Hazırla ──────────────────────
    ready_leads = compose_emails(analyzed_leads)

    # ── Mailleri Gönder ───────────────────────────────────────────
    send_telegram_message(
        f"⏳ <b>Bilgilendirme</b>\n"
        f"{len(ready_leads)} firma hazırlandı (🏥 {klinik_count} klinik + ✨ {guzellik_count} güzellik).\n"
        f"Şimdi mail gönderimi başlıyor. Bittiğinde rapor gelecek."
    )
    send_results = send_emails(ready_leads)

    # ── Telegram Günlük Raporu ────────────────────────────────────
    send_daily_report(ready_leads, send_results)

    # ── Yanıt Kontrolü ────────────────────────────────────────────
    check_replies()

    logger.info("==================================================")
    logger.info("✅ GÜNLÜK İŞLEM BAŞARIYLA TAMAMLANDI")
    logger.info("==================================================")

def main():
    logger.info("🕒 Sistem başlatıldı. Zamanlayıcı (Cron) devrede.")
    logger.info("   -> Çalışma Sıklığı: Her saat başı")
    
    # Her saat başı çalışacak şekilde zamanlayıcı kuruldu
    schedule.every().hour.do(run_pipeline)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception(f"Kritik Sistem Hatası: {e}")
        send_telegram_message(f"❌ <b>SİSTEM HATASI</b>\n\nOutreach scripti çöktü!\nHata: <code>{e}</code>")
        sys.exit(1)
