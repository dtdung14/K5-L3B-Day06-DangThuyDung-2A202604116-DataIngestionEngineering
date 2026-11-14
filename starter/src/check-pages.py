import fitz

OFF = 12
doc = fitz.open("data/psychology2e.pdf")
print("Số trang PDF:", len(doc))
for p in [18, 19, 41, 42, 46, 47, 74, 75]:
    t = " ".join(doc[p - 1].get_text("text").split())
    print(f"--- PDF {p} (in {p-OFF}) | {len(t)} ký tự")
    print("ĐẦU:", t[:130])
    print("CUỐI:", t[-70:])