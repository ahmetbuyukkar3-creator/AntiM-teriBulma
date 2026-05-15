"""
Telegram Notifier — İşlem Özeti ve Yanıt Bildirimleri
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Günlük yapılan mail atma işlemlerinin sonucunu ve 
eğer gelen bir yanıt olursa anında Telegram üzerinden raporlar.
"""
import logging
import requests
from typing import List, Dict

from config import Config

logger = logging.getLogger(__name__)

def send_telegram_message(message: str) -> bool:
    """Telegram Bot API kullanarak mesaj gönderir."""
    token = Config.TELEGRAM_BOT_TOKEN
    chat_id = Config.TELEGRAM_CHAT_ID
    
    if not token or not chat_id:
        logger.warning("⚠️ Telegram Token veya Chat ID eksik, mesaj gönderilmedi.")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"❌ Telegram mesaj hatası: {e}")
        return False

def get_updates_and_set_chat_id():
    """Bota atılan son mesaja bakarak Chat ID'yi bulur ve .env'yi günceller (yardımcı fonksiyon)."""
    token = Config.TELEGRAM_BOT_TOKEN
    if not token:
        return
        
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        
        if data.get("ok") and data.get("result"):
            # En son mesajlaşan kişinin ID'sini al
            chat_id = data["result"][-1]["message"]["chat"]["id"]
            logger.info(f"🔑 Bulunan Telegram Chat ID: {chat_id}")
            return str(chat_id)
        else:
            logger.warning("⚠️ Bot'a atılmış yeni mesaj bulunamadı. Lütfen bota 'merhaba' yazın.")
            return None
    except Exception as e:
        logger.error(f"❌ getUpdates hatası: {e}")
        return None

def send_daily_report(analyzed_leads: List[Dict], send_results: Dict):
    """Günlük gönderim sonrası detaylı rapor mesajı hazırlar ve atar."""
    
    if not analyzed_leads:
        send_telegram_message("⚠️ <b>Rumaysoft İzmir Outreach</b>\nBugün 500'e yakın sayfa taranmasına rağmen e-postası olan hiçbir firma bulunamadı.")
        return
        
    klinik_leads = [l for l in analyzed_leads if l.get("segment") == "klinik"]
    guzellik_leads = [l for l in analyzed_leads if l.get("segment") == "guzellik"]
    other_leads = [l for l in analyzed_leads if l.get("segment") not in ("klinik", "guzellik")]

    lines = [
        "📊 <b>Rumaysoft İzmir Outreach — Günlük Rapor (v2)</b>",
        f"📅 Hedef Şehir: <i>{Config.TARGET_CITY}</i>",
        f"🏥 Klinik: <b>{len(klinik_leads)}</b> | ✨ Güzellik: <b>{len(guzellik_leads)}</b>",
        "",
        "🔍 <b>Gönderilen Firmalar:</b>"
    ]

    segment_groups = []
    if klinik_leads:
        segment_groups.append(("🏥 Özel Klinikler", klinik_leads))
    if guzellik_leads:
        segment_groups.append(("✨ Güzellik & Kuaför", guzellik_leads))
    if other_leads:
        segment_groups.append(("📂 Diğer", other_leads))

    for segment_title, items in segment_groups:
        lines.append(f"\n<b>{segment_title}</b>")
        for i, lead in enumerate(items):
            name = lead.get("business_name")
            email = lead.get("email")
            hizmet = lead.get("best_service", "").replace("_", " ").title()

            has_web = bool(lead.get("website"))
            web_tag = "🌐" if has_web else "🚫"

            status_icon = "✅" if lead.get("status") == "sent" else "❌"

            lines.append(f"  {i+1}. {web_tag} <b>{name}</b>")
            lines.append(f"     📧 {email} {status_icon}")
            lines.append(f"     💡 <i>{hizmet}</i>")

    lines.append("")
    lines.append("✉️ <b>Özet:</b>")
    lines.append(f"Başarılı: <b>{send_results.get('success', 0)}</b> | Başarısız: <b>{send_results.get('failed', 0)}</b>")
    
    message = "\n".join(lines)
    
    logger.info("📱 Telegram günlük raporu gönderiliyor...")
    success = send_telegram_message(message)
    if success:
        logger.info("✅ Telegram raporu gönderildi.")

def send_reply_alert(business_name: str, email: str, snippet: str, date: str):
    """Müşteriden yanıt geldiğinde atılacak anlık bildirim."""
    message = (
        "🔔 <b>YENİ YANIT GELDİ!</b>\n\n"
        f"🏢 <b>Firma:</b> {business_name}\n"
        f"📧 <b>Mail:</b> {email}\n"
        f"⏰ <b>Tarih:</b> {date}\n\n"
        f"💬 <b>Gelen Mesaj Özeti:</b>\n<i>\"{snippet}...\"</i>\n\n"
        "➡️ <i>Hemen Gmail'e girerek yanıtlayın.</i>"
    )
    send_telegram_message(message)

if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    
    # Test için chat_id bulma
    if not Config.TELEGRAM_CHAT_ID:
        found_id = get_updates_and_set_chat_id()
        if found_id:
            Config.TELEGRAM_CHAT_ID = found_id
            
    if Config.TELEGRAM_CHAT_ID:
        test_leads = [
            {
                "business_name": "Test Cafe",
                "category": "kafe kahve dükkanı",
                "email": "test@cafe.com",
                "best_service": "stok_takibi",
                "status": "sent"
            }
        ]
        test_results = {"success": 1, "failed": 0}
        send_daily_report(test_leads, test_results)
