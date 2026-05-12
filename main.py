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

def run_pipeline():
    logger.info("==================================================")
    logger.info("🚀 RUMAYSOFT İZMİR OUTREACH BAŞLIYOR")
    logger.info("==================================================")
    
    # Konfigürasyon kontrolü
    if not Config.validate():
        logger.error("❌ Konfigürasyon hatalı, işlem durduruluyor.")
        sys.exit(1)
        
    if Config.DRY_RUN:
        logger.info("⚠️ DİKKAT: Sistem DRY-RUN (Test) modunda çalışıyor. Gerçek mail GÖNDERİLMEYECEK.")
    
    # 1. Aşama: Firmaları bul (Geniş havuz taraması)
    leads = find_leads(count=Config.DAILY_LEAD_COUNT)
    
    if not leads:
        logger.warning("Bugün için uygun hiçbir firma (mailli) bulunamadı.")
        send_telegram_message("⚠️ <b>Rumaysoft İzmir Outreach</b>\nBugün 500'e yakın sayfa taranmasına rağmen e-postası olan hiçbir firma bulunamadı.")
        sys.exit(0)
        
    # 3. Aşama: AI ile Analiz et (Hizmet belirle)
    analyzed_leads = analyze_leads(leads)
    
    # 4. Aşama: Kişiselleştirilmiş Mailleri Hazırla
    ready_leads = compose_emails(analyzed_leads)
    
    # 5. Aşama: Mailleri Gönder
    send_results = send_emails(ready_leads)
    
    # 6. Aşama: Telegram Günlük Raporu At
    send_daily_report(ready_leads, send_results)
    
    # 7. Aşama: Önceki maillere yanıt gelmiş mi kontrol et
    check_replies()
    
    logger.info("==================================================")
    logger.info("✅ GÜNLÜK İŞLEM BAŞARIYLA TAMAMLANDI")
    logger.info("==================================================")

def main():
    logger.info("🕒 Sistem başlatıldı. Zamanlayıcı (Cron) devrede.")
    logger.info("   -> Çalışma saatleri (TSİ): Sabah 09:00 ve Akşam 18:00")
    
    # Sunucu UTC saatinde çalıştığı için Türkiye Saati (TSİ = UTC+3) ayarlaması yapıyoruz.
    # 09:00 TSİ -> 06:00 UTC
    # 18:00 TSİ -> 15:00 UTC
    schedule.every().day.at("06:00").do(run_pipeline)
    schedule.every().day.at("15:00").do(run_pipeline)
    
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
