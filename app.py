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
st.write("Extracts Order Date, Distributor, and Item line tables directly into Google Sheets.")

# --- SECRETS MANAGEMENT ---
# Pulling API keys and Google Credentials from hidden Streamlit Dashboard settings
if "GEMINI_API_KEY" in st.secrets and "gcp_service_account" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
    google_creds = dict(st.secrets["gcp_service_account"])
else:
    st.error("❌ Missing Required App Credentials in Streamlit Secrets Management!")
    st.stop()
# ---------------------------

# Dropdown / URL targeting field for destination tracking
spreadsheet_url = st.text_input("Enter Destination Google Sheet Link:")
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

if uploaded_files and spreadsheet_url:
    genai.configure(api_key=api_key)
    
    # SYSTEM PROMPT: Updated to dynamically request absolute metadata + table lines
    system_instruction = (
        "You are an expert data parsing agent. Analyze the provided document "
        "and extract information strictly into a CSV table matching these exact 7 columns:\n"
        "Order Date, Distributor, Quantity, Item, Description, Price, Amount\n\n"
        "Rules:\n"
        "1. Identify the general invoice Order Date and the issuing Distributor name, and "
        "repeat those exact values across every row line item parsed from the invoice table.\n"
        "2. Output must format raw CSV with those 7 column headers on line 1.\n"
        "3. Do not include markdown brackets (```csv) or conversational feedback sentences."
    )
    
    model = genai.GenerativeModel(
        model_name='gemini-3.5-flash',
        system_instruction=system_instruction
    )
    
    all_rows = []
    st.info("Extracting invoice rows...")
    
    for file in uploaded_files:
        try:
            if file.type == "application/pdf":
                raw_text = extract_text_from_pdf(file)
                if not raw_text.strip():
                    st.warning(f"⚠️ {file.name} is likely a flat scanned image. Try a PNG or JPEG conversion.")
                    continue
                prompt = f"Map out this document text into the structured 7-column CSV table structure:\n\n{raw_text}"
                response = model.generate_content(prompt)
            else:
                img = Image.open(file)
                prompt = "Map out this layout image into the requested 7-column CSV format table."
                response = model.generate_content([prompt, img])

            csv_output = response.text.strip()
            
            # Clean structural string format
            if csv_output.startswith("```"):
                csv_output = csv_output.split("\n", 1)[1]
            if csv_output.endswith("```"):
                csv_output = csv_output.rsplit("\n", 1)[0]
            csv_output = csv_output.replace("```csv", "").replace("```", "").strip()

            if csv_output:
                df_temp = pd.read_csv(StringIO(csv_output))
                if not df_temp.empty:
                    expected_cols = ["Order Date", "Distributor", "Quantity", "Item", "Description", "Price", "Amount"]
                    for col in expected_cols:
                        if col not in df_temp.columns:
                            df_temp[col] = None
                    df_temp = df_temp[expected_cols]
                    all_rows.append(df_temp)
        except Exception as e:
            st.error(f"❌ Error processing {file.name}: {str(e)}")

    if all_rows:
        final_df = pd.concat(all_rows, ignore_index=True)
        st.write("📊 **Extracted Data Preview:**")
        st.dataframe(final_df)
        
        # --- WRITE DIRECTLY TO GOOGLE SHEETS ---
        try:
            st.info("Connecting and updating Google Sheet database...")
            # Login utilizing service keys
            gc = gspread.service_account_from_dict(google_creds)
            sh = gc.open_by_url(spreadsheet_url)
            worksheet = sh.get_worksheet(0) # Targeting sheet index 1 (Sheet1)
            
            # Convert NaN values safely to empty strings for API stability
            final_df = final_df.fillna("")
            # Extract underlying row matrix list
            data_to_append = final_df.values.tolist()
            
            # Append rows safely below the last active text box row
            worksheet.append_rows(data_to_append)
            st.success("🎉 Data successfully written directly to Google Sheets!")
            
        except Exception as sheet_error:
            st.error(f"❌ Failed to push data into Google Sheets: {str(sheet_error)}")
else:
    st.warning("Provide your Google Sheet link destination and drop your files to execute the process.")
