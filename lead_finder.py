"""
Lead Finder — Jina Search + Reader ile İzmir İşletme Bulucu (V2)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Jina Search API (s.jina.ai) ile Google arama sonuçlarını tarar,
bulunan firmaların web sitelerine girerek e-posta adreslerini çıkarır.
"""
import json
import os
import re
import logging
import urllib.request
import urllib.parse
import time
import random
from datetime import datetime
from typing import List, Dict

from config import Config

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_last_jina_request = 0


def _jina_read(url: str, max_retries: int = 5) -> str:
    """Jina Reader ile bir web sayfasını markdown olarak oku. Başarısız olursa direkt çek."""
    global _last_jina_request

    for attempt in range(max_retries):
        elapsed = time.time() - _last_jina_request
        if elapsed < 6:
            time.sleep(6 - elapsed)

        safe_url = urllib.parse.quote(url, safe=':/?=&%#')
        jina_url = f"https://r.jina.ai/{safe_url}"
        headers = {"User-Agent": _UA, "Accept": "text/plain"}
        if Config.JINA_API_KEY:
            headers["Authorization"] = f"Bearer {Config.JINA_API_KEY}"
        req = urllib.request.Request(jina_url, headers=headers)
        try:
            _last_jina_request = time.time()
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8")
        except Exception as e:
            logger.warning(f"  ⚠️ Jina okuma hatası ({url}): {e}")
            if "429" in str(e):
                wait_time = 30 * (2 ** attempt)
                logger.info(f"  ⏳ Rate limit, {wait_time} saniye bekleniyor... (Deneme {attempt+1}/{max_retries})")
                time.sleep(wait_time)
                continue
            break # break to fallback
            
    # Fallback: Direkt siteye gir (Jina başarısız olduysa)
    try:
        import requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        logger.info(f"  🔄 Direkt HTTP isteği atılıyor (Fallback): {url}")
        resp = requests.get(url, headers={"User-Agent": _UA}, timeout=20, verify=False)
        return resp.text
    except Exception as e:
        logger.warning(f"  ❌ Direkt istek de başarısız ({url}): {e}")
        return ""


# Domain tam eşleşme blocklist (gmail.com, hotmail.com gibi geçerli domainleri etkilemez)
_BLOCKED_DOMAINS = {
    "example.com", "test.com", "domain.com", "yoursite.com",
    "sample.com", "placeholder.com", "company.com", "email.com",
    "yourcompany.com", "yourdomain.com", "site.com", "website.com",
    "mail.com", "email.net",
    "wixpress.com", "wordpress.com", "squarespace.com",
    "facebook.com", "instagram.com", "twitter.com", "google.com",
    "linkedin.com", "youtube.com", "tiktok.com",
    "sentry.io",
}

# Local kısım (@ öncesi) için prefix blocklist
_BLOCKED_LOCAL_PREFIXES = [
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "mailer-daemon", "postmaster", "bounce",
]

# Domain içinde aranacak substring'ler (platform adları)
_BLOCKED_DOMAIN_SUBSTRINGS = [
    "wixpress", "godaddy", "hostinger", "mailchimp", "sendgrid",
    "shopify", "squarespace",
]

# Dosya uzantıları local kısmında veya domain kısmında olmamalı
_BLOCKED_EXTENSIONS = [".png", ".jpg", ".gif", ".svg", ".webp", ".ico"]


def _is_deliverable_email(email: str) -> bool:
    """
    E-postanın gerçek bir işletmeye ait olup olmadığını kontrol eder.
    gmail.com / hotmail.com / outlook.com gibi geçerli sağlayıcıları BLOKE ETMEZ.
    """
    if not email or "@" not in email:
        return False

    email = email.strip()

    if len(email) > 80 or len(email) < 6:
        return False

    if not re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', email):
        return False

    email_lower = email.lower()
    local, domain = email_lower.rsplit("@", 1)

    # Domain yapı kontrolü
    if "." not in domain or domain.startswith(".") or domain.endswith("."):
        return False
    tld = domain.rsplit(".", 1)[-1]
    if len(tld) < 2 or len(tld) > 6:
        return False

    # Domain tam eşleşme bloğu (gmail.com etkilenmez)
    if domain in _BLOCKED_DOMAINS:
        return False

    # Domain içinde platform adı geçiyor mu?
    if any(b in domain for b in _BLOCKED_DOMAIN_SUBSTRINGS):
        return False

    # Local kısım blocklisti
    if any(local.startswith(p) for p in _BLOCKED_LOCAL_PREFIXES):
        return False

    # Dosya uzantısı hataları
    if any(ext in email_lower for ext in _BLOCKED_EXTENSIONS):
        return False

    # Tamamen rakamdan oluşan local = sistem adresi
    if re.match(r'^\d+$', local):
        return False

    return True


def _extract_emails(text: str) -> List[str]:
    """Metinden yüksek kaliteli e-posta adreslerini çıkarır."""
    if not text:
        return []

    raw = re.findall(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', text)
    clean = []
    for e in raw:
        # Typo düzeltmesi: @mail.com → @gmail.com (yaygın Türk yazım hatası)
        if e.lower().endswith("@mail.com"):
            e = e[:-9] + "@gmail.com"
        if _is_deliverable_email(e):
            clean.append(e)

    # Öncelik sırası: kişisel/direkt > info@ > diğerleri
    def _priority(addr):
        a = addr.lower()
        if a.startswith("info@") or a.startswith("iletisim@") or a.startswith("contact@"):
            return 2
        if a.startswith("noreply") or a.startswith("no-reply"):
            return 10  # en düşük öncelik
        return 1  # kişisel adres → en yüksek öncelik

    clean = sorted(set(clean), key=_priority)
    return clean

def _apify_search_google_maps(query: str, limit: int = 30) -> List[Dict]:
    """Apify üzerinden Google Maps araması yapar, engellere takılmaz."""
    if not Config.APIFY_TOKEN:
        logger.error("❌ APIFY_TOKEN bulunamadı. Lütfen .env dosyasını kontrol edin.")
        return []

    url = f"https://api.apify.com/v2/acts/compass~crawler-google-places/runs?token={Config.APIFY_TOKEN}"
    payload = {
        "searchStringsArray": [query],
        "maxCrawledPlacesPerSearch": limit,
        "language": "tr",
        "countryCode": "tr"
    }
    
    logger.info(f"  🤖 Apify Google Maps Extractor başlatılıyor: '{query}'")
    try:
        import requests
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        run_id = resp.json()["data"]["id"]
        
        # İşlemin bitmesini bekle
        logger.info(f"  ⏳ Apify görevi ({run_id}) başlatıldı. Tamamlanması bekleniyor...")
        while True:
            status_url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={Config.APIFY_TOKEN}"
            status_resp = requests.get(status_url, timeout=15).json()
            status = status_resp["data"]["status"]
            
            if status == "SUCCEEDED":
                dataset_id = status_resp["data"]["defaultDatasetId"]
                break
            elif status in ["FAILED", "ABORTED", "TIMED-OUT"]:
                logger.error(f"  ❌ Apify görevi başarısız oldu: {status}")
                return []
            time.sleep(5)
            
        # Sonuçları çek
        dataset_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={Config.APIFY_TOKEN}"
        items = requests.get(dataset_url, timeout=15).json()
        
        results = []
        for item in items:
            website = item.get("website")
            if website:
                # Sosyal medya/genel siteler hariç
                skip = ['google.com', 'facebook.com', 'instagram.com', 'twitter.com',
                        'youtube.com', 'linkedin.com', 'tripadvisor', 'yemeksepeti',
                        'trendyol', 'sahibinden', 'hepsiburada', 'wikipedia']
                if any(s in website.lower() for s in skip):
                    continue
                    
                results.append({
                    "title": item.get("title", ""),
                    "url": website,
                    "phone": item.get("phoneUnformatted", item.get("phone", "")),
                    "apify_email": item.get("email", ""),  # Apify'den direkt gelen mail
                })
        logger.info(f"  ✅ Apify'den web sitesi olan {len(results)} işletme alındı.")
        return results

    except Exception as e:
        logger.error(f"❌ Apify arama hatası: {e}")
        return []


def _load_history() -> set:
    if os.path.exists(Config.LEADS_HISTORY_FILE):
        try:
            with open(Config.LEADS_HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("found_businesses", []))
        except Exception:
            pass
    return set()


def _save_history(history: set):
    os.makedirs(os.path.dirname(Config.LEADS_HISTORY_FILE), exist_ok=True)
    with open(Config.LEADS_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"found_businesses": list(history), "last_updated": datetime.now().isoformat()},
            f, ensure_ascii=False, indent=2
        )


def find_leads(count: int = 5, categories: list = None) -> List[Dict]:
    """
    Geçerli e-postası olan `count` kadar lead bulana kadar çalışır.
    Geçersiz/sahte e-postalar sayıma dahil edilmez — yeni aday aranır.
    categories verilmezse Config.SEARCH_CATEGORIES kullanılır.
    """
    cats = list(categories) if categories else list(Config.SEARCH_CATEGORIES)
    logger.info(f"🔍 Lead arama başlıyor. Hedef: {count} geçerli firma — {Config.TARGET_CITY}")

    history = _load_history()
    seen_emails: set = set()  # Bu çalışma içinde mükerrer mail önleme
    leads = []

    shuffled_cats = cats[:]
    random.shuffle(shuffled_cats)

    # Kategorileri iki kez dön — ilk turda bulamazsak tekrar dene
    for category in shuffled_cats * 2:
        if len(leads) >= count:
            break

        logger.info(f"  ▶️ '{category}' taranıyor ({len(leads)}/{count} bulundu)...")

        # Apify: count'un 3 katı aday çek — filtrelemeden sonra yeterli kalacak
        search_query = f"{category} {Config.TARGET_CITY}"
        candidates = _apify_search_google_maps(search_query, limit=max(count * 3, 15))

        if not candidates:
            logger.info(f"    ⚠️ Apify sonuç döndürmedi, sonraki kategoriye geçiliyor.")
            continue

        for site in candidates:
            if len(leads) >= count:
                break

            title = site.get("title", "").strip()
            url = site.get("url", "").strip()

            if not title or not url:
                continue

            # Daha önce bu işletmeye mail atıldı mı?
            if title.lower() in {h.lower() for h in history}:
                logger.info(f"    ⏭️  Zaten gönderildi, atlanıyor: {title}")
                continue

            # ── E-posta Bulma ve Kalite Filtresi ──────────────────
            best_email = ""
            page_content = ""

            # Önce Apify'nin direkt verdiği maili dene
            apify_email = site.get("apify_email", "").strip()
            if apify_email and _is_deliverable_email(apify_email):
                best_email = apify_email
                logger.info(f"    📧 Apify maili kullanıldı: {apify_email}")
            elif apify_email and apify_email.lower().endswith("@mail.com"):
                # Typo düzeltmesi
                fixed = apify_email[:-9] + "@gmail.com"
                if _is_deliverable_email(fixed):
                    best_email = fixed
                    logger.info(f"    📧 Apify maili düzeltildi: {apify_email} → {fixed}")

            # Apify'den geçerli mail gelmedi → siteyi tara
            if not best_email:
                page_content = _jina_read(url)
                if not page_content:
                    logger.info(f"    ⚠️  Sayfa okunamadı, atlanıyor: {title}")
                    continue

                emails = _extract_emails(page_content)
                if not emails:
                    logger.info(f"    ⚠️  Geçerli mail bulunamadı: {title}")
                    continue

                best_email = emails[0]  # _extract_emails zaten kaliteye göre sıralı döner
                logger.info(f"    📧 Siteden mail çekildi: {best_email}")

            # Bu çalışmada zaten bu maile gönderim olacak mı?
            if best_email.lower() in seen_emails:
                logger.info(f"    ⏭️  Mükerrer mail, atlanıyor: {best_email}")
                continue

            # Telefon bul
            phone = site.get("phone", "")
            if not phone and page_content:
                m = re.search(
                    r'(?:0\d{3}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}|\+90\s?\d{3}\s?\d{3}\s?\d{2}\s?\d{2})',
                    page_content
                )
                phone = re.sub(r'\s+', '', m.group(0)) if m else ""

            lead = {
                "business_name": title,
                "category": category,
                "city": Config.TARGET_CITY,
                "phone": phone,
                "address": "",
                "website": url,
                "email": best_email,
                "instagram": "",
                "facebook": "",
                "found_date": datetime.now().isoformat(),
            }

            leads.append(lead)
            seen_emails.add(best_email.lower())
            history.add(title)
            logger.info(f"    ✅ Lead #{len(leads)}/{count}: {title} — 📧 {best_email}")

    _save_history(history)

    if len(leads) < count:
        logger.warning(f"⚠️  Hedef {count} lead'e ulaşılamadı, {len(leads)} lead bulundu.")
    else:
        logger.info(f"🎯 {len(leads)} geçerli lead bulundu.")

    return leads


if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    leads = find_leads(count=2, categories=Config.KLINIK_CATEGORIES)
    print(json.dumps(leads, ensure_ascii=False, indent=2))

