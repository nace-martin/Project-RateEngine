import fitz
from pathlib import Path

pdf_path = Path(r"C:\Users\commercial.manager\Downloads\QT-36 (5).pdf")
output_dir = Path("temp")
output_dir.mkdir(parents=True, exist_ok=True)

with fitz.open(pdf_path) as doc:
    for page_index in range(min(2, doc.page_count)):
        page = doc.load_page(page_index)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        out_path = output_dir / f"qt-36-page-{page_index+1}.png"
        pix.save(out_path)
        print(out_path)
