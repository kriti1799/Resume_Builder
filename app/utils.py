# app/utils.py
import fitz  # PyMuPDF
import docx
import io
import re


URL_PATTERN = re.compile(r"(https?://[^\s<>\]\)\"']+|www\.[^\s<>\]\)\"']+)", re.IGNORECASE)


def _normalize_url(url: str) -> str:
    u = (url or "").strip().rstrip(".,;)")
    if not u:
        return ""
    if u.lower().startswith("www."):
        return f"https://{u}"
    return u


def _extract_pdf_links(file_bytes: bytes) -> list[str]:
    links: list[str] = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            for item in page.get_links():
                uri = item.get("uri")
                if uri:
                    links.append(uri)
    return links


def _extract_docx_links(doc: docx.Document) -> list[str]:
    links: list[str] = []
    for rel in doc.part.rels.values():
        if "hyperlink" in rel.reltype and rel.target_ref:
            links.append(rel.target_ref)
    return links

def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """
    Extracts text from a PDF or DOCX file stored in memory.
    """
    text = ""
    links: list[str] = []
    filename_lower = filename.lower()
    
    try:
        if filename_lower.endswith('.pdf'):
            # Open the PDF directly from the byte stream
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                for page in doc:
                    text += page.get_text()
            links.extend(_extract_pdf_links(file_bytes))
                    
        elif filename_lower.endswith('.docx'):
            # Open the DOCX directly from the byte stream
            doc = docx.Document(io.BytesIO(file_bytes))
            for para in doc.paragraphs:
                text += para.text + "\n"
            links.extend(_extract_docx_links(doc))
                
        else:
            return "Unsupported file format. Please upload a PDF or DOCX."
            
    except Exception as e:
        return f"Error extracting text: {str(e)}"

    # Catch visible URL strings as fallback for non-embedded links.
    links.extend(URL_PATTERN.findall(text))
    normalized = []
    seen = set()
    for link in links:
        url = _normalize_url(link)
        if not url:
            continue
        low = url.lower()
        if low in seen:
            continue
        seen.add(low)
        normalized.append(url)

    if normalized:
        preferred = sorted(
            normalized,
            key=lambda u: (0 if ("linkedin.com" in u.lower() or "github.com" in u.lower()) else 1, u.lower()),
        )
        text += "\n\nExtracted Links:\n" + "\n".join(f"- {u}" for u in preferred)

    return text.strip()
