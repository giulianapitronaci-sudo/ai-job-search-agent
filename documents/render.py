"""Turn a JSON file into a one-page PDF CV or cover letter.

The agent (or you) writes the content as JSON; this script only handles the
layout. Keeping content and layout apart means a tailored CV is just a new
JSON file, and the design stays the same everywhere.

Usage (from the repository root):
    python3 documents/render.py cv     examples/cv.example.json     output/cv.pdf
    python3 documents/render.py letter examples/letter.example.json output/letter.pdf

Needs Google Chrome (or set the CHROME environment variable to its path).
If pdfplumber is installed, the script also checks the result fits on one page.
"""
import html
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CSS = os.path.join(HERE, "templates", "style.css")
FONT = '<link href="https://fonts.googleapis.com/css2?family=Lato:wght@400;700&display=swap" rel="stylesheet">'
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

e = html.escape  # every piece of text is escaped, so "R&D" or "<5%" can't break the page


# ---------- HTML builders (pure functions: data in, HTML out) ----------

def page(body, extra_class=""):
    with open(CSS) as f:
        css = f.read()
    return (f'<!doctype html><html><head><meta charset="utf-8">{FONT}<style>{css}</style></head>'
            f'<body><div class="page {extra_class}">{body}</div></body></html>')


def entry_html(entry):
    org = f' · <span class="org">{e(entry["org"])}</span>' if entry.get("org") else ""
    out = (f'<div class="entry"><div class="head"><div class="title">{e(entry["role"])}{org}</div>'
           f'<div class="date">{e(entry.get("date", ""))}</div></div>')
    if entry.get("sub"):
        out += f'<div class="sub">{e(entry["sub"])}</div>'
    if entry.get("bullets"):
        out += "<ul>" + "".join(f"<li>{e(b)}</li>" for b in entry["bullets"]) + "</ul>"
    return out + "</div>"


def section_html(section):
    out = f'<h2>{e(section["title"])}</h2>'
    if "skills" in section:
        rows = "".join(f"<p><b>{e(k)}</b> {e(v)}</p>" for k, v in section["skills"].items())
        return out + f'<div class="skills">{rows}</div>'
    return out + "".join(entry_html(x) for x in section.get("entries", []))


def cv_html(cv, base_dir="."):
    photo = ""
    if cv.get("photo"):
        photo = f'<img class="photo" src="file://{os.path.abspath(os.path.join(base_dir, cv["photo"]))}" alt="">'
    contact = "".join(f"<span>{e(c)}</span>" for c in cv.get("contact", []))
    body = (f'<div class="top"><div class="top-text"><h1>{e(cv["name"])}</h1>'
            f'<p class="summary">{e(cv.get("summary", ""))}</p></div>{photo}</div>'
            f'<div class="contact">{contact}</div>'
            + "".join(section_html(s) for s in cv.get("sections", [])))
    return page(body)


def letter_html(letter, base_dir="."):
    paragraphs = "".join(f"<p>{e(p)}</p>" for p in letter["body"])
    signature = ""
    if letter.get("signature"):
        signature = f'<img class="signature" src="file://{os.path.abspath(os.path.join(base_dir, letter["signature"]))}" alt="">'
    body = (f'<h1>{e(letter["name"])}</h1><div class="contact">{e(letter["contact"])}</div>'
            f'<p class="meta">{e(letter["date"])}</p><p class="meta">{e(letter["to"])}</p>'
            f'<p class="re">{e(letter["re"])}</p>{paragraphs}'
            f'<p>{e(letter.get("closing", "Kind regards,"))}</p>{signature}<p>{e(letter["name"])}</p>')
    return page(body, "letter")


# ---------- PDF ----------

def to_pdf(html_text, out_path):
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(html_text)
    try:
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        "--allow-file-access-from-files", "--virtual-time-budget=8000",
                        f"--print-to-pdf={out_path}", f"file://{f.name}"],
                       stderr=subprocess.DEVNULL, check=True)
    finally:
        os.unlink(f.name)
    return out_path


def page_count(pdf_path):
    try:
        import pdfplumber
    except ImportError:
        return None
    with pdfplumber.open(pdf_path) as pdf:
        return len(pdf.pages)


def main():
    if len(sys.argv) != 4 or sys.argv[1] not in ("cv", "letter"):
        sys.exit(__doc__)
    kind, data_path, out_path = sys.argv[1:]
    with open(data_path) as f:
        data = json.load(f)
    base = os.path.dirname(os.path.abspath(data_path))
    html_text = cv_html(data, base) if kind == "cv" else letter_html(data, base)
    pdf = to_pdf(html_text, out_path)
    pages = page_count(pdf)
    print(f"saved {pdf}" + (f" ({pages} page{'s' if pages != 1 else ''})" if pages else ""))
    if pages and pages > 1:
        sys.exit("WARNING: more than one page. Shorten the content and render again.")


if __name__ == "__main__":
    main()
