from pathlib import Path
text = Path('backend/templates/quotes/quote_pdf.html').read_text(encoding='utf-8')
indices = []
start = 0
while True:
    i = text.find('{{', start)
    if i == -1:
        break
    j = text.find('}}', i + 2)
    if j == -1:
        break
    snippet = text[i:j+2]
    if '\n' in snippet:
        indices.append(snippet)
    start = j + 2
print(len(indices))
