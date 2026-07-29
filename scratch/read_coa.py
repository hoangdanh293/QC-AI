import fitz # PyMuPDF
import sys

sys.stdout.reconfigure(encoding='utf-8')

def extract_pdf_text(path):
    doc = fitz.open(path)
    print(f"File: {path}, Pages: {len(doc)}")
    for page_num in range(len(doc)):
        page = doc[page_num]
        print(f"\n================ PAGE {page_num + 1} ================")
        text = page.get_text()
        print(text)

if __name__ == "__main__":
    extract_pdf_text("d:/QC_AI_Win/Test/COA Crystalline Maltitol - F.pdf")
