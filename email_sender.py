"""
Email Sender — Gmail API ile E-posta Gönderimi
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Gmail API kullanarak yetkilendirme yapar ve hazırlanan 
kişiselleştirilmiş e-postaları hedeflere gönderir.
"""
import os
import base64
import logging
from typing import List, Dict
from email.message import EmailMessage

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import Config

logger = logging.getLogger(__name__)
SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly'
]
def get_gmail_service():
    """Gmail API servisini başlatır ve kimlik doğrulamasını yapar."""
    creds = None
    
    # 1. Kayıtlı token var mı kontrol et
    if os.path.exists(Config.GOOGLE_TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(Config.GOOGLE_TOKEN_PATH, SCOPES)
        except Exception as e:
            logger.warning(f"Mevcut token okunamadı: {e}")
            
    # 2. Geçerli değilse veya yoksa yeniden al
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.warning(f"Token yenilenemedi: {e}")
                creds = None
                
        if not creds:
            if not os.path.exists(Config.GOOGLE_CREDENTIALS_PATH):
                logger.error(f"❌ Kimlik bilgisi dosyası bulunamadı: {Config.GOOGLE_CREDENTIALS_PATH}")
                return None
                
            flow = InstalledAppFlow.from_client_secrets_file(
                Config.GOOGLE_CREDENTIALS_PATH, SCOPES)
            # Local server üzerinden auth (Kullanıcının tarayıcıda onaylaması gerekir)
            creds = flow.run_local_server(port=0)
            
        # Yeni token'ı kaydet
        with open(Config.GOOGLE_TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())
            
    try:
        service = build('gmail', 'v1', credentials=creds)
        return service
    except Exception as e:
        logger.error(f"❌ Gmail servisi başlatılamadı: {e}")
        return None

def send_single_email(service, to_email: str, subject: str, body: str) -> bool:
    """Tek bir e-postayı Gmail API üzerinden gönderir."""
    if Config.DRY_RUN:
        logger.info(f"  [DRY-RUN] Mail gönderildi sayıldı -> 📧 {to_email} | Konu: {subject}")
        return True
        
    try:
        message = EmailMessage()
        message.set_content(body)
        message['To'] = to_email
        message['From'] = Config.SENDER_EMAIL
        message['Subject'] = subject

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}

        service.users().messages().send(userId="me", body=create_message).execute()
        return True
    except HttpError as error:
        logger.error(f"❌ Gönderim hatası ({to_email}): {error}")
        return False

def send_emails(leads: List[Dict]) -> Dict:
    """Tüm lead'lere hazırlanan mailleri gönderir ve sonuç raporu döner."""
    results = {"success": 0, "failed": 0, "total": len(leads), "details": []}
    
    if not leads:
        logger.info("📪 Gönderilecek mail bulunmuyor.")
        return results
        
    logger.info(f"🚀 {len(leads)} firmaya mail gönderimi başlıyor...")
    
    service = get_gmail_service()
    if not service and not Config.DRY_RUN:
        logger.error("❌ Gmail yetkilendirmesi başarısız olduğu için gönderim iptal edildi.")
        results["failed"] = len(leads)
        return results

    for lead in leads:
        email = lead.get("email")
        subject = lead.get("email_subject")
        body = lead.get("email_body")
        business_name = lead.get("business_name")
        
        if not email or not subject or not body:
            logger.warning(f"  ⚠️ Eksik veri, atlanıyor: {business_name}")
            results["failed"] += 1
            continue
            
        logger.info(f"  📨 Gönderiliyor: {business_name} ({email})")
        success = send_single_email(service, email, subject, body)
        
        if success:
            results["success"] += 1
            lead["status"] = "sent"
        else:
            results["failed"] += 1
            lead["status"] = "failed"
            
        results["details"].append(lead)
        
    logger.info(f"✅ Gönderim tamamlandı. Başarılı: {results['success']}, Başarısız: {results['failed']}")
    return results

if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    
    # Test için
    Config.DRY_RUN = True
    test_leads = [
        {
            "business_name": "Test Firma",
            "email": "test@ornek.com",
            "email_subject": "Merhaba Test Firma",
            "email_body": "Bu bir test mesajıdır."
        }
    ]
    send_emails(test_leads)
