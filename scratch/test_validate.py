import sys
sys.path.insert(0, '.')
from core.doc_processor import _validate_scanned_criteria

test_data = [
    {'ten_chi_tieu': 'Dinh luong / Assay', 'gioi_han': 'Khong qua 1,0% / Not more than 1.0%'},
    {'ten_chi_tieu': 'Ham luong nuoc / Water', 'gioi_han': 'Khong qua 1,0% / Not more than 1.0%'},
    {'ten_chi_tieu': 'Chi so acid', 'gioi_han': 'Not more than 1 mg/kg Lead'},
    {'ten_chi_tieu': 'Dinh luong / Assay', 'gioi_han': '98,0% den 102,0%'},
    {'ten_chi_tieu': 'Chi / Lead', 'gioi_han': 'Not more than 1 mg/kg'},
]

result = _validate_scanned_criteria(test_data)
for r in result:
    warn = r.get('_validation_warning', '')
    print(f"  Name:  {r['ten_chi_tieu']}")
    print(f"  Limit: \"{r['gioi_han']}\"")
    if warn:
        print(f"  [FIXED]: {warn}")
    print()
