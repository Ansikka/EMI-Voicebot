# ap.py
import os
import sqlite3
from datetime import datetime, date
from dotenv import load_dotenv
import streamlit as st
from pathlib import Path

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
        paid INTEGER DEFAULT 0
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
    rows = cur.fetchall()
    return rows

def execute(q, args=()):
    cur = conn.cursor()
    cur.execute(q, args)
    conn.commit()
    return cur.lastrowid

# --- Seed demo data ---
def seed_demo():
    # small check to avoid duplicates
    existing = query_all("SELECT COUNT(*) FROM customers")[0][0]
    if existing > 0:
        return "Already seeded"
    # Add 4 demo customers across languages/regions
    customers = [
        ("Ramesh Kumar", "+919876543210", "hi"),
        ("Sita Devi", "+919123456789", "en"),
        ("Rajesh Kumar", "+919888777666", "bn"),
        ("Karthik", "+919999888777", "ta"),
    ]
    for name, phone, lang in customers:
        cid = execute("INSERT INTO customers (name, phone, language) VALUES (?, ?, ?)", (name, phone, lang))
        # add loan with upcoming due date
        execute("INSERT INTO loans (customer_id, emi_amount, due_date) VALUES (?, ?, ?)",
                (cid, 4000, (date.today()).isoformat()))
    return "Seeded demo customers and loans."

# --- Utility: language messages ---
LANG_MSGS = {
    "hi": {
        "reminder": "नमस्ते {name}. यह TVS क्रेडिट से रिमाइंडर है। आपकी अगली EMI {amount} रुपये है। भुगतान के लिए 1 दबाएँ, पुनर्निर्धारण के लिए 2 दबाएँ.",
        "link_sent": "हमने आपके नंबर पर भुगतान लिंक भेज दिया है। धन्यवाद।"
    },
    "en": {
        "reminder": "Hello {name}. This is a reminder from TVS Credit. Your EMI of Rs {amount} is due. Press 1 to pay now, 2 to reschedule.",
        "link_sent": "We have sent a payment link to your phone. Thank you."
    },
    "ta": {
        "reminder": "வணக்கம் {name}. இது TVS Credit நினைவூட்டலாகும். உங்கள் EMI {amount} ரூபாய் நிலுவையில் உள்ளது. இப்போது செலுத்த 1 ஐ அழுத்தவும், மாற்றம் செய் 2 ஐ அழுத்தவும்.",
        "link_sent": "உங்கள் எண்ணுக்கான கட்டண இணைப்பு அனுப்பப்பட்டுள்ளது."
    },
    "bn": {
        "reminder": "নমস্কার {name}. এটি TVS Credit থেকে একটি রিমাইন্ডার। আপনার EMI {amount} টাকা বাকি আছে। পে করতে 1 চেপে দিন, পুনঃনির্ধারণ করতে 2 চেপে দিন।",
        "link_sent": "পেমেন্ট লিঙ্ক আপনার ফোনে পাঠানো হয়েছে। ধন্যবাদ।"
    }
}

# Fallback mapping
def get_msg(lang, key, **kwargs):
    if lang in LANG_MSGS:
        return LANG_MSGS[lang][key].format(**kwargs)
    return LANG_MSGS["en"][key].format(**kwargs)

# --- Core functions ---
def place_call(loan_id):
    """Place a call (real Twilio or mock) to the loan's customer"""
    loan = query_all("SELECT loans.id, loans.emi_amount, loans.due_date, customers.name, customers.phone, customers.language FROM loans JOIN customers ON loans.customer_id = customers.id WHERE loans.id = ?", (loan_id,))
    if not loan:
        return {"error": "Loan not found"}
    loan = loan[0]
    _, emi_amount, due_date, name, phone, lang = loan
    text = get_msg(lang, "reminder", name=name, amount=emi_amount)
    # Log call started
    execute("INSERT INTO call_logs (loan_id, event, detail) VALUES (?, ?, ?)", (loan_id, "call_initiated", f"to {phone}"))
    if USE_TWILIO and tw_client:
        # Create a call using TwiML in the call creation
        # Note: Using twiml param to avoid external webhook; simple TTS only
        twiml = f"<Response><Say language='en'>{text}</Say></Response>"
        call = tw_client.calls.create(to=phone, from_=TWILIO_NUMBER, twiml=twiml)
        execute("INSERT INTO call_logs (loan_id, event, detail) VALUES (?, ?, ?)", (loan_id, "twilio_call", call.sid))
        return {"status": "twilio_call_placed", "sid": call.sid}
    else:
        # Mock: store the TTS text in log and return simulated call id
        execute("INSERT INTO call_logs (loan_id, event, detail) VALUES (?, ?, ?)", (loan_id, "mock_call", text))
        return {"status": "mock_call_logged", "text": text}

def send_payment_link(loan_id):
    """Generate (mock) payment link, send via SMS (Twilio optional), and log."""
    loan = query_all("SELECT loans.id, loans.emi_amount, customers.name, customers.phone, customers.language FROM loans JOIN customers ON loans.customer_id = customers.id WHERE loans.id = ?", (loan_id,))
    if not loan:
        return {"error": "Loan not found"}
    loan = loan[0]
    _, emi_amount, name, phone, lang = loan
    # Mock payment link
    # In production, generate secure link from payment gateway (Razorpay/PayU)
    payment_link = f"https://example.com/pay?loan={loan_id}&amount={emi_amount}"
    detail = f"link:{payment_link}"
    if USE_TWILIO and tw_client:
        msg = tw_client.messages.create(body=f"TVS Credit: Pay your EMI of Rs {emi_amount}. Click {payment_link}", from_=TWILIO_NUMBER, to=phone)
        detail = f"tw_sms:{msg.sid}"
    else:
        detail = f"mock_sms_sent_to_{phone}::{payment_link}"
    execute("INSERT INTO call_logs (loan_id, event, detail) VALUES (?, ?, ?)", (loan_id, "payment_link_sent", detail))
    return {"status": "payment_link_sent", "link": payment_link}

def mark_paid(loan_id):
    execute("UPDATE loans SET paid = 1 WHERE id = ?", (loan_id,))
    execute("INSERT INTO call_logs (loan_id, event, detail) VALUES (?, ?, ?)", (loan_id, "marked_paid", "manual_mark"))
    return {"status": "ok"}

# --- Streamlit UI ---
st.set_page_config(page_title="EMI Genie (Demo)", layout="wide", page_icon="🤖")

st.title("EMI Genie — Multilingual VoiceBot for EMI Collections (Demo)")
st.markdown(
    "Demo prototype: voice reminders (mock/Twilio), instant payment link (mock/Twilio SMS), logs & simple analytics."
)

# Left panel: Actions
left, right = st.columns([2, 3])

with left:
    st.header("Quick Actions")
    if st.button("Seed demo customers & loans"):
        msg = seed_demo()
        st.success(msg)

    st.write("---")
    st.subheader("Create Customer & Loan")
    with st.form("create_form", clear_on_submit=True):
        cname = st.text_input("Customer Name", value="Anshika Sharma")
        cphone = st.text_input("Phone (+91...)", value="+919999888777")
        clang = st.selectbox("Language", options=["en", "hi", "ta", "bn"], index=0)
        emi_amt = st.number_input("EMI Amount (₹)", min_value=100, value=4000, step=100)
        due = st.date_input("Due date", value=date.today())
        submit = st.form_submit_button("Create")
        if submit:
            cid = execute("INSERT INTO customers (name, phone, language) VALUES (?, ?, ?)", (cname, cphone, clang))
            loan_id = execute("INSERT INTO loans (customer_id, emi_amount, due_date) VALUES (?, ?, ?)", (cid, emi_amt, due.isoformat()))
            st.success(f"Created loan id {loan_id} for {cname}")

    st.write("---")
    st.subheader("Select Loan for Actions")
    loans = query_all("SELECT loans.id, customers.name, customers.phone, loans.emi_amount, loans.due_date, loans.paid FROM loans JOIN customers ON loans.customer_id = customers.id")
    if not loans:
        st.info("No loans yet. Seed demo or create a loan.")
    else:
        loan_map = {f"Loan {r[0]} | {r[1]} | ₹{r[3]} | Due {r[4]} | Paid:{r[5]}": r[0] for r in loans}
        sel_label = st.selectbox("Pick a loan", options=list(loan_map.keys()))
        sel_loan_id = loan_map[sel_label]
        st.write("Selected:", sel_label)

        # Buttons for actions
        if st.button("Place Voice Reminder (Call)"):
            res = place_call(sel_loan_id)
            if res.get("status"):
                st.success(f"Call action: {res.get('status')}")
                if res.get("text"):
                    st.code(res.get("text"))
            else:
                st.error(res.get("error", "Unknown"))

        if st.button("Send Payment Link (SMS)"):
            res = send_payment_link(sel_loan_id)
            if res.get("status"):
                st.success("Payment link sent.")
                st.write(res.get("link"))
            else:
                st.error(res.get("error"))

        if st.button("Mark Paid (simulate gateway callback)"):
            res = mark_paid(sel_loan_id)
            st.success("Loan marked paid.")

with right:
    st.header("Dashboard & Logs")

    # show summary
    total_loans = query_all("SELECT COUNT(*) FROM loans")[0][0]
    paid_loans = query_all("SELECT COUNT(*) FROM loans WHERE paid=1")[0][0]
    overdue = query_all("SELECT COUNT(*) FROM loans WHERE due_date <= ? AND paid=0", (date.today().isoformat(),))[0][0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Loans", total_loans)
    c2.metric("Paid Loans", paid_loans)
    c3.metric("Due Today/Overdue", overdue)

    st.write("---")
    st.subheader("Recent Call & Payment Logs")
    logs = query_all("SELECT id, loan_id, event, detail, ts FROM call_logs ORDER BY ts DESC LIMIT 50")
    if logs:
        import pandas as pd
        df = pd.DataFrame(logs, columns=["id", "loan_id", "event", "detail", "ts"])
        st.dataframe(df)
    else:
        st.info("No logs yet.")

    st.write("---")
    st.subheader("Loans Table")
    import pandas as pd
    loans_df = pd.DataFrame(loans, columns=["id", "name", "phone", "emi", "due_date", "paid"])
    st.dataframe(loans_df)

st.write("---")
st.caption("Notes: Twilio integration is optional. If you set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_PHONE_NUMBER in a .env file, the app will attempt to place real calls / send real SMS. Otherwise the app will mock those actions for demo purposes.")

