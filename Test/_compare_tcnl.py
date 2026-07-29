import json, os, sys

b = json.load(open('test/result_tcnl_baseline.json', encoding='utf-8'))
i = json.load(open('test/result_tcnl_improved.json', encoding='utf-8'))

W = 70
print('=' * W)
print('SO SANH BASELINE vs IMPROVED (TCNL - Folic Acid EP + COA)')
print('Model: gemma-4-31b-it | Provider: Google API')
print('=' * W)

rows = [
    ('Node 0 - Trich ten (s)',       b.get('node0_time_sec',0),    i.get('node0_time_sec',0),    False),
    ('Node 1 - Scan song song (s)',  b.get('node1_time_sec',0),    i.get('node1_time_sec',0),    False),
    ('Node 2 - Methods (s)',         b.get('node2_time_sec',0),    i.get('node2_time_sec',0),    False),
    ('Tong thoi gian (s)',           b.get('total_time_sec',0),    i.get('total_time_sec',0),    False),
    ('EP chi tieu tim thay',         b.get('ep_criteria_count',0), i.get('ep_criteria_count',0), True),
    ('Scan accuracy (%)',            b.get('scan_accuracy_pct',0), i.get('scan_accuracy_pct',0), True),
    ('Methods accuracy (%)',         b.get('methods_accuracy_pct',0), i.get('methods_accuracy_pct',0), True),
    ('Combined accuracy (%)',        b.get('combined_accuracy_pct',0), i.get('combined_accuracy_pct',0), True),
]

hdr = '%-40s %10s %10s %16s' % ('Tieu chi', 'Baseline', 'Improved', 'Delta')
print('  ' + hdr)
print('  ' + '-' * 78)

for name, bv, iv, higher_good in rows:
    d = iv - bv
    if abs(d) < 0.01:
        arrow = '  -> khong doi'
    elif (d > 0) == higher_good:
        arrow = 'BETTER %+.2f' % d
    else:
        arrow = 'WORSE  %+.2f' % d
    row = '%-40s %10.2f %10.2f %16s' % (name, bv, iv, arrow)
    print('  ' + row)

print()
node2_b = b.get('node2_time_sec', 1)
node2_i = i.get('node2_time_sec', 1)
tot_b   = b.get('total_time_sec', 1)
tot_i   = i.get('total_time_sec', 1)

speed_n2  = round((node2_b - node2_i) / max(node2_b, 1) * 100, 1)
speed_tot = round((tot_b - tot_i) / max(tot_b, 1) * 100, 1)
acc_delta = round(i.get('combined_accuracy_pct', 0) - b.get('combined_accuracy_pct', 0), 1)

print('  Node 2 toc do tang  : %+.1f%%' % speed_n2)
print('  Tong toc do tang    : %+.1f%%' % speed_tot)
print('  Do chinh xac delta  : %+.1f diem phan tram' % acc_delta)
print('=' * W)
