import fitz
doc = fitz.open("data/psychology2e.pdf")
print("Số trang PDF:", len(doc))
for i in range(0, 60):
    t = doc[i].get_text("text")
    if "Introduction to Psychology" in t and "CHAPTER 1" in t.upper():
        print("Gợi ý: Chương 1 bắt đầu ở trang PDF", i + 1)