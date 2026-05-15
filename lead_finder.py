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


def _extract_emails(text: str) -> List[str]:
    """Metinden e-posta adreslerini çıkar."""
    if not text:
        return []
    import re
    pattern = r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
    emails = re.findall(pattern, text)
    # Spam / sahte olanları filtrele
    blocked = ['example.com', 'sentry.io', 'wixpress', 'email.com',
               'domain.com', 'yoursite', 'test.com', 'wordpress',
               'placeholder', '.png', '.jpg', '.gif', '.svg']
    clean = []
    for e in emails:
        e_lower = e.lower()
        if any(b in e_lower for b in blocked):
            continue
        if len(e) > 60:
            continue
            
        # Typo düzeltmesi
        if e_lower.endswith("@mail.com"):
            e = e[:-9] + "@gmail.com"
            e_lower = e.lower()
            
        clean.append(e)
    return list(set(clean))

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
    count kadar lead bulur.
    categories verilmezse Config.SEARCH_CATEGORIES kullanılır.
    """
    cats = list(categories) if categories else list(Config.SEARCH_CATEGORIES)
    logger.info(f"🔍 Toplu arama başlıyor. Hedef: {count} firma — {Config.TARGET_CITY} | Kategoriler: {cats}")

    history = _load_history()
    leads = []

    categories = cats
    random.shuffle(categories)

    for category in categories:
        if len(leads) >= count:
            break

        logger.info(f"  ▶️ Kategori taranıyor: '{category}'")

        # Apify ile arama yap
        query = f"{category} {Config.TARGET_CITY}"
        urls = _apify_search_google_maps(query, limit=count + 5)

        if not urls:
            logger.info(f"    ⚠️ Apify sonucu boş veya hata oluştu, diğer kategoriye geçiliyor.")
            continue

        # Her URL'yi ziyaret edip e-posta ara
        for site in urls:
            if len(leads) >= count:
                break

            title = site["title"]
            url = site["url"]

            # Daha önce bulunmuş mu?
            if title.lower() in {h.lower() for h in history}:
                continue

            # E-posta bul: Önce Apify'den, yoksa siteden çek
            apify_email = site.get("apify_email", "")
            
            if apify_email and "@" in apify_email:
                # Apify direkt vermiş, siteye girmeye gerek yok
                best_email = apify_email
                page_content = ""
                logger.info(f"    📧 Apify'den direkt mail alındı: {apify_email}")
            else:
                # Siteye girip mail kazı
                page_content = _jina_read(url)
                if not page_content:
                    continue

                emails = _extract_emails(page_content)
                if not emails:
                    continue
                
                # Kişisel maili tercih et (info@ en son seçenek)
                personal = [e for e in emails if not e.lower().startswith("info@")]
                best_email = personal[0] if personal else emails[0]

            phone = site.get("phone", "")
            if not phone:
                # Eğer Apify'da telefon yoksa sayfadan tarayalım
                phone_match = re.search(r'(?:0\d{3}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}|\+90\s?\d{3}\s?\d{3}\s?\d{2}\s?\d{2})', page_content)
                phone = re.sub(r'\s+', '', phone_match.group(0)) if phone_match else ""

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
            history.add(title)
            logger.info(
                f"    ✅ Lead #{len(leads)}: {title} "
                f"— 📧 {best_email} (Kategori: {category})"
            )

    _save_history(history)

    logger.info(f"🎯 Toplam {len(leads)} lead bulundu (hedef: {count})")
    return leads


if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    leads = find_leads(count=2, categories=Config.KLINIK_CATEGORIES)
    print(json.dumps(leads, ensure_ascii=False, indent=2))

