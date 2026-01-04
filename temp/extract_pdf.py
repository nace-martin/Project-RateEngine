import fitz
from pathlib import Path

pdf_path = Path(r"C:\Users\commercial.manager\Downloads\QT-36 (5).pdf")
with fitz.open(pdf_path) as doc:
    text = doc.load_page(0).get_text()
print(text)
