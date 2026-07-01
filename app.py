import streamlit as st
import pandas as pd
from pypdf import PdfReader
from io import StringIO
from PIL import Image
import google.generativeai as genai

# Page Config
st.set_page_config(page_title="Doc to CSV Converter", layout="centered")
st.title("📄 Gemini 3.5 Doc-to-CSV Automation")
st.write("Upload your documents, extract structured text via Gemini 3.5 Flash, and download as CSV.")

# --- SECRETS MANAGEMENT ---
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
    
    # We use a cleaner system instruction allowing standard markdown blocks to make parsing safer
    system_instruction = (
        "You are an expert data extraction assistant. Analyze the provided document and extract "
        "all important data points (e.g., Dates, Names, Line Items, Descriptions, Amounts, Totals). "
        "Output the result strictly as a structured CSV table. Include the column header names "
        "on the first line, followed by the extracted data rows. Do not write conversational text."
    )
    
    model = genai.GenerativeModel(
        model_name='gemini-3.5-flash',
        system_instruction=system_instruction
    )
    
    all_rows = []
    st.info("Processing files with Gemini 3.5 Flash...")
    
    for file in uploaded_files:
        try:
            # --- Handle PDF Input ---
            if file.type == "application/pdf":
                raw_text = extract_text_from_pdf(file)
                if not raw_text.strip():
                    st.warning(f"⚠️ {file.name} appears to be a scanned PDF with no embedded text. Try converting it to an image first.")
                    continue
                prompt = f"Convert the following document text into a clean CSV table with headers:\n\n{raw_text}"
                response = model.generate_content(prompt)
            
            # --- Handle Image Input (PNG/JPG) ---
            else:
                img = Image.open(file)
                prompt = "Analyze this image and extract all relevant structured fields into a clean CSV table format with headers."
                response = model.generate_content([prompt, img])

            # --- Process & Clean the Output ---
            csv_output = response.text.strip()
            
            # Clean up potential markdown wrapper code formatting if Gemini adds it (```csv ... ```)
            if csv_output.startswith("```"):
                csv_output = csv_output.split("\n", 1)[1]
            if csv_output.endswith("```"):
                csv_output = csv_output.rsplit("\n", 1)[0]
                
            csv_output = csv_output.replace("```csv", "").replace("```", "").strip()

            # Read the CSV text safely into Pandas
            if csv_output:
                df_temp = pd.read_csv(StringIO(csv_output))
                if not df_temp.empty:
                    all_rows.append(df_temp)
                else:
                    st.error(f"⚠️ Gemini processed {file.name}, but returned an empty table.")
            else:
                st.error(f"❌ Gemini returned a completely blank response for {file.name}.")

        except Exception as e:
            st.error(f"❌ Error processing {file.name}: {str(e)}")

    # --- Display and Download Results ---
    if all_rows:
        # Merge rows matching different structures smoothly
        final_df = pd.concat(all_rows, ignore_index=True, sort=False)
        
        st.success("Extraction Complete!")
        st.dataframe(final_df)  # Visually show the table
        
        # CSV processing for download
        csv_buffer = final_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Data as CSV",
            data=csv_buffer,
            file_name="extracted_document_data.csv",
            mime="text/csv"
        )
else:
    st.warning("Please upload files to begin.")
