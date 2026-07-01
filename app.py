import streamlit as st
import pandas as pd
from pypdf import PdfReader
from io import StringIO
import google.generativeai as genai

# Page Config
st.set_page_config(page_title="Doc to CSV Converter", layout="centered")
st.title("📄 Gemini 3.5 Doc-to-CSV Automation")
st.write("Upload your documents, extract structured text via Gemini 3.5 Flash, and download as CSV.")

# --- SECRETS MANAGEMENT ---
# Pull the API key securely from Streamlit's environment
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
else:
    st.error("❌ Missing Gemini API Key! Please configure it in your Streamlit dashboard secrets.")
    st.stop()
# ---------------------------

uploaded_files = st.file_uploader(
    "Upload PDFs or Images", 
    type=["pdf", "png", "jpg", "jpeg"], 
    accept_multiple_files=True
)

def extract_text_from_pdf(pdf_file):
    reader = PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text

if uploaded_files:
    genai.configure(api_key=api_key)
    
    system_instruction = (
        "You are an expert OCR data extraction assistant. "
        "Analyze the document and extract all key data points into a strict, single-line CSV format. "
        "Ensure data alignment. If a data field is missing, leave it empty between the commas. "
        "Do not wrap your output in markdown code blocks like ```csv, and do not include conversational text."
    )
    
    model = genai.GenerativeModel(
        model_name='gemini-3.5-flash',
        system_instruction=system_instruction
    )
    
    all_rows = []
    st.info("Processing files with Gemini 3.5 Flash...")
    
    for file in uploaded_files:
        if file.type == "application/pdf":
            raw_text = extract_text_from_pdf(file)
            prompt = f"Extract structured data from this text into a CSV row:\n{raw_text}"
        else:
            file_bytes = file.read()
            image_parts = [{"mime_type": file.type, "data": file_bytes}]
            prompt = [image_parts[0], "Extract all key data points from this image and format it strictly as a single CSV row with headers."]

        try:
            response = model.generate_content(prompt)
            csv_output = response.text.strip()
            df_temp = pd.read_csv(StringIO(csv_output))
            all_rows.append(df_temp)
        except Exception as e:
            st.error(f"Error processing {file.name}: {e}")

    if all_rows:
        final_df = pd.concat(all_rows, ignore_index=True)
        st.success("Extraction Complete!")
        st.dataframe(final_df)
        
        csv_buffer = final_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Data as CSV",
            data=csv_buffer,
            file_name="extracted_document_data.csv",
            mime="text/csv"
        )
else:
    st.warning("Please upload files to begin.")
