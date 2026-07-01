import streamlit as st
import pandas as pd
from pypdf import PdfReader
from io import StringIO
from PIL import Image
import google.generativeai as genai

# Page Config
st.set_page_config(page_title="Doc to CSV Converter", layout="centered")
st.title("📄 Gemini 3.5 Item Extractor")
st.write("Extracts Quantity, Item, Description, Price, and Amount straight to a clean CSV.")

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
    
    # SYSTEM PROMPT: Locked down to strictly map out your 5 desired columns
    system_instruction = (
        "You are a strict data extraction engine. Analyze the provided document "
        "and extract information ONLY into these exact 5 columns: "
        "Quantity, Item, Description, Price, Amount. "
        "Instructions:\n"
        "1. Output must be raw CSV formatting with those 5 columns as headers on line 1.\n"
        "2. If an item name and its description are grouped together, separate them cleanly.\n"
        "3. Do not include invoice totals, billing addresses, or metadata.\n"
        "4. Do not include markdown style syntax (like ```csv) or introductory sentences."
    )
    
    model = genai.GenerativeModel(
        model_name='gemini-3.5-flash',
        system_instruction=system_instruction
    )
    
    all_rows = []
    st.info("Parsing specific item data points...")
    
    for file in uploaded_files:
        try:
            # Handle PDF Input
            if file.type == "application/pdf":
                raw_text = extract_text_from_pdf(file)
                if not raw_text.strip():
                    st.warning(f"⚠️ {file.name} appears to be a scanned image-PDF. Convert it to a PNG/JPG first.")
                    continue
                prompt = f"Convert this text into the requested 5-column CSV format:\n\n{raw_text}"
                response = model.generate_content(prompt)
            
            # Handle Image Input
            else:
                img = Image.open(file)
                prompt = "Extract all line items from this image into the requested 5-column CSV format."
                response = model.generate_content([prompt, img])

            # Process Output
            csv_output = response.text.strip()
            
            # Sanitize stray markdown formatting tags if Gemini emits them
            if csv_output.startswith("```"):
                csv_output = csv_output.split("\n", 1)[1]
            if csv_output.endswith("```"):
                csv_output = csv_output.rsplit("\n", 1)[0]
            csv_output = csv_output.replace("```csv", "").replace("```", "").strip()

            if csv_output:
                df_temp = pd.read_csv(StringIO(csv_output))
                if not df_temp.empty:
                    # Enforce the column filter in case the model hallucinated extra header rows
                    expected_cols = ["Quantity", "Item", "Description", "Price", "Amount"]
                    # Add missing columns dynamically just in case
                    for col in expected_cols:
                        if col not in df_temp.columns:
                            df_temp[col] = None
                    # Reorder/filter to your exact layout requirement
                    df_temp = df_temp[expected_cols]
                    all_rows.append(df_temp)
                else:
                    st.error(f"⚠️ Could not identify distinct columns in {file.name}.")
            else:
                st.error(f"❌ Failed to extract readable text matrix for {file.name}.")

        except Exception as e:
            st.error(f"❌ Error processing {file.name}: {str(e)}")

    # Display and Download
    if all_rows:
        final_df = pd.concat(all_rows, ignore_index=True)
        
        st.success("Extraction Complete!")
        st.dataframe(final_df)  # Show the structured preview table directly on screen
        
        csv_buffer = final_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Structured CSV",
            data=csv_buffer,
            file_name="extracted_line_items.csv",
            mime="text/csv"
        )
else:
    st.warning("Please upload file arrays to begin extraction.")
