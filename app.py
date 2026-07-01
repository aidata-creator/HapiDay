import streamlit as st
import pandas as pd
from pypdf import PdfReader
from io import StringIO
from PIL import Image
import google.generativeai as genai
import gspread

# Page Configuration
st.set_page_config(page_title="Doc to Google Sheets Automation", layout="centered")
st.title("📄 HapiDay Order Automation Pipeline")
st.write("Fill out the tracking parameters, upload your files, review the data, then click Save.")

# --- AUTOMATION CONFIGURATION ---
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1y2ITgmqH9f4-xavbrS550qCDXZ4Bu-ILlaq84Y76zSY/edit#gid=0"
# ---------------------------------

# --- SECRETS MANAGEMENT ---
if "GEMINI_API_KEY" in st.secrets and "gcp_service_account" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
    google_creds = dict(st.secrets["gcp_service_account"])
else:
    st.error("❌ Missing Required App Credentials in Streamlit Secrets Management!")
    st.stop()
# ---------------------------

# Initialize session state variables to hold data across clicks
if "extracted_df" not in st.session_state:
    st.session_state.extracted_df = None

# Form prompts for the operator in charge
st.subheader("📋 Administrative Info Setup")
col1, col2 = st.columns(2)
with col1:
    user_order_date = st.text_input("📅 Order Date (e.g., MM/DD/YYYY or YYYY-MM-DD):")
with col2:
    user_distributor = st.text_input("🏢 Distributor / Vendor Name:")

st.write("---")

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

# --- STEP 1: EXTRACTION TRIGGER ---
if uploaded_files:
    if not user_order_date or not user_distributor:
        st.warning("⚠️ Action Required: Please fill out both the **Order Date** and **Distributor Name** fields above before processing.")
    else:
        # Create a button to run the AI extraction
        if st.button("🔍 Step 1: Run AI Extraction", use_container_width=True):
            genai.configure(api_key=api_key)
            
            system_instruction = (
                "You are a strict item-line extraction engine. Analyze the document provided "
                "and map out data parameters strictly into a CSV matrix with these exact 5 columns:\n"
                "Quantity, Item, Description, Price, Amount\n\n"
                "Rules:\n"
                "1. Output must display the raw CSV data formatting with those 5 column headers on line 1.\n"
                "2. If an item name and its description are combined in the source file, split them into separate columns.\n"
                "3. Do not attempt to look for generic metadata fields like dates or distributor addresses. Skip all invoice summary totals.\n"
                "4. Output only raw table lines; do not wrap text outputs in markdown brackets like ```csv."
            )
            
            model = genai.GenerativeModel(
                model_name='gemini-3.5-flash',
                system_instruction=system_instruction
            )
            
            all_rows = []
            st.info("Parsing invoice segments using Gemini 3.5 Flash...")
            
            for file in uploaded_files:
                try:
                    if file.type == "application/pdf":
                        raw_text = extract_text_from_pdf(file)
                        if not raw_text.strip():
                            st.warning(f"⚠️ Scanned page check failed for {file.name}. Try processing as an image instead.")
                            continue
                        prompt = f"Extract all row data items matching the 5-column CSV target matrix from this text block:\n\n{raw_text}"
                        response = model.generate_content(prompt)
                    else:
                        img = Image.open(file)
                        prompt = "Extract all individual product line items from this document image array into the 5-column CSV matrix schema."
                        response = model.generate_content([prompt, img])

                    csv_output = response.text.strip()
                    
                    # Sanitize output string
                    if csv_output.startswith("```"):
                        csv_output = csv_output.split("\n", 1)[1]
                    if csv_output.endswith("```"):
                        csv_output = csv_output.rsplit("\n", 1)[0]
                    csv_output = csv_output.replace("```csv", "").replace("```", "").strip()

                    if csv_output:
                        df_temp = pd.read_csv(StringIO(csv_output))
                        if not df_temp.empty:
                            expected_cols = ["Quantity", "Item", "Description", "Price", "Amount"]
                            for col in expected_cols:
                                if col not in df_temp.columns:
                                    df_temp[col] = None
                            df_temp = df_temp[expected_cols]
                            
                            # Prepend metadata
                            df_temp.insert(0, "Distributor", user_distributor)
                            df_temp.insert(0, "Order Date", user_order_date)
                            
                            all_rows.append(df_temp)
                except Exception as e:
                    st.error(f"❌ Automation Error handling {file.name}: {str(e)}")

            if all_rows:
                # Save data frame into session state memory
                st.session_state.extracted_df = pd.concat(all_rows, ignore_index=True)
                st.success("🤖 Extraction Complete! Review your data below.")

# --- STEP 2: REVIEW & MANUAL SAVE TO GOOGLE SHEETS ---
if st.session_state.extracted_df is not None:
    st.write("### 📊 Data Preview")
    # Display editable dataframe option so you can tweak any errors manually right on screen!
    edited_df = st.data_editor(st.session_state.extracted_df, use_container_width=True)
    
    st.write("---")
    
    # Dedicated Save Button
    if st.button("📤 Step 2: Save to Google Sheet", type="primary", use_container_width=True):
        try:
            with st.spinner("Pushing data to Google Sheets..."):
                gc = gspread.service_account_from_dict(google_creds)
                sh = gc.open_by_url(SPREADSHEET_URL)
                worksheet = sh.get_worksheet(0)
                
                # Fill missing cells, convert to a standard python list matrix
                edited_df = edited_df.fillna("")
                data_to_append = edited_df.values.tolist()
                
                worksheet.append_rows(data_to_append)
                st.success("🎉 Data successfully aligned and pushed into your Google Sheet log!")
                
                # Clear out state so it doesn't prompt you to accidentally duplicate save
                st.session_state.extracted_df = None
                
        except Exception as sheet_error:
            st.error(f"❌ Spreadsheet connection error: {str(sheet_error)}")
