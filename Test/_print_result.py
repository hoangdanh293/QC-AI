import json, sys
sys.stdout.reconfigure(encoding='utf-8')
d = json.load(open('test/result_tcnl_improved.json', encoding='utf-8'))
print("=== EP LIST ===")
for x in d.get('ep_list', []):
    print(f"- {x.get('ten_chi_tieu')}: {x.get('gioi_han')}")
print("=== METHODS ===")
for k, v in d.get('methods', {}).items():
    print(f"- {k}: {v[:150]}...")
