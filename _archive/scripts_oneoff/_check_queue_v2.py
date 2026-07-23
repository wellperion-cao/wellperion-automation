import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
path = r"C:\Users\jjky0\welperion-automation\3. 웰페리온 가이드\cmo\review\review_queue.json"
with open(path, encoding="utf-8") as f:
    q = json.load(f)
v2 = [x for x in q if "V2" in x.get("id", "")]
print("총 엔트리:", len(q))
for item in v2:
    print(" ", item["id"], "|", item["status"], "|", item["title"][:45])
print("JSON 유효성: OK")
