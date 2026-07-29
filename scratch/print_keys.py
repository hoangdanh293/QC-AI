import json
with open("method_library.json", "r", encoding="utf-8") as f:
    data = json.load(f)
with open("scratch/nung_1_detail.txt", "w", encoding="utf-8") as out:
    if "nung_1" in data:
        json.dump(data["nung_1"], out, indent=2, ensure_ascii=False)
    else:
        out.write("Not found")
print("Done writing nung_1 details")
