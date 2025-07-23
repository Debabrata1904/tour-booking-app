import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, date
import pandas as pd
from fpdf import FPDF
import base64
import tempfile
import smtplib
from email.message import EmailMessage
import qrcode
import os
import json

# ---- Password Protection ----
def login():
    st.title("🔐 Indian Express Tour Login")
    password = st.text_input("Enter Access Password", type="password")
    if password == "indianexpress2025":
        st.success("✅ Access Granted")
        return True
    elif password != "":
        st.error("❌ Wrong password.")
        return False
    return False

if not login():
    st.stop()

# ---- Destination Codes ----
destination_codes = {
    "Sundarban": "01",
    "Digha": "02",
    "Puri": "03",
    "Darjeeling": "04",
    "Purulia": "05"
}

# ---- Google Sheets Setup via Secrets ----
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["GOOGLE_SHEETS_CREDENTIALS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1bSh0QHlZWo30Nxm9TSToZ4-RSe8ug2S121EJz6jI69U/edit#gid=0").sheet1

# ---- Email Config ----
EMAIL_SENDER = "indianexpress.tourdesk@gmail.com"
EMAIL_PASSWORD = st.secrets["EMAIL_PASSWORD"]  # Also store this in secrets!

# ---- Booking Form ----
st.title("🌐 Indian Express Tour Booking")

with st.form("booking_form"):
    st.subheader("📝 New Booking")

    name = st.text_input("Full Name")
    phone = st.text_input("Phone")
    email = st.text_input("Email")
    address = st.text_area("Address")
    destination = st.selectbox("Destination", list(destination_codes.keys()))
    travel_date = st.date_input("Travel Date", min_value=date.today())
    persons = st.number_input("Persons", min_value=1, value=1)
    room_type = st.selectbox("🛏️ Room Type", ["Single", "Double", "Triple"])
    meal = st.selectbox("🍱 Meal Preference", ["None", "Veg", "Non-Veg", "Both"])
    custom_msg = st.text_area("✍️ Custom Message")
    amount_paid = st.number_input("💰 Amount Paid (₹)", min_value=0, step=100)

    submit = st.form_submit_button("✅ Confirm Booking")

    if submit:
        data = sheet.get_all_records()
        dest_code = destination_codes[destination]
        prefix = datetime.today().strftime("%y")
        matching_ids = [row['Booking_ID'] for row in data if row['Destination'] == destination]
        last_serial = max([int(bid[-4:]) for bid in matching_ids], default=0)
        next_serial = f"{last_serial + 1:04d}"
        booking_id = f"{prefix}{dest_code}{next_serial}"

        new_row = [
            booking_id, name, phone, email, address, destination,
            str(travel_date), persons, room_type, meal, custom_msg, amount_paid
        ]
        sheet.append_row(new_row)

        st.success(f"✅ Booking Confirmed! Booking ID: `{booking_id}`")

        # ---- QR ----
        qr_data = f"Booking ID: {booking_id}\nName: {name}\nDestination: {destination}\nDate: {travel_date}\nAmount: ₹{amount_paid}"
        qr_img = qrcode.make(qr_data)
        qr_path = tempfile.NamedTemporaryFile(delete=False, suffix=".png").name
        qr_img.save(qr_path)

        # ---- PDF ----
        def generate_pdf(data, qr_path):
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.cell(200, 10, txt="Indian Express Tour Booking", ln=True, align='C')
            pdf.ln(10)
            for key, value in data.items():
                if isinstance(value, str):
                    value = value.replace("\u20b9", "Rs.")
                pdf.cell(200, 10, txt=f"{key}: {value}", ln=True)
            pdf.image(qr_path, x=150, y=pdf.get_y() + 10, w=40)
            temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            pdf.output(temp.name.encode("latin-1"))
            return temp.name

        pdf_data = {
            "Booking_ID": booking_id, "Name": name, "Phone": phone, "Email": email,
            "Address": address, "Destination": destination, "Date": str(travel_date),
            "Persons": persons, "Room Type": room_type, "Meal": meal,
            "Custom Note": custom_msg, "Amount Paid": f"₹{amount_paid}"
        }

        pdf_path = generate_pdf(pdf_data, qr_path)

        # ---- Email ----
        msg = EmailMessage()
        msg["Subject"] = f"Booking Confirmation - {booking_id}"
        msg["From"] = EMAIL_SENDER
        msg["To"] = email
        msg.set_content(f"""
Hello {name},

Your tour booking has been confirmed!

Destination: {destination}
Date: {travel_date}
Booking ID: {booking_id}
Persons: {persons}
Room Type: {room_type}
Meal: {meal}
Amount Paid: ₹{amount_paid}

Please find your attached Booking Slip.

Thank you,
Indian Express Tours
""")

        with open(pdf_path, "rb") as f:
            msg.add_attachment(f.read(), maintype="application", subtype="pdf", filename=f"Booking_{booking_id}.pdf")

        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
                smtp.send_message(msg)
            st.success("📧 Confirmation Email Sent!")
        except Exception as e:
            st.error(f"❌ Email Failed: {e}")

        # ---- WhatsApp ----
        whatsapp_msg = f"Hello {name},%0ABooking Confirmed for {destination} on {travel_date}.%0AID: {booking_id}%0ARoom: {room_type}, Meal: {meal}, ₹{amount_paid}%0AThank you!"
        st.markdown(f"[📤 WhatsApp Confirmation](https://wa.me/{phone}?text={whatsapp_msg})", unsafe_allow_html=True)

        # ---- PDF Download ----
        with open(pdf_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
            st.markdown(f'<a href="data:application/octet-stream;base64,{b64}" download="Booking_{booking_id}.pdf">📄 Download PDF</a>', unsafe_allow_html=True)

# ---- Manage Bookings ----
st.markdown("---")
st.subheader("🔍 Manage Bookings")
df = pd.DataFrame(sheet.get_all_records())

# Dashboard
st.markdown("### 📊 Dashboard Summary")
st.write(f"🔢 Total Bookings: {len(df)}")
if 'Destination' in df.columns:
    st.write("📍 Destination-wise Count:")
    st.dataframe(df['Destination'].value_counts().rename_axis('Destination').reset_index(name='Total'))

# Date Filter
st.markdown("### 🗓️ Filter by Travel Date")
from_date = st.date_input("From Date", value=date.today())
to_date = st.date_input("To Date", value=date.today())
if 'Date' in df.columns:
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    filtered_df = df[(df['Date'] >= pd.to_datetime(from_date)) & (df['Date'] <= pd.to_datetime(to_date))]
    st.write(f"Showing {len(filtered_df)} bookings from {from_date} to {to_date}")
    st.dataframe(filtered_df)

# Search
st.markdown("### 🔍 Search Booking")
query = st.text_input("Search by Name / Phone / Email / Booking ID")
if query:
    results = df[df.apply(lambda row: query.lower() in str(row.values).lower(), axis=1)]
    if not results.empty:
        st.dataframe(results)
    else:
        st.warning("❌ No results found.")

# Delete
st.markdown("### 🗑️ Delete Booking")
delete_id = st.text_input("Enter Booking ID to Delete")
if st.button("❌ Delete Booking"):
    df_all = sheet.get_all_values()
    headers = df_all[0]
    rows = df_all[1:]
    target_row = next((i + 2 for i, row in enumerate(rows) if row and row[0] == delete_id), None)
    if target_row:
        sheet.delete_rows(target_row)
        st.success(f"🗑️ Booking ID {delete_id} deleted.")
    else:
        st.error("❌ Booking ID not found.")
