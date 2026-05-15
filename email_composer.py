"""
Email Composer — Kişiselleştirilmiş B2B E-posta Hazırlama
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AI tarafından analiz edilen firmalara özel, doğal ve ikna edici 
satış / tanışma mailleri üretir.
"""
import logging
from typing import List, Dict

from lead_analyzer import _call_llm

logger = logging.getLogger(__name__)

# Temel Mail Şablonları (LLM başarısız olursa kullanılacak Fallback)
FALLBACK_TEMPLATES = {
    "stok_takibi": """Merhaba {yetkili_adi},

Nasılsınız? Ben Ahmet, Rumaysoft'tan ulaşıyorum. İzmir bölgesindeki değerli işletmeleri incelerken firmanız {business_name} dikkatimi çekti. {kisisellestirme}

Günümüzde işletmelerin en büyük zorluklarından biri stoklarını ve siparişlerini manuel olarak takip etmek. Rumaysoft olarak geliştirdiğimiz Akıllı Stok Takip Otomasyonu ile bu süreci tamamen dijitalleştiriyor, stok azaldığında size haber veren ve siparişleri otomatik düzenleyen bir sistem kuruyoruz.

Bu sayede zamandan tasarruf edip doğrudan satışlara odaklanabiliyorsunuz. Konu hakkında detaylı bilgi almak ve sistemin size nasıl fayda sağlayacağını görüşmek isterseniz, kısa bir telefon görüşmesi ayarlayabilir miyiz?

İyi çalışmalar dilerim.

Ahmet
Rumaysoft Ekibi
0553 705 8337
rumaysoft.com""",

    "web_sitesi": """Merhaba {yetkili_adi},

Nasılsınız? Ben Ahmet, Rumaysoft'tan yazıyorum. {business_name} markanızı internette ararken fark ettim. {kisisellestirme}

Müşterilerinizin çoğu sizi dijital dünyada arıyor ancak etkili bir web siteniz olmadığını gördük. Rumaysoft olarak yerel işletmeler için çok uygun fiyatlara mobil uyumlu, modern ve satış getiren web siteleri kuruyoruz.

Sadece 1 hafta içinde tüm dijital varlığınızı profesyonel bir seviyeye taşıyabiliriz. Dilerseniz size örnek çalışmalarımızı iletebilir veya kısa bir görüşme yapabiliriz. 

Geri dönüşünüzü bekliyorum, iyi çalışmalar.

Ahmet
Rumaysoft Ekibi
0553 705 8337
rumaysoft.com""",

    "ai_asistan": """Merhaba {yetkili_adi},

Umarım harika bir gün geçiriyorsunuzdur. Ben Ahmet, Rumaysoft ekibinden ulaşıyorum. {business_name} işletmenizin müşteri iletişimini incelerken size çok fayda sağlayacak bir çözümümüz olduğunu düşündüm. {kisisellestirme}

Müşterilerinizden gelen mesajlara 7/24 anında yanıt verebilen, randevu alabilen ve bilgi sağlayan "Yapay Zeka Müşteri Asistanı" kuruyoruz. Bu sistem sayesinde hiçbir müşteriyi kaçırmıyor, mesajlara cevap verme yükünden tamamen kurtuluyorsunuz.

Bu sistemi WhatsApp veya Instagram'ınıza entegre etmemiz çok kolay. Sistemin nasıl çalıştığını görmek isterseniz kısa bir demo yapabilir miyiz?

Haberlerinizi bekliyorum.

Ahmet
Rumaysoft Ekibi
0553 705 8337
rumaysoft.com""",

    "klinik_ai_asistan": """Merhaba {yetkili_adi},

Nasılsınız? Ben Ahmet, Rumaysoft'tan ulaşıyorum. {business_name} kliniğinizi incelerken aklıma hemen sizin için çalışabilecek bir fikir geldi. {kisisellestirme}

Birçok özel klinik, hasta sorularını ve randevu taleplerini yönetmek için çok zaman harcıyor. Geliştirdiğimiz "Yapay Zeka Hasta Asistanı" sistemi sayesinde WhatsApp ve Instagram üzerinden gelen hasta mesajlarına 7/24 anında yanıt veriliyor; randevular otomatik olarak sisteme işleniyor.

Doktorlarınız ve personelleriniz sadece gerçekten önemli işlere odaklanabiliyor, boş mesajlara cevap verme yüküyle uğraşmak zorunda kalmıyor. İstediğinizde hasta sizi değil, asistanınız sizi buluyor.

10 dakikalık kısa bir görüşme ile sistemi canlı gösterebilirim — uygun bir zamanınız var mı?

İyi çalışmalar.

Ahmet
Rumaysoft Ekibi
0553 705 8337
rumaysoft.com""",

    "guzellik_ai_asistan": """Merhaba {yetkili_adi},

Umarım güzel bir gün geçiriyorsunuzdur. Ben Ahmet, Rumaysoft'tan yazıyorum. {business_name}'i gezerken aklıma hemen sizi düşündürdü. {kisisellestirme}

Güzellik ve kuaför sektöründe en büyük zorluk, randevu mesajlarını takip etmek ve her müşteriye hızlı dönmek. Özellikle yoğun günlerde bazı mesajlar gözden kaçabiliyor.

Geliştirdiğimiz "Yapay Zeka Randevu Asistanı" ile WhatsApp veya Instagram üzerinden gelen tüm mesajlar anında cevaplanıyor, randevular otomatik alınıyor. Müşterileriniz sizi hiç beklemeden randevu alabilir, siz ise işinize odaklanabilirsiniz.

Kısa bir demo için uygun bir zamanınız var mı?

Sevgiler,

Ahmet
Rumaysoft Ekibi
0553 705 8337
rumaysoft.com"""
}

def generate_email_content(lead: Dict) -> Dict:
    """Bir firma için kişiselleştirilmiş mail konusunu ve içeriğini üretir."""

    business_name = lead.get("business_name", "İşletme Yetkilisi")
    service = lead.get("best_service", "ai_asistan")
    hint = lead.get("personalization_hint", f"{business_name} için dijital süreçlerinizi hızlandırmak isteriz.")
    segment = lead.get("segment", "")

    # Segment'e göre mail tonunu belirle
    if segment == "klinik":
        segment_context = ("Bu işletme bir ÖZEL KLİNİK (diş, dermatoloji, çocuk sağlığı vb.). "
                           "Mail tonu profesyonel ama sıcak olsun. Hasta iletişimi ve randevu yönetimine odaklan. "
                           "CTA: kısa bir görüşme veya demo talebi.")
    elif segment == "guzellik":
        segment_context = ("Bu işletme bir GÜZELLIK/KUAFÖR merkezi veya tırnak bakım salonu. "
                           "Mail tonu daha samimi ve enerjik olsun. Randevu takibi ve müşteri mesajlarına odaklan. "
                           "CTA: kısa bir demo talebi.")
    else:
        segment_context = "Genel bir işletme. Doğal ve samimi bir dil kullan."

    system_prompt = f"""Sen Rumaysoft şirketinin uzman B2B metin yazarısın. İzmir'deki işletmelere doğal, sıcak ve samimi "soğuk e-postalar" (cold email) yazıyorsun.
Asla "Sayın Yetkili", "Saygılarımla" gibi çok resmi ve robotik/spam kokan ifadeler KULLANMA. "Merhaba", "Nasılsınız?", "İyi çalışmalar" gibi daha insan gibi konuş.

Segment Bilgisi: {segment_context}

Görevin: Verilen firma bilgisi ve kişiselleştirme ipucunu kullanarak, satılması hedeflenen hizmete uygun bir mail yazmak.
Kısa tut (maksimum 4-5 paragraf). Satış yapmaya çalışma, sadece merak uyandırıp görüşme talep et.
Kendini "Ahmet, Rumaysoft ekibinden" olarak tanıt. Mailin sonuna şu imza bloğunu mutlaka ekle:
Ahmet
Rumaysoft Ekibi
0553 705 8337
rumaysoft.com

Ek Olarak: Mailin uygun bir yerine, Rumaysoft'un diğer hizmetlerinden (Modern Web Tasarımı, AI Satış Asistanları, Özel CRM ve Yazılım Çözümleri, İş Otomasyonları) doğal bir cümleyle bahset.

YANITINI SADECE AŞAĞIDAKİ FORMATTA VER:

SUBJECT: [Mail Konusu - Dikkat çekici ama spam olmayan, emojili olabilir]
BODY:
[Mailin tam metni burada olacak. Boşluklar ve paragraflar dahil.]
"""

    prompt = f"""Firma Adı: {business_name}
Segment: {segment if segment else "genel"}
Satılacak Hizmet: {service.replace('_', ' ').title()}
Kişiselleştirme İpucu: {hint}

Lütfen yukarıdaki kurallara göre maili hazırla."""

    response = _call_llm(prompt, system_prompt)
    
    email_data = {
        "subject": "",
        "body": ""
    }
    
    if response and "SUBJECT:" in response and "BODY:" in response:
        try:
            parts = response.split("BODY:")
            email_data["subject"] = parts[0].replace("SUBJECT:", "").strip()
            email_data["body"] = parts[1].strip()
            return email_data
        except Exception as e:
            logger.warning(f"⚠️ LLM mail ayrıştırma hatası: {e}")
            
    # Fallback (API yoksa veya hata olursa)
    # Segment'e özel template önceliklidir
    if segment == "klinik":
        template_key = "klinik_ai_asistan"
        subject_default = f"🏥 {business_name} — Hasta İletişimini Kolaylaştıralım"
    elif segment == "guzellik":
        template_key = "guzellik_ai_asistan"
        subject_default = f"✨ {business_name} — Randevu Takibinizi Otomatikleştirelim"
    else:
        template_key = service
        subject_default = f"👋 {business_name} için Dijital Çözüm Önerisi"

    logger.info(f"  Fallback mail şablonu kullanılıyor ({template_key}).")
    template = FALLBACK_TEMPLATES.get(template_key, FALLBACK_TEMPLATES["ai_asistan"])
    body = template.format(
        yetkili_adi=business_name,
        business_name=business_name,
        kisisellestirme=hint
    )

    email_data["subject"] = subject_default
    email_data["body"] = body

    return email_data

def compose_emails(analyzed_leads: List[Dict]) -> List[Dict]:
    """Tüm lead'ler için mail metinlerini hazırlar."""
    logger.info(f"✍️ {len(analyzed_leads)} firma için kişiselleştirilmiş mail hazırlanıyor...")
    
    for i, lead in enumerate(analyzed_leads):
        name = lead.get("business_name", "?")
        logger.info(f"  [{i+1}/{len(analyzed_leads)}] Mail yazılıyor: {name}")
        
        email_content = generate_email_content(lead)
        lead["email_subject"] = email_content["subject"]
        lead["email_body"] = email_content["body"]
        
    logger.info("✅ Tüm maillerin yazımı tamamlandı.")
    return analyzed_leads

if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    
    test_lead = {
        "business_name": "Telve Cafe",
        "email": "info@telvecofe.com",
        "best_service": "stok_takibi",
        "personalization_hint": "Instagram hesabınızda yeni kahve çeşitlerinizi gördüm, ürün stoklarınızı takip etmek zorlaşıyor olabilir."
    }
    
    res = compose_emails([test_lead])
    print(f"\nKONU: {res[0]['email_subject']}\n")
    print(res[0]['email_body'])
