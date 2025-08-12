
# ap.py
import os
import sqlite3
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
import streamlit as st
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go 
import random
# Optional Twilio (only used if credentials set)
try:
    from twilio.rest import Client
except Exception:
    Client = None

load_dotenv()
# Twilio env vars (optional)
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")  # e.g. +91XXXXXXXXXX
USE_TWILIO = bool(TWILIO_SID and TWILIO_AUTH and TWILIO_NUMBER and Client is not None)

if USE_TWILIO:
    tw_client = Client(TWILIO_SID, TWILIO_AUTH)
else:
    tw_client = None

DB_PATH = "emi_genie_streamlit.db"

# --- Database helpers ---
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        phone TEXT,
        language TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS loans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        emi_amount INTEGER,
        due_date TEXT,
        status TEXT DEFAULT 'due' -- e.g., 'due', 'paid', 'rescheduled'
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS call_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        loan_id INTEGER,
        event TEXT,
        detail TEXT,
        ts DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    return conn

conn = init_db()

def query_all(q, args=()):
    cur = conn.cursor()
    cur.execute(q, args)
    columns = [description[0] for description in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    return rows

def execute(q, args=()):
    cur = conn.cursor()
    cur.execute(q, args)
    conn.commit()
    return cur.lastrowid

# --- Seed demo data ---
def seed_demo():
    """
    Seeds the database with a diverse set of customers and loans.
    This new version creates more data with randomized statuses and due dates
    to provide a richer demonstration.
    """
    existing = query_all("SELECT COUNT(*) as count FROM customers")[0]['count']
    if existing > 0:
        return f"Database already contains {existing} customers. To re-seed, please delete the 'emi_genie_streamlit.db' file and restart."

    # A larger, more diverse list of customers to showcase multilingual capabilities
    customers_to_seed = [
        ("Ramesh Kumar", "+919876543210", "hi"),       # Hindi
        ("Sita Devi", "+919123456789", "en"),         # English
        ("Arjun Patil", "+919888777666", "mr"),       # Marathi
        ("Priya Sharma", "+919999888777", "pa"),       # Punjabi
        ("Vikram Singh", "+919111222333", "gu"),       # Gujarati
        ("Ananya Reddy", "+919222333444", "te"),       # Telugu
        ("Fatima Begum", "+919333444555", "ur"),       # Urdu
        ("Carlos Garcia", "+34612345678", "es"),      # Spanish
        ("Sophie Dubois", "+33612345678", "fr"),      # French
        ("Kenji Tanaka", "+819012345678", "ja"),      # Japanese
        ("Maria Silva", "+5511987654321", "pt"),      # Portuguese
        ("John Smith", "+447123456789", "en")         # English
    ]
    
    total_loans_created = 0
    today = date.today()

    for name, phone, lang in customers_to_seed:
        cid = execute("INSERT INTO customers (name, phone, language) VALUES (?, ?, ?)", (name, phone, lang))
        
        # Create 1 or 2 loans for each customer for variety
        for _ in range(random.randint(1, 2)):
            # Randomly assign a status to make the dashboard more interesting
            status = random.choices(["due", "paid", "rescheduled"], weights=[0.7, 0.2, 0.1], k=1)[0]
            emi = random.randint(15, 80) * 100 # EMI between 1500 and 8000

            if status == "paid":
                # Paid loans should have a due date in the past
                due_dt = today - timedelta(days=random.randint(15, 60))
            elif status == "rescheduled":
                # Rescheduled loans should have a due date in the future
                due_dt = today + timedelta(days=random.randint(10, 25))
            else: # status is 'due'
                # 'Due' loans can be overdue, due soon, or due in the future
                # This creates targets for both "Overdue" and "Pre-Due" calls
                due_dt = today + timedelta(days=random.randint(-10, 20))

            execute("INSERT INTO loans (customer_id, emi_amount, due_date, status) VALUES (?, ?, ?, ?)",
                    (cid, emi, due_dt.isoformat(), status))
            total_loans_created += 1

    return f"✅ Seeded {len(customers_to_seed)} new customers and {total_loans_created} loans with varied statuses and due dates."

# --- Utility: language messages ---
LANG_MSGS = {
    # --- Indian Languages ---
    "en": { # English
        "reminder": "Hello {name}. This is a reminder from TVS Credit. Your EMI of Rs {amount} is due today. Press 1 to pay now, or press 2 to request a reschedule.",
        "pre_due_reminder": "Hello {name}. A friendly reminder from TVS Credit. Your EMI of Rs {amount} is due on {due_date}. Thank you.",
        "link_sent": "We have sent a payment link to your phone. Thank you.",
        "rescheduled": "Your request has been noted. An agent will call you back shortly to confirm a new date. Thank you."
    },
    "hi": { # Hindi
        "reminder": "नमस्ते {name}. TVS क्रेडिट से रिमाइंडर। आपकी EMI {amount} रुपये आज देय है। भुगतान के लिए 1 दबाएँ, पुनर्निर्धारण के लिए 2 दबाएँ।",
        "pre_due_reminder": "नमस्ते {name}. TVS क्रेडिट से एक सूचना। आपकी EMI {amount} रुपये {due_date} को देय है। धन्यवाद।",
        "link_sent": "हमने आपके नंबर पर भुगतान लिंक भेज दिया है। धन्यवाद।",
        "rescheduled": "आपका अनुरोध नोट कर लिया गया है। एक एजेंट आपको एक नई तारीख की पुष्टि करने के लिए जल्द ही कॉल करेगा। धन्यवाद।"
    },
    "bn": { # Bengali
        "reminder": "নমস্কার {name}. TVS Credit থেকে একটি রিমাইন্ডার। আপনার EMI {amount} টাকা আজ বাকি আছে। পে করতে 1 চেপে দিন, পুনঃনির্ধারণ করতে 2 চেপে দিন।",
        "pre_due_reminder": "নমস্কার {name}. TVS Credit থেকে একটি বন্ধুত্বপূর্ণ রিমাইন্ডার। আপনার EMI {amount} টাকা {due_date} তারিখে বাকি আছে। ধন্যবাদ।",
        "link_sent": "পেমেন্ট লিঙ্ক আপনার ফোনে পাঠানো হয়েছে। ধন্যবাদ।",
        "rescheduled": "আপনার অনুরোধ নোট করা হয়েছে। একজন এজেন্ট একটি নতুন তারিখ নিশ্চিত করতে আপনাকে শীঘ্রই আবার কল করবে। ধন্যবাদ।"
    },
    "ta": { # Tamil
        "reminder": "வணக்கம் {name}. TVS Credit நினைவூட்டல். உங்கள் EMI {amount} ரூபாய் இன்று செலுத்த வேண்டும். செலுத்த 1 ஐ அழுத்தவும், மாற்றம் செய்ய 2 ஐ அழுத்தவும்.",
        "pre_due_reminder": "வணக்கம் {name}. TVS Credit நினைவூட்டல். உங்கள் EMI {amount} ரூபாய் {due_date} அன்று செலுத்த வேண்டும். நன்றி.",
        "link_sent": "உங்கள் எண்ணுக்கான கட்டண இணைப்பு அனுப்பப்பட்டுள்ளது.",
        "rescheduled": "உங்கள் கோரிக்கை ஏற்கப்பட்டது. ஒரு முகவர் புதிய தேதியை உறுதிப்படுத்த உங்களை மீண்டும் அழைப்பார். நன்றி."
    },
    "te": { # Telugu
        "reminder": "నమస్కారం {name}. TVS క్రెడిట్ నుండి రిమైండర్. మీ EMI {amount} రూపాయలు ఈ రోజు చెల్లించాల్సి ఉంది. ఇప్పుడు చెల్లించడానికి 1 నొక్కండి లేదా రీషెడ్యూల్ కోసం 2 నొక్కండి.",
        "pre_due_reminder": "నమస్కారం {name}. TVS క్రెడిట్ నుండి ఒక స్నేహపూర్వక రిమైండర్. మీ EMI {amount} రూపాయలు {due_date} న చెల్లించాల్సి ఉంది. ధన్యవాదాలు.",
        "link_sent": "మేము మీ ఫోన్‌కు చెల్లింపు లింక్‌ను పంపాము. ధన్యవాదాలు.",
        "rescheduled": "మీ అభ్యర్థన నమోదు చేయబడింది. ఒక ఏజెంట్ త్వరలో కొత్త తేదీని నిర్ధారించడానికి మీకు తిరిగి కాల్ చేస్తారు. ధన్యవాదాలు."
    },
    "mr": { # Marathi
        "reminder": "नमस्कार {name}. TVS क्रेडिट कडून रिमाइंडर. तुमचा {amount} रुपयांचा EMI आज देय आहे. आता पेमेंट करण्यासाठी 1 दाबा किंवा रीशेड्यूल करण्याची विनंती करण्यासाठी 2 दाबा.",
        "pre_due_reminder": "नमस्कार {name}. TVS क्रेडिट कडून एक मैत्रीपूर्ण रिमाइंडर. तुमचा {amount} रुपयांचा EMI {due_date} रोजी देय आहे. धन्यवाद.",
        "link_sent": "आम्ही तुमच्या फोनवर पेमेंट लिंक पाठवली आहे. धन्यवाद.",
        "rescheduled": "तुमच्या विनंतीची नोंद घेतली आहे. एक एजंट लवकरच नवीन तारखेची पुष्टी करण्यासाठी तुम्हाला परत कॉल करेल. धन्यवाद."
    },
    "gu": { # Gujarati
        "reminder": "નમસ્તે {name}. TVS ક્રેડિટ તરફથી રિમાઇન્ડર. તમારી EMI {amount} રૂપિયા આજે ચૂકવવાપાત્ર છે. હમણાં ચૂકવવા માટે 1 દબાવો, અથવા ફરીથી શેડ્યૂલની વિનંતી કરવા માટે 2 દબાવો.",
        "pre_due_reminder": "નમસ્તે {name}. TVS ક્રેડિટ તરફથી એક અનૌપચારિક રિમાઇન્ડર. તમારી EMI {amount} રૂપિયા {due_date} ના રોજ ચૂકવવાપાત્ર છે. આભાર.",
        "link_sent": "અમે તમારા ફોન પર ચુકવણી લિંક મોકલી છે. આભાર.",
        "rescheduled": "તમારી વિનંતીની નોંધ લેવામાં આવી છે. એક એજન્ટ ટૂંક સમયમાં નવી તારીખની પુષ્ટિ કરવા માટે તમને પાછા કૉલ કરશે. આભાર."
    },
    "kn": { # Kannada
        "reminder": "ನಮಸ್ಕಾರ {name}. TVS ಕ್ರೆಡಿಟ್‌ನಿಂದ ಜ್ಞಾಪನೆ. ನಿಮ್ಮ EMI {amount} ರೂಪಾಯಿಗಳು ಇಂದು ಪಾವತಿಸಬೇಕಾಗಿದೆ. ಈಗ ಪಾವತಿಸಲು 1 ಒತ್ತಿರಿ, ಅಥವಾ ಮರುಹೊಂದಿಸಲು 2 ಒತ್ತಿರಿ.",
        "pre_due_reminder": "ನಮಸ್ಕಾರ {name}. TVS ಕ್ರೆಡಿಟ್‌ನಿಂದ ಸೌಹಾರ್ದಯುತ ಜ್ಞಾಪನೆ. ನಿಮ್ಮ EMI {amount} ರೂಪಾಯಿಗಳು {due_date} ರಂದು ಪಾವತಿಸಬೇಕಾಗಿದೆ. ಧನ್ಯವಾದಗಳು.",
        "link_sent": "ನಾವು ನಿಮ್ಮ ಫೋನ್‌ಗೆ ಪಾವತಿ ಲಿಂಕ್ ಕಳುಹಿಸಿದ್ದೇವೆ. ಧನ್ಯವಾದಗಳು.",
        "rescheduled": "ನಿಮ್ಮ ವಿನಂತಿಯನ್ನು નોંધಲಾಗಿದೆ. ಏಜೆಂಟ್ ಶೀಘ್ರದಲ್ಲೇ ಹೊಸ ದಿನಾಂಕವನ್ನು ಖಚಿತಪಡಿಸಲು ನಿಮಗೆ ಮರಳಿ ಕರೆ ಮಾಡುತ್ತಾರೆ. ಧನ್ಯವಾದಗಳು."
    },
    "ml": { # Malayalam
        "reminder": "നമസ്കാരം {name}. TVS ക്രെഡിറ്റിൽ നിന്നുള്ള ഒരു ഓർമ്മപ്പെടുത്തൽ. നിങ്ങളുടെ {amount} രൂപയുടെ EMI ഇന്ന് അടയ്‌ക്കേണ്ടതാണ്. ഇപ്പോൾ പണമടയ്ക്കാൻ 1 അമർത്തുക, അല്ലെങ്കിൽ പുനഃക്രമീകരിക്കാൻ 2 അമർത്തുക.",
        "pre_due_reminder": "നമസ്കാരം {name}. TVS ക്രെഡിറ്റിൽ നിന്നുള്ള ഒരു സൗഹൃദപരമായ ഓർമ്മപ്പെടുത്തൽ. നിങ്ങളുടെ {amount} രൂപയുടെ EMI {due_date} തീയതിയിൽ അടയ്‌ക്കേണ്ടതാണ്. നന്ദി.",
        "link_sent": "ഞങ്ങൾ നിങ്ങളുടെ ഫോണിലേക്ക് ഒരു പേയ്‌മെന്റ് ലിങ്ക് അയച്ചിട്ടുണ്ട്. നന്ദി.",
        "rescheduled": "നിങ്ങളുടെ അഭ്യർത്ഥന രേഖപ്പെടുത്തിയിട്ടുണ്ട്. ഒരു പുതിയ തീയതി സ്ഥിരീകരിക്കുന്നതിന് ഒരു ഏജന്റ് നിങ്ങളെ ഉടൻ തിരികെ വിളിക്കുന്നതാണ്. നന്ദി."
    },
    "pa": { # Punjabi
        "reminder": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ {name}. TVS ਕ੍ਰੈਡਿਟ ਵੱਲੋਂ ਇੱਕ ਯਾਦ-ਦਹਾਨੀ। ਤੁਹਾਡੀ {amount} ਰੁਪਏ ਦੀ EMI ਅੱਜ ਬਕਾਇਆ ਹੈ। ਹੁਣੇ ਭੁਗਤਾਨ ਕਰਨ ਲਈ 1 ਦਬਾਓ, ਜਾਂ ਮੁੜ-ਨਿਰਧਾਰਤ ਕਰਨ ਲਈ 2 ਦਬਾਓ।",
        "pre_due_reminder": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ {name}. TVS ਕ੍ਰੈਡਿਟ ਵੱਲੋਂ ਇੱਕ ਦੋਸਤਾਨਾ ਯਾਦ-ਦਹਾਨੀ। ਤੁਹਾਡੀ {amount} ਰੁਪਏ ਦੀ EMI {due_date} ਨੂੰ ਬਕਾਇਆ ਹੈ। ਧੰਨਵਾਦ।",
        "link_sent": "ਅਸੀਂ ਤੁਹਾਡੇ ਫ਼ੋਨ 'ਤੇ ਭੁਗਤਾਨ ਲਿੰਕ ਭੇਜ ਦਿੱਤਾ ਹੈ। ਧੰਨਵਾਦ।",
        "rescheduled": "ਤੁਹਾਡੀ ਬੇਨਤੀ ਨੋਟ ਕਰ ਲਈ ਗਈ ਹੈ। ਇੱਕ ਏਜੰਟ ਜਲਦੀ ਹੀ ਨਵੀਂ ਤਾਰੀਖ ਦੀ ਪੁਸ਼ਟੀ ਕਰਨ ਲਈ ਤੁਹਾਨੂੰ ਵਾਪਸ ਕਾਲ ਕਰੇਗਾ। ਧੰਨਵਾਦ।"
    },
    "or": { # Odia
        "reminder": "ନମସ୍କାର {name}। TVS କ୍ରେଡିଟ୍‌ରୁ ଏକ ସ୍ମାରକ। ଆପଣଙ୍କର {amount} ଟଙ୍କାର EMI ଆଜି ଦେୟ ଅଟେ। ବର୍ତ୍ତମାନ ପେମେଣ୍ଟ କରିବା ପାଇଁ 1 ଦବାନ୍ତୁ, କିମ୍ବା ପୁନଃ-ନିର୍ଧାରଣ ପାଇଁ 2 ଦବାନ୍ତୁ।",
        "pre_due_reminder": "ନମସ୍କାର {name}। TVS କ୍ରେଡିଟ୍‌ରୁ ଏକ ବନ୍ଧୁତ୍ୱପୂର୍ଣ୍ଣ ସ୍ମାରକ। ଆପଣଙ୍କର {amount} ଟଙ୍କାର EMI {due_date} ରେ ଦେୟ ଅଟେ। ଧନ୍ୟବାଦ।",
        "link_sent": "ଆମେ ଆପଣଙ୍କ ଫୋନକୁ ଏକ ପେମେଣ୍ଟ ଲିଙ୍କ୍ ପଠାଇଛୁ। ଧନ୍ୟବାଦ।",
        "rescheduled": "ଆପଣଙ୍କ ଅନୁରୋଧକୁ ଟିପ୍ପଣୀ କରାଯାଇଛି। ଜଣେ ଏଜେଣ୍ଟ ଶୀଘ୍ର ଏକ ନୂତନ ତାରିଖ ନିଶ୍ଚିତ କରିବାକୁ ଆପଣଙ୍କୁ ପୁନର୍ବାର କଲ୍ କରିବେ। ଧନ୍ୟବାଦ।"
    },
    "ur": { # Urdu
        "reminder": "ہیلو {name}۔ TVS کریڈٹ کی طرف سے ایک یاد دہانی۔ آپ کی {amount} روپے کی EMI آج واجب الادا ہے۔ ابھی ادائیگی کے لیے 1 دبائیں، یا دوبارہ شیڈول کرنے کی درخواست کے لیے 2 دبائیں۔",
        "pre_due_reminder": "ہیلو {name}۔ TVS کریڈٹ کی طرف سے ایک دوستانہ یاد دہانی۔ آپ کی {amount} روپے کی EMI {due_date} کو واجب الادا ہے۔ شکریہ۔",
        "link_sent": "ہم نے آپ کے فون پر ادائیگی کا لنک بھیج دیا ہے۔ شکریہ۔",
        "rescheduled": "آپ کی درخواست نوٹ کر لی گئی ہے۔ ایک ایجنٹ جلد ہی نئی تاریخ کی تصدیق کے لیے آپ کو واپس کال کرے گا۔ شکریہ۔"
    },
    
    # --- Global Languages ---
    "es": { # Spanish
        "reminder": "Hola {name}. Este es un recordatorio de TVS Credit. Su EMI de {amount} rupias vence hoy. Presione 1 para pagar ahora, o 2 para solicitar una reprogramación.",
        "pre_due_reminder": "Hola {name}. Un recordatorio amistoso de TVS Credit. Su EMI de {amount} rupias vence el {due_date}. Gracias.",
        "link_sent": "Hemos enviado un enlace de pago a su teléfono. Gracias.",
        "rescheduled": "Su solicitud ha sido registrada. Un agente le devolverá la llamada en breve para confirmar una nueva fecha. Gracias."
    },
    "fr": { # French
        "reminder": "Bonjour {name}. Ceci est un rappel de TVS Credit. Votre EMI de {amount} roupies est due aujourd'hui. Appuyez sur 1 pour payer maintenant, ou sur 2 pour demander un rééchelonnement.",
        "pre_due_reminder": "Bonjour {name}. Un rappel amical de TVS Credit. Votre EMI de {amount} roupies est due le {due_date}. Merci.",
        "link_sent": "Nous avons envoyé un lien de paiement sur votre téléphone. Merci.",
        "rescheduled": "Votre demande a été enregistrée. Un agent vous rappellera sous peu pour confirmer une nouvelle date. Merci."
    },
    "de": { # German
        "reminder": "Hallo {name}. Dies ist eine Erinnerung von TVS Credit. Ihre EMI von {amount} Rupien ist heute fällig. Drücken Sie 1, um jetzt zu zahlen, oder 2, um eine Umschuldung zu beantragen.",
        "pre_due_reminder": "Hallo {name}. Eine freundliche Erinnerung von TVS Credit. Ihre EMI von {amount} Rupien ist am {due_date} fällig. Danke.",
        "link_sent": "Wir haben einen Zahlungslink an Ihr Telefon gesendet. Danke.",
        "rescheduled": "Ihre Anfrage wurde vermerkt. Ein Mitarbeiter wird Sie in Kürze zurückrufen, um ein neues Datum zu bestätigen. Danke."
    },
    "pt": { # Portuguese
        "reminder": "Olá {name}. Este é um lembrete da TVS Credit. Sua EMI de {amount} rúpias vence hoje. Pressione 1 para pagar agora, ou 2 para solicitar um reagendamento.",
        "pre_due_reminder": "Olá {name}. Um lembrete amigável da TVS Credit. Sua EMI de {amount} rúpias vence em {due_date}. Obrigado.",
        "link_sent": "Enviamos um link de pagamento para o seu telefone. Obrigado.",
        "rescheduled": "Sua solicitação foi registrada. Um agente ligará de volta em breve para confirmar uma nova data. Obrigado."
    },
    "ru": { # Russian
        "reminder": "Здравствуйте, {name}. Это напоминание от TVS Credit. Ваш платеж EMI в размере {amount} рупий необходимо внести сегодня. Нажмите 1, чтобы оплатить сейчас, или 2, чтобы запросить перенос срока.",
        "pre_due_reminder": "Здравствуйте, {name}. Дружеское напоминание от TVS Credit. Ваш платеж EMI в размере {amount} рупий необходимо внести {due_date}. Спасибо.",
        "link_sent": "Мы отправили ссылку для оплаты на ваш телефон. Спасибо.",
        "rescheduled": "Ваш запрос был принят. Агент скоро свяжется с вами для подтверждения новой даты. Спасибо."
    },
    "zh": { # Mandarin Chinese
        "reminder": "您好 {name}。这是来自 TVS Credit 的提醒。您的 {amount} 卢比 EMI 今天到期。请按 1 立即付款，或按 2 请求重新安排。",
        "pre_due_reminder": "您好 {name}。来自 TVS Credit 的友好提醒。您的 {amount} 卢比 EMI 将于 {due_date} 到期。谢谢。",
        "link_sent": "我们已将付款链接发送到您的手机。谢谢。",
        "rescheduled": "您的请求已被记录。代理商将很快给您回电以确认新日期。谢谢。"
    },
    "ja": { # Japanese
        "reminder": "こんにちは、{name}さん。TVS Creditからのお知らせです。{amount}ルピーのEMIは本日が期日です。今すぐ支払うには1を、リスケジュールをリクエストするには2を押してください。",
        "pre_due_reminder": "こんにちは、{name}さん。TVS Creditからの丁寧なリマインダーです。{amount}ルピーのEMIは{due_date}が期日です。ありがとうございます。",
        "link_sent": "お使いの携帯電話に支払いリンクを送信しました。ありがとうございます。",
        "rescheduled": "ご要望は記録されました。担当者が後ほど新しい日付を確認するために折り返しお電話いたします。ありがとうございます。"
    },
    "ar": { # Arabic
        "reminder": "مرحباً {name}. هذا تذكير من TVS Credit. قسطك الشهري بقيمة {amount} روبية مستحق اليوم. اضغط 1 للدفع الآن، أو 2 لطلب إعادة جدولة.",
        "pre_due_reminder": "مرحباً {name}. تذكير ودي من TVS Credit. قسطك الشهري بقيمة {amount} روبية مستحق في {due_date}. شكراً لك.",
        "link_sent": "لقد أرسلنا رابط دفع إلى هاتفك. شكراً لك.",
        "rescheduled": "لقد تم تسجيل طلبك. سيعاود أحد الوكلاء الاتصال بك قريباً لتأكيد تاريخ جديد. شكراً لك."
    },
    "id": { # Indonesian
        "reminder": "Halo {name}. Ini adalah pengingat dari TVS Credit. EMI Anda sebesar {amount} rupee jatuh tempo hari ini. Tekan 1 untuk membayar sekarang, atau 2 untuk meminta penjadwalan ulang.",
        "pre_due_reminder": "Halo {name}. Pengingat ramah dari TVS Credit. EMI Anda sebesar {amount} rupee jatuh tempo pada {due_date}. Terima kasih.",
        "link_sent": "Kami telah mengirimkan tautan pembayaran ke ponsel Anda. Terima kasih.",
        "rescheduled": "Permintaan Anda telah dicatat. Seorang agen akan segera menelepon Anda kembali untuk mengkonfirmasi tanggal baru. Terima kasih."
    },
    "it": { # Italian
        "reminder": "Ciao {name}. Questo è un promemoria da TVS Credit. La tua rata EMI di {amount} rupie scade oggi. Premi 1 per pagare ora, o 2 per richiedere una riprogrammazione.",
        "pre_due_reminder": "Ciao {name}. Un promemoria amichevole da TVS Credit. La tua rata EMI di {amount} rupie scade il {due_date}. Grazie.",
        "link_sent": "Abbiamo inviato un link di pagamento al tuo telefono. Grazie.",
        "rescheduled": "La tua richiesta è stata registrata. Un agente ti richiamerà a breve per confermare una nuova data. Grazie."
    },
    "tr": { # Turkish
        "reminder": "Merhaba {name}. Bu, TVS Credit'ten bir hatırlatmadır. {amount} rupilik EMI ödemeniz bugün vadesi dolmuştur. Şimdi ödemek için 1'e, yeniden planlama talep etmek için 2'ye basın.",
        "pre_due_reminder": "Merhaba {name}. TVS Credit'ten dostça bir hatırlatma. {amount} rupilik EMI ödemenizin vadesi {due_date} tarihinde dolmaktadır. Teşekkür ederiz.",
        "link_sent": "Telefonunuza bir ödeme bağlantısı gönderdik. Teşekkür ederiz.",
        "rescheduled": "Talebiniz kaydedilmiştir. Bir temsilci yeni bir tarihi onaylamak için kısa süre içinde sizi geri arayacaktır. Teşekkür ederiz."
    },
    "nl": { # Dutch
        "reminder": "Hallo {name}. Dit is een herinnering van TVS Credit. Uw EMI van {amount} roepie vervalt vandaag. Druk op 1 om nu te betalen, of 2 om een nieuwe planning aan te vragen.",
        "pre_due_reminder": "Hallo {name}. Een vriendelijke herinnering van TVS Credit. Uw EMI van {amount} roepie vervalt op {due_date}. Dank u.",
        "link_sent": "We hebben een betalingslink naar uw telefoon gestuurd. Dank u.",
        "rescheduled": "Uw verzoek is genoteerd. Een medewerker belt u binnenkort terug om een nieuwe datum te bevestigen. Dank u."
    },
    "ko": { # Korean
        "reminder": "안녕하세요 {name}님. TVS Credit에서 알려드립니다. {amount}루피의 EMI가 오늘 마감입니다. 지금 결제하려면 1번을, 일정 변경을 요청하려면 2번을 누르십시오.",
        "pre_due_reminder": "안녕하세요 {name}님. TVS Credit의 친절한 알림입니다. {amount}루피의 EMI가 {due_date}에 마감됩니다. 감사합니다.",
        "link_sent": "결제 링크를 휴대폰으로 보내드렸습니다. 감사합니다.",
        "rescheduled": "요청이 접수되었습니다. 상담원이 곧 새로운 날짜를 확인하기 위해 다시 연락드릴 것입니다. 감사합니다."
    },
    "pl": { # Polish
        "reminder": "Witaj {name}. To jest przypomnienie od TVS Credit. Twoja rata EMI w wysokości {amount} rupii jest dzisiaj wymagalna. Naciśnij 1, aby zapłacić teraz, lub 2, aby poprosić o zmianę terminu.",
        "pre_due_reminder": "Witaj {name}. Przyjazne przypomnienie od TVS Credit. Twoja rata EMI w wysokości {amount} rupii jest wymagalna {due_date}. Dziękujemy.",
        "link_sent": "Wysłaliśmy link do płatności na Twój telefon. Dziękujemy.",
        "rescheduled": "Twoja prośba została odnotowana. Agent wkrótce oddzwoni, aby potwierdzić nową datę. Dziękujemy."
    },
    "vi": { # Vietnamese
        "reminder": "Chào {name}. Đây là lời nhắc từ TVS Credit. Khoản EMI {amount} rupee của bạn đến hạn hôm nay. Nhấn 1 để thanh toán ngay, hoặc 2 để yêu cầu sắp xếp lại lịch.",
        "pre_due_reminder": "Chào {name}. Một lời nhắc thân thiện từ TVS Credit. Khoản EMI {amount} rupee của bạn đến hạn vào ngày {due_date}. Cảm ơn bạn.",
        "link_sent": "Chúng tôi đã gửi một liên kết thanh toán đến điện thoại của bạn. Cảm ơn bạn.",
        "rescheduled": "Yêu cầu của bạn đã được ghi nhận. Một nhân viên sẽ sớm gọi lại cho bạn để xác nhận ngày mới. Cảm ơn bạn."
    },
    "fil": { # Filipino
        "reminder": "Kumusta {name}. Ito ay isang paalala mula sa TVS Credit. Ang iyong EMI na {amount} piso ay dapat bayaran ngayon. Pindutin ang 1 para magbayad ngayon, o 2 para humiling ng reschedule.",
        "pre_due_reminder": "Kumusta {name}. Isang paalala mula sa TVS Credit. Ang iyong EMI na {amount} piso ay dapat bayaran sa {due_date}. Salamat.",
        "link_sent": "Nagpadala kami ng link para sa pagbabayad sa iyong telepono. Salamat.",
        "rescheduled": "Nai-record na ang iyong kahilingan. Tatawagan ka ng isang ahente sa lalong madaling panahon para kumpirmahin ang bagong petsa. Salamat."
    }
}

def get_msg(lang, key, **kwargs):
    return LANG_MSGS.get(lang, LANG_MSGS["en"])[key].format(**kwargs)

# --- Core functions ---
def place_call(loan_id, message_key="reminder"):
    """Place a call (real Twilio or mock) to the loan's customer."""
    loan = query_all("SELECT l.id, l.emi_amount, l.due_date, c.name, c.phone, c.language FROM loans l JOIN customers c ON l.customer_id = c.id WHERE l.id = ?", (loan_id,))
    if not loan: return {"error": "Loan not found"}
    
    loan_info = loan[0]
    # Format due_date for display
    formatted_due_date = datetime.fromisoformat(loan_info['due_date']).strftime('%B %d, %Y')
    
    text = get_msg(loan_info['language'], message_key, name=loan_info['name'], amount=loan_info['emi_amount'], due_date=formatted_due_date)
    execute("INSERT INTO call_logs (loan_id, event, detail) VALUES (?, ?, ?)", (loan_id, "call_initiated", f"to {loan_info['phone']}"))

    if USE_TWILIO and tw_client:
        twiml = f"<Response><Gather input='dtmf' timeout='5' numDigits='1'><Say language='en-IN'>{text}</Say></Gather></Response>"
        call = tw_client.calls.create(to=loan_info['phone'], from_=TWILIO_NUMBER, twiml=twiml)
        execute("INSERT INTO call_logs (loan_id, event, detail) VALUES (?, ?, ?)", (loan_id, "twilio_call", call.sid))
        return {"status": "twilio_call_placed", "sid": call.sid}
    else:
        execute("INSERT INTO call_logs (loan_id, event, detail) VALUES (?, ?, ?)", (loan_id, "mock_call", text))
        return {"status": "mock_call_logged", "text": text}

def send_payment_link(loan_id):
    """Generate mock payment link and send via SMS."""
    loan = query_all("SELECT l.id, l.emi_amount, c.phone FROM loans l JOIN customers c ON l.customer_id = c.id WHERE l.id = ?", (loan_id,))
    if not loan: return {"error": "Loan not found"}
    
    loan_info = loan[0]
    payment_link = f"https://example.com/pay?loan={loan_id}&amount={loan_info['emi_amount']}"
    sms_body = f"TVS Credit: Pay your EMI of Rs {loan_info['emi_amount']}. Click {payment_link}"
    
    if USE_TWILIO and tw_client:
        msg = tw_client.messages.create(body=sms_body, from_=TWILIO_NUMBER, to=loan_info['phone'])
        detail = f"tw_sms:{msg.sid}"
    else:
        detail = f"mock_sms_sent_to_{loan_info['phone']}::{payment_link}"
    
    execute("INSERT INTO call_logs (loan_id, event, detail) VALUES (?, ?, ?)", (loan_id, "payment_link_sent", detail))
    return {"status": "payment_link_sent", "link": payment_link}

def mark_paid(loan_id):
    """Mark a loan as paid."""
    execute("UPDATE loans SET status = 'paid' WHERE id = ?", (loan_id,))
    execute("INSERT INTO call_logs (loan_id, event, detail) VALUES (?, ?, ?)", (loan_id, "marked_paid", "Webhook/Manual"))
    return {"status": "ok"}

def reschedule_loan(loan_id, days_to_add=7):
    """Reschedule a loan by updating its due date and status."""
    loan = query_all("SELECT due_date FROM loans WHERE id = ?", (loan_id,))
    if not loan: return {"error": "Loan not found"}

    current_due_date = datetime.fromisoformat(loan[0]['due_date']).date()
    new_due_date = current_due_date + timedelta(days=days_to_add)
    
    execute("UPDATE loans SET status = 'rescheduled', due_date = ? WHERE id = ?", (new_due_date.isoformat(), loan_id))
    execute("INSERT INTO call_logs (loan_id, event, detail) VALUES (?, ?, ?)", (loan_id, "rescheduled", f"New due date: {new_due_date.isoformat()}"))
    return {"status": "rescheduled", "new_date": new_due_date.isoformat()}

# --- Streamlit UI ---
st.set_page_config(page_title="TVS Credit", layout="wide", page_icon="🤖")

# NEW CODE
# NEW CODE
st.markdown("""
    <h1 style="text-align: center; font-weight:1000; font-size:2.2rem;">
        <span style="color: #1E88E5;">TVS</span> 
        <span style="color: #2E7D32;">Credit</span>
        <span style="color: #546E7A;">—</span> 
        <span style="color: #00897B;">EMI</span> 
        <span style="color: #00897B;">Agentic</span> 
        <span style="color: #00897B;">VoiceBot</span>
    </h1>
""", unsafe_allow_html=True)
st.markdown("""
    <h2 style="text-align: center; font-weight: 500; font-size: 1.5rem;">
        <span style="color: #43A047;">"A hyper-personalized, multilingual agentic voicebot designed to revolutionize EMI collections."</span>
    </h2>
    """, unsafe_allow_html=True)

left, right = st.columns([2, 3])

# --- Left Panel: Controls & Actions ---
with left:
    st.header("Controls & Actions")
    
    with st.expander("Seed Data & Create New Loan", expanded=False):
        if st.button("🌱 Seed Demo Data"):
            st.success(seed_demo())
            st.rerun()

        with st.form("create_form", clear_on_submit=True):
            st.subheader("Create New Loan")
            cname = st.text_input("Customer Name", value="Rahul junkar")
            cphone = st.text_input("Phone (+91...)", value="+919999888777")
            clang = st.selectbox("Language", options=["en", "hi", "ta", "bn"], index=0)
            emi_amt = st.number_input("EMI Amount (₹)", min_value=100, value=4000, step=100)
            due = st.date_input("Due date", value=date.today() + timedelta(days=3))
            if st.form_submit_button("Create Loan"):
                cid = execute("INSERT INTO customers (name, phone, language) VALUES (?, ?, ?)", (cname, cphone, clang))
                loan_id = execute("INSERT INTO loans (customer_id, emi_amount, due_date) VALUES (?, ?, ?)", (cid, emi_amt, due.isoformat()))
                st.success(f"Created loan id {loan_id} for {cname}")
                st.rerun()

    st.write("---")

    # --- Bulk Actions ---
    st.header("Proactive Bulk Operations")
    b_cols = st.columns(2)
    
    # NEW: Button for Pre-Due Reminders
    with b_cols[0]:
        if st.button("📞 Call Pre-Due Customers"):
            pre_due_date = (date.today() + timedelta(days=3)).isoformat()
            target_loans = query_all("SELECT id FROM loans WHERE due_date = ? AND status='due'", (pre_due_date,))
            if not target_loans:
                st.warning("No customers with EMIs due in 3 days.")
            else:
                progress_bar = st.progress(0, text=f"Calling {len(target_loans)} pre-due customers...")
                for i, loan in enumerate(target_loans):
                    place_call(loan['id'], message_key="pre_due_reminder")
                    st.toast(f"Called loan {loan['id']} (pre-due reminder)")
                    progress_bar.progress((i + 1) / len(target_loans), text=f"Calling {i+1}/{len(target_loans)}...")
                progress_bar.empty()
                st.success(f"Finished calling all {len(target_loans)} pre-due customers.")

    with b_cols[1]:
        if st.button("🚨 Call Overdue Customers", type="primary"):
            overdue_loans = query_all("SELECT id FROM loans WHERE due_date <= ? AND status='due'", (date.today().isoformat(),))
            if not overdue_loans:
                st.warning("No overdue loans to call.")
            else:
                progress_bar = st.progress(0, text=f"Calling {len(overdue_loans)} overdue customers...")
                for i, loan in enumerate(overdue_loans):
                    place_call(loan['id']) # Default message_key is 'reminder'
                    st.toast(f"Called loan {loan['id']} (overdue)")
                    progress_bar.progress((i + 1) / len(overdue_loans), text=f"Calling {i+1}/{len(overdue_loans)}...")
                progress_bar.empty()
                st.success(f"Finished calling all {len(overdue_loans)} overdue customers.")

    st.write("---")
    
    # --- Individual Loan Actions ---
    st.header("Individual Loan Actions")
    all_loans = query_all("SELECT l.id, c.name, l.emi_amount, l.due_date, l.status FROM loans l JOIN customers c ON l.customer_id = c.id ORDER BY l.due_date ASC")
    
    if not all_loans:
        st.info("No loans yet. Seed demo or create a loan.")
    else:
        loan_map = {f"Loan {r['id']} | {r['name']} | Status: {r['status'].upper()} | Due: {r['due_date']}": r['id'] for r in all_loans}
        sel_label = st.selectbox("Pick a loan to manage", options=list(loan_map.keys()))
        sel_loan_id = loan_map[sel_label]
        
        st.write(f"**Selected:** `{sel_label}`")

        action_cols = st.columns(3)
        if action_cols[0].button("Place Voice Call", key=f"call_{sel_loan_id}"):
            with st.spinner("Placing call..."):
                res = place_call(sel_loan_id)
                st.success(f"Call Action Status: `{res.get('status')}`")
                if res.get("text"): st.code(res.get("text"), language="text")
        
        if action_cols[1].button("Send Payment SMS", key=f"sms_{sel_loan_id}"):
            with st.spinner("Sending SMS..."):
                res = send_payment_link(sel_loan_id)
                st.success(f"Link sent successfully. URL: {res.get('link')}")

        if action_cols[2].button("Mark as Paid", key=f"paid_{sel_loan_id}"):
            mark_paid(sel_loan_id)
            st.success(f"Loan {sel_loan_id} marked as PAID.")
            st.rerun()
        
        if st.button("🗓️ Reschedule (+7 Days)", key=f"reschedule_{sel_loan_id}"):
            res = reschedule_loan(sel_loan_id)
            st.success(f"Loan {sel_loan_id} rescheduled. New due date: {res['new_date']}")
            st.rerun()

# --- Right Panel: Dashboard & Logs ---
# --- Dashboard Sidebar Filters ---

# --- Dashboard Sidebar Filters ---
st.sidebar.header("🔍 Dashboard Filters")

# Fetch data once for filter options
initial_df = pd.DataFrame(query_all("SELECT l.status, c.language FROM loans l JOIN customers c ON l.customer_id = c.id"))

if not initial_df.empty:
    status_options = initial_df['status'].unique().tolist()
    lang_options = initial_df['language'].unique().tolist()

    selected_status = st.sidebar.multiselect("Filter by Status", options=status_options, default=status_options)
    selected_lang = st.sidebar.multiselect("Filter by Language", options=lang_options, default=lang_options)
    
    start_date_filter = st.sidebar.date_input("Start Date", date.today() - timedelta(days=90))
    end_date_filter = st.sidebar.date_input("End Date", date.today() + timedelta(days=30))
else:
    st.sidebar.warning("No data to filter.")
    selected_status, selected_lang, start_date_filter, end_date_filter = [], [], date.today(), date.today()

# --- Right Panel: Dashboard & Logs ---
with right:
    st.header("🚀 Advanced Analytics Dashboard")
    st.markdown(f"_Data as of: {datetime.now().strftime('%B %d, %Y, %I:%M %p')} (IST)_")

    # --- Filter Data based on Sidebar ---
    all_loans_data = query_all("""
        SELECT l.id, c.name, l.status, l.emi_amount, l.due_date, c.language
        FROM loans l JOIN customers c ON l.customer_id = c.id
    """)

    if not all_loans_data:
        st.warning("No loan data available. Please seed the database first.")
    else:
        df = pd.DataFrame(all_loans_data)
        df['due_date'] = pd.to_datetime(df['due_date']).dt.date

        # Apply filters
        df_filtered = df[
            (df['status'].isin(selected_status)) &
            (df['language'].isin(selected_lang)) &
            (df['due_date'] >= start_date_filter) &
            (df['due_date'] <= end_date_filter)
        ]
        
        st.markdown(f"#### Showing **{len(df_filtered)}** of **{len(df)}** total loans")
        st.write("---")

        # --- NEW: Performance Metrics Section ---
        with st.container(border=True):
            st.markdown("#### 📞 Call Effectiveness Metrics")
            
            # Query call and payment logs for analysis
            call_logs = pd.DataFrame(query_all("SELECT loan_id, ts FROM call_logs WHERE event = 'call_initiated'"))
            paid_logs = pd.DataFrame(query_all("SELECT loan_id, ts FROM call_logs WHERE event = 'marked_paid'"))

            if not call_logs.empty and not paid_logs.empty:
                call_logs['ts'] = pd.to_datetime(call_logs['ts'])
                paid_logs['ts'] = pd.to_datetime(paid_logs['ts'])
                
                # Find the first call and first payment for each loan
                first_calls = call_logs.loc[call_logs.groupby('loan_id')['ts'].idxmin()]
                first_payments = paid_logs.loc[paid_logs.groupby('loan_id')['ts'].idxmin()]

                # Merge to find time difference
                merged_logs = pd.merge(first_calls, first_payments, on='loan_id', suffixes=('_call', '_paid'))
                merged_logs['time_to_pay'] = merged_logs['ts_paid'] - merged_logs['ts_call']

                # Filter for payments made within 48 hours of a call
                successful_conversions = merged_logs[merged_logs['time_to_pay'] <= timedelta(hours=48)]
                
                conversion_rate = (len(successful_conversions) / len(first_calls)) * 100 if not first_calls.empty else 0
                avg_time_to_pay = successful_conversions['time_to_pay'].mean() if not successful_conversions.empty else timedelta(0)
                
                # Convert timedelta to a readable string H:M:S
                hours, remainder = divmod(avg_time_to_pay.total_seconds(), 3600)
                minutes, seconds = divmod(remainder, 60)
                avg_time_str = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"

                perf_cols = st.columns(2)
                perf_cols[0].metric(
                    "Overdue-to-Paid Conversion (48h)",
                    f"{conversion_rate:.1f}%",
                    help="Percentage of loans that were paid within 48 hours of receiving a voice call."
                )
                perf_cols[1].metric(
                    "Avg. Time to Pay (Post-Call)",
                    avg_time_str,
                    help="For successfully converted loans, the average time from call to payment."
                )
            else:
                st.info("Insufficient log data for effectiveness analysis.")

        # --- KPIs and Charts ---
        col1, col2 = st.columns(2)
        with col1:
            with st.container(border=True):
                 st.markdown("##### Status Distribution")
                 if not df_filtered.empty:
                    status_counts = df_filtered['status'].value_counts().reset_index()
                    fig_pie = px.pie(status_counts, values='count', names='status', hole=0.4,
                                     color='status',
                                     color_discrete_map={'paid': '#2ca02c', 'due': '#ff7f0e', 'rescheduled': '#1f77b4'})
                    fig_pie.update_layout(height=300, margin=dict(l=20, r=20, t=30, b=20))
                    st.plotly_chart(fig_pie, use_container_width=True)
                 else:
                     st.info("No data for the selected filters.")
        with col2:
            with st.container(border=True):
                st.markdown("##### Loan Distribution by Language")
                if not df_filtered.empty:
                    lang_counts = df_filtered['language'].value_counts().nlargest(10).reset_index()
                    fig_bar = px.bar(lang_counts, y='language', x='count', orientation='h', text_auto=True)
                    fig_bar.update_layout(height=300, margin=dict(l=20, r=20, t=30, b=20),
                                          yaxis={'categoryorder':'total ascending', 'title': ''},
                                          xaxis={'title': ''})
                    st.plotly_chart(fig_bar, use_container_width=True)
                else:
                    st.info("No data for the selected filters.")

        # --- Data Tables with Conditional Formatting ---
        st.markdown("#### 🗂️ Detailed Loan Data (Filtered)")
        
        def style_loan_table(df_to_style):
            def style_status(row):
                style = [''] * len(row)
                today = date(2025, 8, 12)
                if row.status == 'paid':
                    style = ['background-color: #d4edda; color: #155724'] * len(row)
                elif row.status == 'rescheduled':
                    style = ['background-color: #cce5ff; color: #004085'] * len(row)
                elif row.status == 'due' and row.due_date < today:
                     style = ['background-color: #f8d7da; color: #721c24'] * len(row)
                elif row.status == 'due':
                     style = ['background-color: #fff3cd; color: #856404'] * len(row)
                return style
            return df_to_style.style.apply(style_status, axis=1)

        display_df = df_filtered[['id', 'name', 'status', 'emi_amount', 'due_date', 'language']].copy()
        display_df['emi_amount'] = display_df['emi_amount'].apply(lambda x: f"₹{x:,.0f}")
        styled_df = style_loan_table(display_df)
        st.dataframe(styled_df, use_container_width=True, hide_index=True)
