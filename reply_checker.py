"""
Reply Checker — Gelen Yanıtları Kontrol Eden Modül
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Gmail Inbox'ını tarar ve daha önce bizim tarafımızdan gönderilmiş 
outreach maillerine gelen yanıtları bulup Telegram'a iletir.
"""
import json
import os
import logging
from datetime import datetime
import dateutil.parser

from googleapiclient.errors import HttpError
from email_sender import get_gmail_service
from telegram_notifier import send_reply_alert
from config import Config

logger = logging.getLogger(__name__)

def load_processed_replies() -> set:
    file_path = os.path.join(Config.DATA_DIR, "processed_replies.json")
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("processed_ids", []))
        except Exception:
            pass
    return set()

def save_processed_replies(processed_ids: set):
    file_path = os.path.join(Config.DATA_DIR, "processed_replies.json")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(
            {"processed_ids": list(processed_ids), "last_updated": datetime.now().isoformat()},
            f, indent=2
        )

def check_replies():
    """Gelen kutusundaki yeni yanıtları kontrol eder."""
    logger.info("📬 Gelen kutusunda yeni yanıtlar kontrol ediliyor...")
    
    service = get_gmail_service()
    if not service:
        logger.error("❌ Gmail servisi başlatılamadığı için yanıt kontrolü iptal edildi.")
        return

    processed_ids = load_processed_replies()
    
    try:
        # Gelen kutusundaki mailleri getir (Sadece INBOX ve okunmamış/okunmuş, son 7 gün)
        query = "in:inbox newer_than:7d"
        results = service.users().messages().list(userId='me', q=query).execute()
        messages = results.get('messages', [])

        if not messages:
            logger.info("  📭 Son 7 gün içinde gelen kutusunda hiç mesaj yok.")
            return

        new_replies_count = 0

        for msg in messages:
            msg_id = msg['id']
            if msg_id in processed_ids:
                continue

            # Mesajın detaylarını al
            msg_detail = service.users().messages().get(userId='me', id=msg_id, format='metadata', metadataHeaders=['From', 'Subject', 'Date', 'In-Reply-To', 'References']).execute()
            headers = msg_detail.get('payload', {}).get('headers', [])
            
            sender = ""
            subject = ""
            date = ""
            is_reply = False
            
            for header in headers:
                name = header['name'].lower()
                if name == 'from':
                    sender = header['value']
                elif name == 'subject':
                    subject = header['value']
                elif name == 'date':
                    date = header['value']
                elif name == 'in-reply-to' or name == 'references':
                    # Eğer bu başlıklar varsa, bu mail bir şeye yanıttır.
                    is_reply = True

            # Eğer bizim mailimize verilmiş bir yanıtsa (is_reply) ve spam değilse
            if is_reply and "mailer-daemon" not in sender.lower():
                snippet = msg_detail.get('snippet', '')
                
                # Tarihi düzelt
                try:
                    dt = dateutil.parser.parse(date)
                    date_str = dt.strftime("%d %b %Y %H:%M")
                except Exception:
                    date_str = date

                # Telegrama bildir
                logger.info(f"  🔔 Yeni yanıt bulundu: {sender} -> {subject}")
                send_reply_alert(
                    business_name="Yanıt Veren",
                    email=sender,
                    snippet=snippet,
                    date=date_str
                )
                new_replies_count += 1
            
            # Mesajı işlendi olarak işaretle (ister yanıtsın ister normal mail, tekrar bakmayalım)
            processed_ids.add(msg_id)

        save_processed_replies(processed_ids)
        logger.info(f"✅ Yanıt kontrolü tamamlandı. Yeni bulunan yanıt sayısı: {new_replies_count}")

    except HttpError as error:
        logger.error(f"❌ Gmail API hatası: {error}")

if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    check_replies()
