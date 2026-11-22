import pymupdf

doc = pymupdf.open("data/synthetic_cases/draft_business_bay_lease.pdf")
page = doc[0]

print("=== get_text('text') — plain extraction ===")
text = page.get_text("text")
print(f"Total chars: {len(text)}")
arabic_chars = [c for c in text if '\u0600' <= c <= '\u06FF']
print(f"Arabic codepoint chars: {len(arabic_chars)}")
print(f"First 400 chars:\n{text[:400]}")
print()

print("=== get_text('dict') — block-by-block ===")
d = page.get_text("dict")
blocks_with_arabic = 0
for block in d["blocks"]:
    if "lines" not in block:
        continue
    for line in block["lines"]:
        for span in line["spans"]:
            txt = span["text"]
            if any('\u0600' <= c <= '\u06FF' for c in txt):
                blocks_with_arabic += 1
                print(f"  font={span['font']} | text={txt[:80]}")
print(f"Arabic spans found: {blocks_with_arabic}")
print()

print("=== fonts embedded ===")
for f in page.get_fonts(full=True):
    print(f"  {f}")

doc.close()