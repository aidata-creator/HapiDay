import streamlit as st
import pandas as pd
from pypdf import PdfReader
from io import StringIO
from PIL import Image
import google.generativeai as genai
import gspread

# Page Config
st.set_page_config(page_title="Doc to Google Sheets Automation", layout="centered")
st.title("📄 Gemini 3.5 Sheet Automation Pipeline")
st.write("Enter the metadata metadata below, then upload documents to append them to your Google Sheet.")

# --- AUTOMATION CONFIGURATION ---
# Put your permanent Google Sheet link here
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/YOUR_ACTUAL_SHEET_ID_HERE/edit#gid=0"
# ---------------------------------

# --- SECRETS MANAGEMENT ---
if "GEMINI_API_KEY" in st.secrets and "gcp_service_account" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
    google_creds = dict(st.secrets["gcp_service_account"])
else:
    st.error("❌ Missing Required App Credentials in Streamlit Secrets Management!")
    st.stop()
# ---------------------------

# Side-by-side user inputs for the person in charge
col1, col2 = st.columns(2)
with col1:
    user_order_date = st.text_input("📅 Order Date (e.g., YYYY-MM-DD or MM/DD/YYYY):")
with col2:
    user_distributor = st.text_input("🏢 Distributor Name:")

uploaded_files = st.file_uploader(
    "Upload Document Invoices / Receipts", 
    type=["pdf", "png", "jpg", "jpeg"], 
    accept_multiple_files=True
)

def extract_text_from_pdf(pdf_file):
    reader = PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text

# Process only if inputs are filled out by the operator
if uploaded_files:
    if not user_order_date or not user_distributor:
        st.warning("⚠️ Please enter the Order Date and Distributor Name above before processing.")
    else:
        genai.configure(api_key=api_key)
        
        # SYSTEM PROMPT: Now strictly focused ONLY on getting the 5 item table variables
        system_instruction = (
            "You are a strict line-item extraction engine. Analyze the provided document "
            "and extract line data items ONLY into these exact 5 columns:\n"
            "Quantity, Item, Description, Price, Amount\n\n"
            "Rules:\n"
            "1. Output must be raw CSV formatting with those 5 columns as headers on line 1.\n"
            "2. If an item name and its description are grouped together, separate them cleanly.\n"
            "3. Do not look for dates or distributor headers. Do not include summary totals or metadata.\n"
            "4. Do not include markdown brackets (```csv) or conversational text."
        )
        
        model = genai.GenerativeModel(
            model_name='gemini-3.5-flash',
            system_instruction=system_instruction
        )
        
        all_rows = []
        st.info("Extracting line item rows with Gemini 3.5 Flash...")
        
        for file in uploaded_files:
            try:
                if file.type == "application/pdf":
                    raw_text = extract_text_from_pdf(file)
                    if not raw_text.strip():
                        st.warning(f"⚠️ {file.name} is likely a flat scanned image. Try a PNG or JPEG conversion.")
                        continue
                    prompt = f"Convert this text layout into the 5-column CSV matrix schema:\n\n{raw_text}"
                    response = model.generate_content(prompt)
                else:
                    img = Image.open(file)
                    prompt = "Extract all line items from this image layout into the 5-column CSV format table."
                    response = model.generate_content([prompt, img])

                csv_output = response.text.strip()
                
                # Clean up potential markdown code indicators
                if csv_output.startswith("```"):
                    csv_output = csv_output.split("\n", 1)[1]
                if csv_output.endswith("```"):
                    csv_output = csv_output.rsplit("\n", 1)[0]
                csv_output = csv_output.replace("```csv", "").replace("```", "").strip()

                if csv_output:
                    df_temp = pd.read_csv(StringIO(csv_output))
                    if not df_temp.empty:
                        # Enforce standard column validation checking
                        expected_cols = ["Quantity", "Item", "Description", "Price", "Amount"]
                        for col in expected_cols:
                            if col not in df_temp.columns:
                                df_temp[col] = None
                        df_temp = df_temp[expected_cols]
                        
                        # Inject the values typed by the person in charge into the structural columns
                        df_temp.insert(0, "Distributor", user_distributor)
                        df_temp.insert(0, "Order Date", user_order_date)
                        
                        all_rows.append(df_temp)
            except Exception as e:
                st.error(f"❌ Error processing {file.name}: {str(e)}")

        if all_rows:
            final_df = pd.concat(all_rows, ignore_index=True)
            st.write("📊 **Extracted Data Preview (Ready to Sync):**")
            st.dataframe(final_df)
            
            # --- WRITE DIRECTLY TO GOOGLE SHEETS ---
            try:
                st.info("Connecting and updating Google Sheet database...")
                gc = gspread.service_account_from_dict(google_creds)
                sh = gc.open_by_url(SPREADSHEET_URL)
                worksheet = sh.get_worksheet(0)  # Targets Sheet1
                
                # Clean missing fields cleanly
                final_df = final_df.fillna("")
                data_to_append = final_df.values.tolist()
                
                worksheet.append_rows(data_to_append)
                st.success("🎉 Data successfully appended directly to your Google Sheet!")
                
            except Exception as sheet_error:
                st.error(f"❌ Failed to push data into Google Sheets: {str(sheet_error)}")
