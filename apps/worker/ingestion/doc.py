import fitz # PyMuPDF
import os

def process_pdf(file_path: str):
    doc = fitz.open(file_path)
    chunks = []

    for page_num, page in enumerate(doc):
        text = page.get_text()
        # Naive page-level chunking.
        # Better: layout analysis or sliding window on text.
        chunks.append({
            "text": text,
            "metadata": {
                "page": page_num + 1,
                "source": os.path.basename(file_path)
            }
        })
    return chunks
