import sys
sys.stdout.reconfigure(encoding='utf-8')

try:
    import fitz # PyMuPDF
    print("fitz available")
except ImportError:
    print("fitz not available")

try:
    import pypdf
    print("pypdf available")
except ImportError:
    print("pypdf not available")

try:
    import pdfplumber
    print("pdfplumber available")
except ImportError:
    print("pdfplumber not available")
