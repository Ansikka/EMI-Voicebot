
# ap.py
import os
import sqlite3
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
import streamlit as st
from pathlib import Path
import pandas as pd
import plotly.express as px


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
    # MODIFIED: Replaced 'paid' with 'status' for more granular tracking
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
    # Fetch column names
    columns = [description[0] for description in cur.description]
    # Create list of dicts
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    return rows

def execute(q, args=()):
    cur = conn.cursor()
    cur.execute(q, args)
    conn.commit()
    return cur.lastrowid

# --- Seed demo data ---
def seed_demo():
    # small check to avoid duplicates
    existing = query_all("SELECT COUNT(*) as count FROM customers")[0]['count']
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
        "link_sent": "हमने आपके नंबर पर भुगतान लिंक भेज दिया है। धन्यवाद।",
        "rescheduled": "आपका अनुरोध नोट कर लिया गया है। एक एजेंट आपको एक नई तारीख की पुष्टि करने के लिए जल्द ही कॉल करेगा। धन्यवाद।"
    },
    "en": {
        "reminder": "Hello {name}. This is a reminder from TVS Credit. Your EMI of Rs {amount} is due. Press 1 to pay now, or press 2 to request a reschedule.",
        "link_sent": "We have sent a payment link to your phone. Thank you.",
        "rescheduled": "Your request has been noted. An agent will call you back shortly to confirm a new date. Thank you."
    },
    "ta": {
        "reminder": "வணக்கம் {name}. இது TVS Credit நினைவூட்டலாகும். உங்கள் EMI {amount} ரூபாய் நிலுவையில் உள்ளது. இப்போது செலுத்த 1 ஐ அழுத்தவும், மாற்றம் செய்ய 2 ஐ அழுத்தவும்.",
        "link_sent": "உங்கள் எண்ணுக்கான கட்டண இணைப்பு அனுப்பப்பட்டுள்ளது.",
        "rescheduled": "உங்கள் கோரிக்கை ஏற்கப்பட்டது. ஒரு முகவர் புதிய தேதியை உறுதிப்படுத்த உங்களை மீண்டும் அழைப்பார். நன்றி."
    },
    "bn": {
        "reminder": "নমস্কার {name}. এটি TVS Credit থেকে একটি রিমাইন্ডার। আপনার EMI {amount} টাকা বাকি আছে। পে করতে 1 চেপে দিন, পুনঃনির্ধারণ করতে 2 চেপে দিন।",
        "link_sent": "পেমেন্ট লিঙ্ক আপনার ফোনে পাঠানো হয়েছে। ধন্যবাদ।",
        "rescheduled": "আপনার অনুরোধ নোট করা হয়েছে। একজন এজেন্ট একটি নতুন তারিখ নিশ্চিত করতে আপনাকে শীঘ্রই আবার কল করবে। ধন্যবাদ।"
    }
}

def get_msg(lang, key, **kwargs):
    return LANG_MSGS.get(lang, LANG_MSGS["en"])[key].format(**kwargs)

# --- Core functions ---
def place_call(loan_id):
    """Place a call (real Twilio or mock) to the loan's customer"""
    loan = query_all("SELECT l.id, l.emi_amount, c.name, c.phone, c.language FROM loans l JOIN customers c ON l.customer_id = c.id WHERE l.id = ?", (loan_id,))
    if not loan:
        return {"error": "Loan not found"}
    
    loan_info = loan[0]
    text = get_msg(loan_info['language'], "reminder", name=loan_info['name'], amount=loan_info['emi_amount'])
    execute("INSERT INTO call_logs (loan_id, event, detail) VALUES (?, ?, ?)", (loan_id, "call_initiated", f"to {loan_info['phone']}"))

    if USE_TWILIO and tw_client:
        # NEW: Using <Gather> to simulate an interactive menu
        twiml = f"<Response><Gather input='dtmf' timeout='5' numDigits='1'><Say language='en-IN'>{text}</Say></Gather></Response>"
        call = tw_client.calls.create(to=loan_info['phone'], from_=TWILIO_NUMBER, twiml=twiml)
        execute("INSERT INTO call_logs (loan_id, event, detail) VALUES (?, ?, ?)", (loan_id, "twilio_call", call.sid))
        return {"status": "twilio_call_placed", "sid": call.sid}
    else:
        execute("INSERT INTO call_logs (loan_id, event, detail) VALUES (?, ?, ?)", (loan_id, "mock_call", text))
        return {"status": "mock_call_logged", "text": text}

def send_payment_link(loan_id):
    """Generate mock payment link and send via SMS."""
    loan = query_all("SELECT l.id, l.emi_amount, c.name, c.phone, c.language FROM loans l JOIN customers c ON l.customer_id = c.id WHERE l.id = ?", (loan_id,))
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
    """Mark a loan as paid. Simulates a payment gateway callback."""
    execute("UPDATE loans SET status = 'paid' WHERE id = ?", (loan_id,))
    execute("INSERT INTO call_logs (loan_id, event, detail) VALUES (?, ?, ?)", (loan_id, "marked_paid", "Webhook/Manual"))
    return {"status": "ok"}

# NEW: Function to handle rescheduling
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
st.set_page_config(page_title="EMI Genie (Demo)", layout="wide", page_icon="🤖")

st.title("EMI Genie — Multilingual VoiceBot for EMI Collections (Demo)")
st.markdown("Demo prototype: voice reminders (mock/Twilio), instant payment link (mock/Twilio SMS), logs & simple analytics.")

left, right = st.columns([2, 3])

# --- Left Panel: Controls & Actions ---
with left:
    st.header("Controls & Actions")
    
    # --- Seeding and Creation ---
    with st.expander("Seed Data & Create New Loan", expanded=False):
        if st.button("🌱 Seed Demo Customers & Loans"):
            msg = seed_demo()
            st.success(msg)

        with st.form("create_form", clear_on_submit=True):
            st.subheader("Create Customer & Loan")
            cname = st.text_input("Customer Name", value="Anshika Sharma")
            cphone = st.text_input("Phone (+91...)", value="+919999888777")
            clang = st.selectbox("Language", options=["en", "hi", "ta", "bn"], index=0)
            emi_amt = st.number_input("EMI Amount (₹)", min_value=100, value=4000, step=100)
            due = st.date_input("Due date", value=date.today())
            if st.form_submit_button("Create Loan"):
                cid = execute("INSERT INTO customers (name, phone, language) VALUES (?, ?, ?)", (cname, cphone, clang))
                loan_id = execute("INSERT INTO loans (customer_id, emi_amount, due_date) VALUES (?, ?, ?)", (cid, emi_amt, due.isoformat()))
                st.success(f"Created loan id {loan_id} for {cname}")
                st.rerun()

    st.write("---")

    # --- Bulk Actions ---
    st.header("Bulk Operations")
    if st.button("📞 Call All Overdue Loans", type="primary"):
        overdue_loans = query_all("SELECT id FROM loans WHERE due_date <= ? AND status='due'", (date.today().isoformat(),))
        if not overdue_loans:
            st.warning("No overdue loans to call.")
        else:
            progress_bar = st.progress(0, text=f"Calling {len(overdue_loans)} customers...")
            for i, loan in enumerate(overdue_loans):
                res = place_call(loan['id'])
                st.toast(f"Called loan {loan['id']}: {res.get('status', 'failed')}")
                progress_bar.progress((i + 1) / len(overdue_loans), text=f"Calling {i+1}/{len(overdue_loans)}...")
            progress_bar.empty()
            st.success(f"Finished calling all {len(overdue_loans)} overdue customers.")
            st.rerun()

    st.write("---")
    
    # --- Individual Loan Actions ---
    st.header("Individual Loan Actions")
    all_loans = query_all("SELECT l.id, c.name, l.emi_amount, l.due_date, l.status FROM loans l JOIN customers c ON l.customer_id = c.id ORDER BY l.id DESC")
    
    if not all_loans:
        st.info("No loans yet. Seed demo or create a loan.")
    else:
        # UPDATED: Selectbox label is more informative
        loan_map = {f"Loan {r['id']} | {r['name']} | ₹{r['emi_amount']} | Status: {r['status'].upper()}": r['id'] for r in all_loans}
        sel_label = st.selectbox("Pick a loan to manage", options=list(loan_map.keys()))
        sel_loan_id = loan_map[sel_label]
        
        st.write(f"**Selected:** `{sel_label}`")

        action_cols = st.columns(3)
        if action_cols[0].button("Place Voice Call", key=f"call_{sel_loan_id}"):
            with st.spinner("Placing call..."):
                res = place_call(sel_loan_id)
                if "error" in res: st.error(res["error"])
                else:
                    st.success(f"Call Action Status: `{res.get('status')}`")
                    if res.get("text"): st.code(res.get("text"), language="text")
                    st.rerun()

        if action_cols[1].button("Send Payment SMS", key=f"sms_{sel_loan_id}"):
            with st.spinner("Sending SMS..."):
                res = send_payment_link(sel_loan_id)
                if "error" in res: st.error(res["error"])
                else: 
                    st.success(f"Link sent successfully. URL: {res.get('link')}")
                    st.rerun()

        if action_cols[2].button("Mark as Paid", key=f"paid_{sel_loan_id}"):
            mark_paid(sel_loan_id)
            st.success(f"Loan {sel_loan_id} marked as PAID.")
            st.rerun()
        
        # NEW: Reschedule action
        if st.button("🗓️ Reschedule (+7 Days)", key=f"reschedule_{sel_loan_id}"):
            res = reschedule_loan(sel_loan_id)
            if "error" in res: st.error(res["error"])
            else:
                st.success(f"Loan {sel_loan_id} rescheduled. New due date: {res['new_date']}")
                st.rerun()

# --- Right Panel: Dashboard & Logs ---
with right:
    st.header("Dashboard & Logs")

    # --- Metrics & Chart ---
    status_counts = query_all("SELECT status, COUNT(*) as count FROM loans GROUP BY status")
    status_data = {item['status']: item['count'] for item in status_counts}
    
    total_loans = sum(status_data.values())
    paid_loans = status_data.get('paid', 0)
    rescheduled_loans = status_data.get('rescheduled', 0)
    overdue_loans = query_all("SELECT COUNT(*) as count FROM loans WHERE due_date <= ? AND status='due'", (date.today().isoformat(),))[0]['count']

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Loans", total_loans)
    c2.metric("✅ Paid Loans", paid_loans)
    c3.metric("🗓️ Rescheduled", rescheduled_loans)
    c4.metric("⚠️ Due/Overdue", overdue_loans, help="Loans with status 'due' and due date is today or in the past.")

    # NEW: Pie chart for visual summary
    if status_data:
        pie_df = pd.DataFrame(status_data.items(), columns=['Status', 'Count'])
        fig = px.pie(pie_df, values='Count', names='Status', title='Loan Status Distribution',
                     color_discrete_map={'paid': 'green', 'due': 'orange', 'rescheduled': 'royalblue'})
        st.plotly_chart(fig, use_container_width=True)

    st.write("---")

    # --- Data Tables ---
    tab1, tab2 = st.tabs(["📊 All Loans", "📜 Action Logs"])

    with tab1:
        st.subheader("Loans Table")
        if all_loans:
            loans_df = pd.DataFrame(all_loans)[['id', 'name', 'status', 'emi_amount', 'due_date']]
            st.dataframe(loans_df, use_container_width=True)
        else:
            st.info("No loans to display.")

    with tab2:
        st.subheader("Recent Call & Payment Logs")
        logs = query_all("SELECT id, loan_id, event, detail, ts FROM call_logs ORDER BY ts DESC LIMIT 100")
        if logs:
            st.dataframe(pd.DataFrame(logs), use_container_width=True)
        else:
            st.info("No logs yet.")

st.write("---")
st.caption("Notes: Twilio integration is optional. If you set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_PHONE_NUMBER in a .env file, the app will attempt to place real calls / send real SMS. Otherwise the app will mock those actions for demo purposes.")

