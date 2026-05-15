"""
Lead Analyzer — AI ile Firma Analizi ve Hizmet Eşleştirme
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Bulunan firmayı Groq (Llama3) veya OpenAI kullanarak analiz eder:
- 1-10 arası uygunluk skoru verir.
- Rumaysoft'un hangi hizmetinin (Stok, Web, AI) en uygun olduğunu belirler.
- Maillerde kullanılacak kişiselleştirilmiş bir açılış cümlesi/ipucu üretir.
"""
import json
import logging
import requests
from typing import List, Dict

from config import Config
from lead_finder import _jina_read

logger = logging.getLogger(__name__)

def _call_single_llm(provider: str, api_key: str, model: str, messages: list, timeout: int = 25) -> str:
    """Tek bir LLM sağlayıcısını çağırır."""
    urls = {
        "kimi": "https://api.moonshot.ai/v1/chat/completions",
        "groq": "https://api.groq.com/openai/v1/chat/completions",
        "openai": "https://api.openai.com/v1/chat/completions",
    }
    url = urls.get(provider, "")
    if not url or not api_key:
        return ""

    payload = {"model": model, "messages": messages}
    # Kimi reasoning modelleri temperature desteklemiyor
    if provider != "kimi":
        payload["temperature"] = 0.7
        payload["max_tokens"] = 500

    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_llm(prompt: str, system_prompt: str = "") -> str:
    """Akıllı Fallback: Önce Kimi AI dener, timeout/hata olursa anında Groq'a düşer."""

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    # ── Sıralı deneme listesi (birincil → yedek) ──
    providers = []
    if Config.KIMI_API_KEY:
        providers.append(("kimi", Config.KIMI_API_KEY, "kimi-k2.6", 25))
    if Config.GROQ_API_KEY:
        providers.append(("groq", Config.GROQ_API_KEY, "llama3-70b-8192", 15))
    if Config.OPENAI_API_KEY:
        providers.append(("openai", Config.OPENAI_API_KEY, "gpt-4o-mini", 20))

    if not providers:
        logger.warning("⚠️ Hiçbir LLM API anahtarı bulunamadı — Temel analiz kullanılacak.")
        return ""

    for provider_name, api_key, model, timeout in providers:
        try:
            result = _call_single_llm(provider_name, api_key, model, messages, timeout)
            if result:
                if provider_name != "kimi":
                    logger.info(f"  🔄 Yedek AI ({provider_name.upper()}) devreye girdi ve başarılı.")
                return result
        except Exception as e:
            logger.warning(f"  ⚠️ {provider_name.upper()} başarısız ({type(e).__name__}), sıradaki deneniyor...")
            continue

    logger.error("❌ Tüm LLM sağlayıcıları başarısız — temel şablona düşülüyor.")
    return ""

def analyze_lead(lead: Dict) -> Dict:
    """Tek bir lead'i analiz ederek skor ve hizmet önerisi ekler."""
    
    has_website = bool(lead.get("website"))
    website_content = ""
    
    if has_website:
        logger.info(f"    🔎 Kimi Ajani: Web sitesi okunuyor ({lead.get('website')})")
        # Eğer Kimi için web sitesi içeriğini okumamız gerekirse (Kimi API devasa context'e sahip)
        content = _jina_read(lead.get("website"))
        if content:
            # 32k modele sığması için 25000 karakterle sınırlıyoruz
            website_content = content[:25000]
            logger.info("    ✅ Kimi Ajani: Web sitesi icerigi basariyla cekildi.")
            
    segment = lead.get("segment", "")
    segment_hint = ""
    if segment == "klinik":
        segment_hint = ('DİKKAT: Bu işletme bir ÖZEL KLİNİK. Kliniklerin randevu yönetimi ve hasta iletişimi için '
                        '"ai_asistan" hizmeti KESİNLİKLE doğru seçimdir. Kişiselleştirme ipucunu randevu/hasta '
                        'iletişimi açısından yaz.')
    elif segment == "guzellik":
        segment_hint = ('DİKKAT: Bu işletme bir GÜZELLIK/KUAFÖR merkezi. Müşteri mesajlarını ve randevuları '
                        'otomatikleştirmek için "ai_asistan" hizmeti en uygunudur. Kişiselleştirme ipucunu '
                        'randevu takibi ve müşteri mesajları açısından yaz.')
    elif not has_website:
        segment_hint = 'DİKKAT: BU FİRMANIN WEB SİTESİ YOK. O YÜZDEN KESİNLİKLE "web_sitesi" HİZMETİNİ ÖNER.'
    else:
        segment_hint = 'DİKKAT: BU FİRMANIN ZATEN BİR WEB SİTESİ VAR. O YÜZDEN "web_sitesi" DIŞINDA BİR HİZMET ÖNER (stok_takibi veya ai_asistan).'

    system_prompt = f"""Sen Rumaysoft'un elit araştırma ve satış ajanısın (Kimi).
Sana bir firmanın web sitesi verilerini veya adını/kategorisini vereceğim.
Hedefin bu firmayı derinlemesine analiz edip, Rumaysoft'un hizmetlerinden hangisine KESİN ihtiyacı olduğunu bulmak ve onlara özel, reddedemeyecekleri kadar kişisel bir açılış cümlesi yazmak.

Rumaysoft şu 3 ana hizmeti satar:
1. Akıllı Stok Takip Otomasyonu (Ürün takibi, azalan stok uyarısı)
2. Profesyonel Web Sitesi Kurulumu (Modern, mobil uyumlu)
3. AI Müşteri Asistanı (7/24 otomatik cevap veren bot — randevu, soru, yönlendirme)

{segment_hint}

YANITINI SADECE AŞAĞIDAKİ GİBİ JSON FORMATINDA VER. HİÇBİR AÇIKLAMA YAZMA.
{{
  "uygunluk_skoru": 8,
  "en_uygun_hizmet": "ai_asistan",
  "kisisellestirme_ipucu": "Kliniğinizin web sitesinde randevu formu olduğunu gördüm, hasta mesajlarına 7/24 otomatik cevap veren bir asistan ile hasta memnuniyetini çok artırabilirsiniz."
}}
Not: "en_uygun_hizmet" alanı SADECE şu değerlerden biri olabilir: "stok_takibi", "web_sitesi", "ai_asistan"
"""

    prompt = f"""Lütfen aşağıdaki İzmir işletmesini analiz et:
İşletme Adı: {lead.get('business_name', 'Bilinmiyor')}
Kategori: {lead.get('category', 'Bilinmiyor')}
Web Sitesi var mı?: {'Evet' if has_website else 'Hayır'}
"""

    if website_content:
        prompt += f"\n\n--- İŞLETME WEB SİTESİ İÇERİĞİ ---\n{website_content}\n----------------------------------\nLütfen bu içeriği analiz et ve kişiselleştirme ipucunu çıkar."

    response = _call_llm(prompt, system_prompt)
    
    # Varsayılan temel analiz (API yoksa veya hata olursa)
    analysis = {
        "uygunluk_skoru": 6,
        "en_uygun_hizmet": "web_sitesi" if not has_website else "stok_takibi",
        "kisisellestirme_ipucu": f"{lead.get('business_name', 'İşletmeniz')} için dijital süreçlerinizi hızlandırmak isteriz."
    }
    
    if response:
        try:
            cleaned_response = response.strip()
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response.split("```json")[1].split("```")[0].strip()
            elif cleaned_response.startswith("```"):
                cleaned_response = cleaned_response.split("```")[1].split("```")[0].strip()
                
            ai_data = json.loads(cleaned_response)
            
            analysis["uygunluk_skoru"] = ai_data.get("uygunluk_skoru", 6)
            
            hizmet = ai_data.get("en_uygun_hizmet", "stok_takibi")
            if hizmet in ["stok_takibi", "web_sitesi", "ai_asistan"]:
                analysis["en_uygun_hizmet"] = hizmet
                
            analysis["kisisellestirme_ipucu"] = ai_data.get("kisisellestirme_ipucu", analysis["kisisellestirme_ipucu"])
        except Exception as e:
            logger.warning(f"⚠️ LLM JSON çözümleme hatası: {e}. Yanıt: {response}")

    # ══ KATEGORİ BAZLI KESİN KURAL TABLOSU ══════════════════════
    # Segment'e göre hizmet: klinik+güzellik her zaman ai_asistan.

    SEGMENT_KLINIK_KEYWORDS = [
        "klinik", "diş", "dermatoloji", "çocuk hastalıkları",
        "göz kliniği", "ortopedi", "plastik cerrahi",
        "dahiliye", "kadın doğum", "poliklinik", "tıp merkezi",
    ]

    SEGMENT_GUZELLIK_KEYWORDS = [
        "güzellik", "tırnak", "kuaför", "estetik güzellik",
        "medikal estetik", "manikür", "pedikür", "spa",
    ]

    cat_lower = lead.get("category", "").lower()
    segment = lead.get("segment", "")

    if not has_website:
        analysis["en_uygun_hizmet"] = "web_sitesi"
    elif segment == "klinik" or any(x in cat_lower for x in SEGMENT_KLINIK_KEYWORDS):
        analysis["en_uygun_hizmet"] = "ai_asistan"
    elif segment == "guzellik" or any(x in cat_lower for x in SEGMENT_GUZELLIK_KEYWORDS):
        analysis["en_uygun_hizmet"] = "ai_asistan"
    else:
        # Tanınmayan kategori → güvenli varsayılan
        analysis["en_uygun_hizmet"] = "ai_asistan"

    lead["analysis_score"] = analysis["uygunluk_skoru"]
    lead["best_service"] = analysis["en_uygun_hizmet"]
    lead["personalization_hint"] = analysis["kisisellestirme_ipucu"]
    
    return lead

def analyze_leads(leads: List[Dict]) -> List[Dict]:
    """Birden fazla lead'i topluca analiz eder."""
    logger.info(f"🧠 {len(leads)} firma AI ile analiz ediliyor...")
    analyzed_leads = []
    
    for i, lead in enumerate(leads):
        name = lead.get("business_name", "?")
        logger.info(f"  [{i+1}/{len(leads)}] Analiz: {name}")
        
        analyzed_lead = analyze_lead(lead)
        analyzed_leads.append(analyzed_lead)
        
    logger.info("✅ Tüm firmaların analizi tamamlandı.")
    return analyzed_leads

if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    
    test_leads = [
        {
            "business_name": "DENİZALTI PORT",
            "category": "kafe kahve dükkanı",
            "website": ""
        },
        {
            "business_name": "TELVE CAFE",
            "category": "kafe kahve dükkanı",
            "website": "http://telvecofe.com"
        }
    ]
    
    results = analyze_leads(test_leads)
    print(json.dumps(results, indent=2, ensure_ascii=False))
