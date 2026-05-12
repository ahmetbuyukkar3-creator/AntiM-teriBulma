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
from datetime import datetime
from typing import List, Dict

from config import Config

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_last_jina_request = 0


def _jina_read(url: str, max_retries: int = 3) -> str:
    """Jina Reader ile bir web sayfasını markdown olarak oku."""
    global _last_jina_request

    for attempt in range(max_retries):
        elapsed = time.time() - _last_jina_request
        if elapsed < 3:
            time.sleep(3 - elapsed)

        safe_url = urllib.parse.quote(url, safe=':/?=&%#')
        jina_url = f"https://r.jina.ai/{safe_url}"
        req = urllib.request.Request(
            jina_url,
            headers={"User-Agent": _UA, "Accept": "text/plain"},
        )
        try:
            _last_jina_request = time.time()
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8")
        except Exception as e:
            logger.warning(f"  ⚠️ Jina okuma hatası ({url}): {e}")
            if "429" in str(e):
                logger.info(f"  ⏳ Rate limit, 20 saniye beklenip tekrar deneniyor... (Deneme {attempt+1}/{max_retries})")
                time.sleep(20)
                continue
            return ""
    return ""


def _jina_search(query: str) -> str:
    """Google arama sonuçlarını Jina Reader ile oku (s.jina.ai yerine)."""
    safe_q = urllib.parse.quote(query)
    google_url = f"https://www.google.com/search?q={safe_q}&num=20&hl=tr"
    return _jina_read(google_url)


def _extract_emails(text: str) -> List[str]:
    """Metinden e-posta adreslerini çıkar."""
    if not text:
        return []
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


def _extract_urls(search_result: str) -> List[Dict]:
    """Jina Search sonucundan firma URL'lerini çıkar."""
    results = []
    # Markdown link formatı: [Title](URL)
    links = re.findall(r'\[([^\]]+)\]\((https?://[^\)]+)\)', search_result)
    for title, url in links:
        # Google/sosyal medya/genel siteler hariç, gerçek firma sitelerini al
        skip = ['google.com', 'facebook.com', 'instagram.com', 'twitter.com',
                'youtube.com', 'linkedin.com', 'tripadvisor', 'yemeksepeti',
                'trendyol', 'sahibinden', 'hepsiburada', 'wikipedia',
                'foursquare', 'yelp', 'jina.ai', 'maps.google']
        if any(s in url.lower() for s in skip):
            continue
        results.append({"title": title.strip(), "url": url.strip()})
    return results


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


def find_leads(count: int = 30) -> List[Dict]:
    logger.info(f"🔍 Toplu arama başlıyor. Hedef: {count} firma — {Config.TARGET_CITY}")

    history = _load_history()
    leads = []

    for category in Config.SEARCH_CATEGORIES:
        if len(leads) >= count:
            break

        logger.info(f"  ▶️ Kategori taranıyor: '{category}'")

        # Jina Search ile Google'da arama yap
        query = f"{category} İzmir iletişim e-posta"
        search_result = _jina_search(query)

        if not search_result:
            logger.info(f"    ⚠️ Arama sonucu boş, diğer kategoriye geçiliyor.")
            continue

        # Arama sonuçlarından e-posta ve URL çek
        # Önce direkt arama sonuçlarındaki e-postaları kontrol et
        direct_emails = _extract_emails(search_result)
        urls = _extract_urls(search_result)

        logger.info(f"    📊 {len(urls)} web sitesi bulundu, {len(direct_emails)} direkt e-posta tespit edildi")

        # Her URL'yi ziyaret edip e-posta ara
        for site in urls:
            if len(leads) >= count:
                break

            title = site["title"]
            url = site["url"]

            # Daha önce bulunmuş mu?
            if title.lower() in {h.lower() for h in history}:
                continue

            # Web sitesini oku
            page_content = _jina_read(url)
            if not page_content:
                continue

            # E-posta çıkar
            emails = _extract_emails(page_content)
            if not emails:
                continue

            # Telefon numarası ara
            phone_match = re.search(r'(?:0\d{3}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}|\+90\s?\d{3}\s?\d{3}\s?\d{2}\s?\d{2})', page_content)
            phone = re.sub(r'\s+', '', phone_match.group(0)) if phone_match else ""

            lead = {
                "business_name": title,
                "category": category,
                "city": Config.TARGET_CITY,
                "phone": phone,
                "address": "",
                "website": url,
                "email": emails[0],
                "instagram": "",
                "facebook": "",
                "found_date": datetime.now().isoformat(),
            }

            leads.append(lead)
            history.add(title)
            logger.info(
                f"    ✅ Lead #{len(leads)}: {title} "
                f"— 📧 {emails[0]} (Kategori: {category})"
            )

    _save_history(history)

    logger.info(f"🎯 Toplam {len(leads)} lead bulundu (hedef: {count})")
    return leads


if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    leads = find_leads(count=3)
    print(json.dumps(leads, ensure_ascii=False, indent=2))

