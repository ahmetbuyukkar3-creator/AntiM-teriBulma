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

def _call_llm(prompt: str, system_prompt: str = "") -> str:
    """Belirtilen LLM sağlayıcısını çağırarak yanıt alır."""
    
    if Config.LLM_PROVIDER == "kimi" and Config.KIMI_API_KEY:
        url = "https://api.moonshot.ai/v1/chat/completions"
        api_key = Config.KIMI_API_KEY
        model = "kimi-k2.6" # Yeni Kimi K2.6 modeli
    elif Config.LLM_PROVIDER == "groq" and Config.GROQ_API_KEY:
        url = "https://api.groq.com/openai/v1/chat/completions"
        api_key = Config.GROQ_API_KEY
        model = "llama3-70b-8192" # Groq modeli
    elif Config.OPENAI_API_KEY:
        url = "https://api.openai.com/v1/chat/completions"
        api_key = Config.OPENAI_API_KEY
        model = "gpt-4o-mini"
    else:
        logger.warning("⚠️ LLM API anahtarı (Kimi/Groq/OpenAI) bulunamadı — Temel analiz kullanılacak.")
        return ""
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": model,
        "messages": messages,
    }
    
    # Kimi K2.6 gibi reasoning modelleri temperature=0.7 desteklemiyor
    if Config.LLM_PROVIDER != "kimi":
        payload["temperature"] = 0.7
        payload["max_tokens"] = 500

    try:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"❌ LLM çağrı hatası: {e}")
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
            
    system_prompt = f"""Sen Rumaysoft'un elit araştırma ve satış ajanısın (Kimi).
Sana bir firmanın web sitesi verilerini veya adını/kategorisini vereceğim.
Hedefin bu firmayı derinlemesine analiz edip, Rumaysoft'un 3 hizmetinden hangisine KESİN ihtiyacı olduğunu bulmak ve onlara özel, reddedemeyecekleri kadar kişisel bir açılış cümlesi yazmak.

Rumaysoft şu 3 ana hizmeti satar:
1. Akıllı Stok Takip Otomasyonu (Ürün takibi, azalan stok uyarısı)
2. Profesyonel Web Sitesi Kurulumu (Modern, mobil uyumlu)
3. AI Müşteri Asistanı (7/24 otomatik cevap veren bot)

Görevin: Sana verilen işletme bilgilerini (ve varsa kazınmış web sitesi verisini) inceleyerek Rumaysoft'un bu firmaya hangi hizmeti satabileceğini belirlemek.
{'DİKKAT: BU FİRMANIN WEB SİTESİ YOK. O YÜZDEN KESİNLİKLE "web_sitesi" HİZMETİNİ ÖNER.' if not has_website else 'DİKKAT: BU FİRMANIN ZATEN BİR WEB SİTESİ VAR. O YÜZDEN "web_sitesi" DIŞINDA BİR HİZMET ÖNER (stok_takibi veya ai_asistan).'}

YANITINI SADECE AŞAĞIDAKİ GİBİ JSON FORMATINDA VER. HİÇBİR AÇIKLAMA YAZMA.
{{
  "uygunluk_skoru": 8,
  "en_uygun_hizmet": "stok_takibi", 
  "kisisellestirme_ipucu": "Web sitenizdeki menü çeşitliliği harika, stok takibi ile maliyetlerinizi çok daha iyi yönetebilirsiniz."
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

    # Kod düzeyinde kesin kural uygulaması (LLM yanılsa bile düzeltir)
    if not has_website:
        analysis["en_uygun_hizmet"] = "web_sitesi"

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
