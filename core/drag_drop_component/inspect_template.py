import docx

with open('core/drag_drop_component/inspection_both.txt', 'w', encoding='utf-8') as f:
    for filename in ['Template_Form_TCNL.docx', 'Template_Form_KNNL.docx']:
        try:
            doc = docx.Document(filename)
            f.write(f'=== {filename} ===\n')
            f.write(f"Normal style font: {doc.styles['Normal'].font.name} {doc.styles['Normal'].font.size}\n")
            
            # Check first few paragraphs that have text
            for idx, p in enumerate(doc.paragraphs):
                if p.text.strip():
                    sizes = [r.font.size.pt if r.font.size else None for r in p.runs]
                    fonts = [r.font.name for r in p.runs]
                    f.write(f'P{idx}: "{p.text[:50]}" | Style: {p.style.name} | Fonts: {fonts} | Sizes: {sizes}\n')
                    break
                    
            # Check first table cell
            for t in doc.tables:
                for row in t.rows:
                    for cell in row.cells:
                        for p in cell.paragraphs:
                            if p.text.strip():
                                sizes = [r.font.size.pt if r.font.size else None for r in p.runs]
                                fonts = [r.font.name for r in p.runs]
                                f.write(f'Table cell: "{p.text[:50]}" | Fonts: {fonts} | Sizes: {sizes}\n')
                                break
                        break
                    break
                break
        except Exception as e:
            f.write(f'Error reading {filename}: {e}\n')
