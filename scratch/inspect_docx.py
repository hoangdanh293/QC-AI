import docx
import sys

sys.stdout.reconfigure(encoding='utf-8')

def find_text_docx(path, search_str):
    doc = docx.Document(path)
    print("--- PARAGRAPHS ---")
    for i, p in enumerate(doc.paragraphs):
        if search_str.lower() in p.text.lower():
            print(f"P {i}: {p.text}")
            
    print("--- TABLES ---")
    for i, t in enumerate(doc.tables):
        for r_idx, row in enumerate(t.rows):
            seen_cells = set()
            for c_idx, cell in enumerate(row.cells):
                if cell in seen_cells:
                    continue
                seen_cells.add(cell)
                if search_str.lower() in cell.text.lower():
                    txt = cell.text.strip().replace('\n', ' ')
                    print(f"Table {i} R{r_idx} C{c_idx}: {txt}")

if __name__ == "__main__":
    find_text_docx("d:/QC_AI_Win/Template_Form_TCNL.docx", "ban hành")
