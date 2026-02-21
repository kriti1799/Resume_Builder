# app/utils.py
import fitz  # PyMuPDF
import docx
import io

def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """
    Extracts text from a PDF or DOCX file stored in memory.
    """
    text = ""
    filename_lower = filename.lower()
    
    try:
        if filename_lower.endswith('.pdf'):
            # Open the PDF directly from the byte stream
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                for page in doc:
                    text += page.get_text()
                    
        elif filename_lower.endswith('.docx'):
            # Open the DOCX directly from the byte stream
            doc = docx.Document(io.BytesIO(file_bytes))
            for para in doc.paragraphs:
                text += para.text + "\n"
                
        else:
            return "Unsupported file format. Please upload a PDF or DOCX."
            
    except Exception as e:
        return f"Error extracting text: {str(e)}"
        
    return text.strip()