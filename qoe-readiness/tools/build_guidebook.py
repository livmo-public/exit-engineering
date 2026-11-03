"""Build the QoE readiness guidebook (HTML and PDF) in the LIVMO checklist brand template.

The style block and the two logo images come from the SaaS Sellability Checklist, byte for byte.
Page text comes from skill/core/stage-1-learn.md, skill/data/files.json, skill/data/checks.json,
and tools/install-steps.md. The PDF comes from headless Chrome.

Usage: python tools/build_guidebook.py [--no-pdf]
"""
import argparse
import html
import json
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPO = ROOT.parent
CHECKLIST = Path("saas/saas-sellability-checklist/detailed/saas-sellability-checklist-1-under-500k-arr.html")
DATA = Path("qoe-readiness/skill/data")
INSTALL_STEPS = ROOT / "tools" / "install-steps.md"
OUT_HTML = ROOT / "guidebook" / "qoe-readiness-guidebook.html"
OUT_PDF = ROOT / "guidebook" / "qoe-readiness-guidebook.pdf"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")

START_TEXT = ("This skill was designed by LIVMO. LIVMO is not responsible for its output. "
              "You supply the files and approve every number, and the results are yours. "
              "The skill helps you prepare for a Quality of Earnings report. "
              "It does not replace one, and it gives no tax, legal, or accounting advice.")
CTA_LINK = "https://calendly.com/khaledazar/exit-builder"
SBA_URL = "https://www.sba.gov/document/sop-50-10-lender-development-company-loan-programs"
PAGE_SIZE_PX = (816, 1056)

# Footer text colour for each page background.
FOOTER_COLOR = {"ink": "var(--ocean-200)", "ocean": "var(--white)", "white": "var(--gray-600)",
                "cream": "var(--gray-600)"}
DARK = {"ink", "ocean"}

# ---- owner text (education text from skill/core/stage-1-learn.md) ------------------

QOE_INTRO = [
    "A Quality of Earnings report, or QoE, is an analysis of a company's earnings. It tests whether the earnings repeat.",
    "A buyer or a lender can rely on it. An independent analyst builds it from your bank, ledger, and tax records.",
    "A QoE does not give an opinion on your financial statements. It asks one question: how much profit will this business keep earning?",
]
QOE_PRODUCES = [
    ("Adjusted EBITDA bridge.", "EBITDA is earnings before interest, taxes, depreciation, and amortization. The bridge starts at net income. It adds or removes one-time and personal items to reach adjusted EBITDA."),
    ("Proof of cash.", "This tests that the cash in your books matches the bank, month by month."),
    ("Proof of revenue.", "This tests that the revenue in your books matches your sales records and bank deposits."),
    ("Revenue analysis.", "This shows revenue trends, customer concentration, and customer counts. For a SaaS business it also shows recurring revenue and retention."),
    ("Net working capital (NWC) and the peg.", "NWC is receivables, inventory, and other short-term items, minus payables and other short-term debts. The peg is the normal level of NWC. The seller leaves that level in the business."),
    ("Net debt and debt-like items.", "These are loans and other obligations that reduce what the buyer pays you."),
]
SELL_SIDE = ("Sell-side QoE", "The seller orders it. It helps you find and fix problems before buyers see them.")
BUY_SIDE = ("Buy-side QoE", "The buyer or the buyer's lender orders it. It tests what the seller claims.")
SELL_VS_BUY = "A sell-side report does not replace a buy-side report."

COMPARISON = [
    ("Audit", "An audit is a full test of your financial statements. The auditor gives an opinion on them."),
    ("Review", "A review is a lighter check. The accountant asks questions and looks for numbers that seem off."),
    ("Compilation", "A compilation has the least work. The accountant formats your numbers into statements and checks nothing."),
    ("Bookkeeping", "Accrual bookkeeping records income when you earn it and costs when you incur them. It is a way to keep books. It is not a report on them."),
    ("Tax return", "A tax return reports income by tax rules. Those rules can differ from how you keep your books."),
]
COMPARISON_CLOSE = "A QoE sits on top of these. It starts from your books and tests them against the bank and the tax return."

SBA_LEAD = ("The SBA has a new rule for 7(a) loans. It is in SOP 50 10 8.1 and it takes effect on October 1, 2026.")
SBA_POINTS = [
    "For an initial acquisition or a business expansion, the rule applies at a price of $3 million or more.",
    "The SBA sets the $3 million line before buyer equity, seller debt, or other financing. The price does not include owner-occupied real estate.",
    "In that case the lender must obtain a QoE. It must be done for the benefit of the lender.",
    "The lender uses the QoE earnings to test the loan. If those earnings do not support the valuation and the debt structure, the lender must reduce the loan amount.",
    "The SBA says an owner buyout does not need a QoE.",
    "In an SBA deal, the loan can include QoE costs among the borrower's out-of-pocket costs.",
    "A buyer may commission a QoE first. The lender may then have its own vendor review that report.",
]
# Word for word from the SOP, as recorded in skill/core/stage-1-learn.md.
SBA_QUOTE = ("The QoE must be performed by an independent, experienced financial professional and must be "
             "conducted for the benefit of the Lender. As the QoE report is part of the financial due diligence "
             "of the transaction, the report must not be prepared by or for the seller.")
SBA_SOURCE = "SBA SOP 50 10 8.1 on sba.gov, as of 2026-11-02."

FILES_LEAD = {
    1: "A critical file is a file the workbook needs. The hard floor is C1, C2, and either C3 or C4.",
    2: "A recommended file helps, but its absence does not stop the work.",
    3: "The S files are for a SaaS business. The P files are for a business that sells products or runs projects.",
}
FILE_PAGES = [
    ("Critical files", lambda f: f["module"] == "core" and f["critical"]),
    ("Recommended files", lambda f: f["module"] == "core" and not f["critical"]),
    ("SaaS and product files", lambda f: f["module"] in ("saas", "product")),
]

SPOT_LEAD = "A spot check tests your files for errors that a buyer's QoE will find. Each check gives a result in plain words and a fix. A SaaS tag marks a check for SaaS businesses."
SPOT_GROUPS = [
    ("hygiene", "Hygiene", "Your books hold an error to fix. An example is a bank balance that does not match the books."),
    ("risk", "Risk", "Your books are correct, and a buyer will still discount for the fact. An example is one customer paying for a large share of revenue."),
]
SPOT_LIMITS = ("Each check uses a fixed limit. Bank cash must tie to the balance sheet within $100. "
               "Revenue must tie within 5%. A receivable older than 90 days needs a note.")
SPOT_RESPONSES = ("For each critical or high finding, you pick one response: fix now, explain, or accept. "
                  "A fix before the sale is a change you made. A finding a buyer discovers is a reason to cut the price.")

RUN_LEAD = ("The skill lists the files a QoE firm asks for, and checks them for errors. It builds an Excel workbook with live formulas. "
            "The workbook also opens in Google Sheets.")
RUN_NOT = "The skill does not produce a QoE. It gives no valuation. It does not connect to your accounting system. It processes your files only inside the chat."

NEXT_LEAD = "A buyer who finds a problem in diligence cuts the price. The industry calls this a retrade."
NEXT_BODY = ("You can fix many of the same problems before you list the business. A fix you make is a change in how you run the business. "
             "A problem a buyer finds is a reason to pay less.")
CTA_TEXT = "Book a 30-minute exit assessment with LIVMO. We review what you found and talk through your sale."
CTA_BUTTON = "Book a 30-Minute Exit Assessment"
LIVMO_LINE = "LIVMO is a tech-focused M&A advisory in San Diego."
LICENSE_LINE = "This guidebook is licensed under CC BY-NC-ND 4.0."


# ---- source readers -----------------------------------------------------------------

def read_checklist(repo_root: Path) -> str:
    return (Path(repo_root) / CHECKLIST).read_text(encoding="utf-8")


def extract_style(checklist: str) -> str:
    """The checklist style block, byte for byte."""
    match = re.search(r"<style>.*?</style>", checklist, flags=re.S)
    if not match:
        raise ValueError("checklist has no style block")
    return match.group(0)


def extract_logos(checklist: str) -> dict[str, str]:
    """The data URI of the logo for light pages and for dark pages, from the checklist cover and first page."""
    dark = re.search(r'<div class="cover-logo"><img src="(data:image/png;base64,[^"]+)"', checklist)
    light = re.search(r'<section class="page g-white"><div class="logo"><img src="(data:image/png;base64,[^"]+)"',
                      checklist)
    if not (dark and light):
        raise ValueError("checklist logos not found")
    return {"dark": dark.group(1), "light": light.group(1)}


def load_json(repo_root: Path, name: str) -> list[dict]:
    return json.loads((Path(repo_root) / DATA / name).read_text(encoding="utf-8"))


def load_install_steps(path: Path = INSTALL_STEPS) -> dict[str, list[str]]:
    """Read tools/install-steps.md: one '## ' heading per route, one numbered line per step."""
    routes: dict[str, list[str]] = {}
    current = None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            routes[current] = []
        elif current and (match := re.match(r"\d+\.\s+(.*)", line)):
            routes[current].append(match.group(1).strip())
    return routes


# ---- html pieces ----------------------------------------------------------------------

def esc(text: str) -> str:
    return html.escape(text, quote=True)


def inline(text: str) -> str:
    """Escape text and turn `code` spans into <code> tags."""
    parts = re.split(r"`([^`]+)`", text)
    out = []
    for i, part in enumerate(parts):
        if i % 2:
            out.append(f'<code style="font-family:Consolas,monospace;font-size:.92em;'
                       f'background:var(--gray-100);padding:0 4px">{esc(part)}</code>')
        else:
            out.append(esc(part))
    return "".join(out)


def footer(background: str) -> str:
    return (f'<div style="position:absolute;left:64px;right:132px;bottom:22px;font-size:10.5px;line-height:1.35;'
            f'color:{FOOTER_COLOR[background]}">{esc(START_TEXT)}</div>')


def page(background: str, logos: dict[str, str], number: int, body: str, cover: bool = False) -> str:
    dark = background in DARK
    logo_src = logos["dark" if dark else "light"]
    if cover:
        top = f'<div class="cover-logo"><img src="{logo_src}" alt="LIVMO"></div>'
        style = ' style="padding-top:64px"'
        pageno = ""
    else:
        top = f'<div class="logo"><img src="{logo_src}" alt="LIVMO"></div>'
        style = ""
        pageno = f'<div class="pageno">{number}</div>'
    return (f'<section class="page g-{background}"{style}>{top}\n{body}\n'
            f'{footer(background)}{pageno}</section>')


def title(text: str, small: bool = True) -> str:
    style = ' style="font-size:40px;margin-bottom:12px;max-width:640px"' if small else ""
    return f'<div class="title"{style}>{esc(text)}</div>'


def overline(text: str) -> str:
    return f'<div class="overline">{esc(text)}</div>'


def lead(text: str, style: str = "") -> str:
    return f'<div class="lead" style="margin-bottom:16px;font-size:18px;{style}">{esc(text)}</div>'


def para(text: str, style: str = "") -> str:
    return f'<p style="font-size:16px;line-height:1.5;margin-bottom:10px;{style}">{esc(text)}</p>'


def kv(heading: str, text: str) -> str:
    return f'<div class="kv" style="margin-bottom:14px"><h3>{esc(heading)}</h3><p>{esc(text)}</p></div>'


# ---- pages ----------------------------------------------------------------------------

def cover_page(logos: dict[str, str]) -> str:
    body = (
        f'<div class="title" style="font-size:72px;max-width:640px">QoE Readiness Guidebook</div>\n'
        f'<div class="lead" style="font-size:24px;max-width:600px">Prepare your files for a Quality of Earnings report before a buyer asks.</div>\n'
        f'<div class="panel panel-ink" style="margin-top:32px;max-width:640px"><h3>Read this first</h3>'
        f'<p style="font-size:16px">{esc(START_TEXT)}</p></div>\n'
        f'<p style="color:var(--ocean-200);font-size:14px;margin-top:24px">{esc(LICENSE_LINE)}</p>'
        f'<div class="dots"></div>'
    )
    return page("ink", logos, 1, body, cover=True)


def what_is_page(logos: dict[str, str]) -> str:
    produces = "".join(
        f'<li style="padding:5px 0"><b style="color:var(--ink-900)">{esc(label)}</b> {esc(text)}</li>'
        for label, text in QOE_PRODUCES)
    body = (
        f'{title("What a QoE is")}\n'
        f'{lead(QOE_INTRO[0])}'
        f'{para(QOE_INTRO[1])}{para(QOE_INTRO[2])}\n'
        f'<h3 style="margin-top:14px">What a QoE produces</h3><ul class="plain">{produces}</ul>\n'
        f'<div class="cols" style="margin-top:18px"><div>{kv(*SELL_SIDE)}</div><div>{kv(*BUY_SIDE)}</div></div>\n'
        f'<p style="font-size:15px;color:var(--ocean-600);font-weight:600">{esc(SELL_VS_BUY)}</p>'
    )
    return page("white", logos, 2, body)


def compare_page(logos: dict[str, str]) -> str:
    items = "".join(kv(h, t) for h, t in COMPARISON)
    body = (
        f'{overline("Audit, review, compilation, bookkeeping, tax return")}'
        f'{title("QoE compared with other reports")}\n'
        f'{lead("Each report answers a different question about your numbers.")}\n'
        f'{items}\n'
        f'<div class="panel panel-cream"><h3>Where a QoE fits</h3><p>{esc(COMPARISON_CLOSE)}</p></div>'
    )
    return page("cream", logos, 3, body)


def sba_page(logos: dict[str, str]) -> str:
    points = "".join(f'<li style="padding:6px 0">{esc(t)}</li>' for t in SBA_POINTS)
    body = (
        f'{overline("The SBA rule")}{title("Why now")}\n'
        f'{lead(SBA_LEAD)}\n'
        f'<ul class="plain">{points}</ul>\n'
        f'<div class="panel panel-ink" style="margin-top:20px"><blockquote style="font-size:15px;line-height:1.45;'
        f'font-style:italic;color:var(--cream-50)">{esc(SBA_QUOTE)}</blockquote>'
        f'<p style="margin-top:8px;font-size:13px">{esc(SBA_SOURCE)} '
        f'<a href="{SBA_URL}" style="color:var(--sky-400)">{esc(SBA_URL)}</a></p></div>'
    )
    return page("ocean", logos, 4, body)


def file_item(entry: dict) -> str:
    return (
        f'<div class="item" style="padding:7px 0"><div class="pts" style="width:40px;text-align:left;margin-top:1px">'
        f'{esc(entry["id"])}</div><div class="it"><div class="t" style="display:flex;justify-content:space-between;gap:16px">'
        f'<div>{esc(entry["name"])}</div>'
        f'<div style="font-size:12.5px;font-weight:500;color:var(--ocean-600);text-align:right;max-width:230px">'
        f'{esc(entry["period"])}</div></div>'
        f'<div class="why" style="font-size:13.5px;line-height:1.38">{esc(entry["why_buyers_ask"])}</div></div></div>'
    )


def files_page(logos: dict[str, str], number: int, part: int, entries: list[dict]) -> str:
    heading, _ = FILE_PAGES[part - 1]
    background = ("white", "cream", "white")[part - 1]
    body = (
        f'{overline(f"Files and why buyers ask, part {part} of 3")}'
        f'{title("The files buyers ask for")}\n'
        f'<div class="lead" style="font-size:16px;margin-bottom:8px"><b style="color:var(--ink-900)">{esc(heading)}.</b> '
        f'{esc(FILES_LEAD[part])}</div>\n'
        f'{"".join(file_item(e) for e in entries)}'
    )
    return page(background, logos, number, body)


def spot_item(check: dict) -> str:
    tag = (' <span class="pill pill-sky" style="font-size:12px;padding:0 8px">SaaS</span>'
           if check["module"] == "saas" else "")
    return f"<li>{esc(check['name'])}{tag}</li>"


def spot_group(label: str, definition: str, rows: list[str]) -> str:
    half = (len(rows) + 1) // 2
    columns = "".join(f'<div><ul class="plain">{"".join(part)}</ul></div>' for part in (rows[:half], rows[half:]) if part)
    return (f'<div class="kv" style="margin-bottom:14px"><h3>{esc(label)}</h3>'
            f'<p style="margin-bottom:6px">{esc(definition)}</p><div class="cols" style="gap:32px">{columns}</div></div>')


def spot_page(logos: dict[str, str], number: int, checks: list[dict]) -> str:
    groups = [spot_group(label, definition, [spot_item(c) for c in checks if c["category"] == category])
              for category, label, definition in SPOT_GROUPS]
    body = (
        f'{title("What the spot checks look for")}\n'
        f'{lead(SPOT_LEAD, "font-size:17px")}\n'
        f'{"".join(groups)}\n'
        f'<div class="panel panel-cream" style="margin-top:12px"><p>{esc(SPOT_LIMITS)}</p>'
        f'<p style="margin-top:6px">{esc(SPOT_RESPONSES)}</p></div>'
    )
    return page("cream", logos, number, body)


def run_page(logos: dict[str, str], number: int, steps: dict[str, list[str]]) -> str:
    blocks = []
    for route, items in steps.items():
        rows = "".join(f'<li style="padding:4px 0"><b style="color:var(--ocean-600)">{i}</b>&nbsp; {inline(s)}</li>'
                       for i, s in enumerate(items, start=1))
        blocks.append(f'<div class="kv" style="margin-bottom:12px"><h3>{esc(route)}</h3><ul class="plain">{rows}</ul></div>')
    body = (
        f'{title("How to run the skill")}\n'
        f'{lead(RUN_LEAD, "font-size:16px")}'
        f'{"".join(blocks)}\n'
        f'<p style="font-size:14px">{esc(RUN_NOT)}</p>'
    )
    return page("white", logos, number, body)


def next_page(logos: dict[str, str], number: int) -> str:
    body = (
        f'{title("Next step")}\n'
        f'{lead(NEXT_LEAD)}\n'
        f'<p style="color:var(--cream-50)">{esc(NEXT_BODY)}</p>\n'
        f'<p style="color:var(--cream-50);margin-top:12px">{esc(CTA_TEXT)}</p>\n'
        f'<a class="btn" href="{CTA_LINK}">{esc(CTA_BUTTON)}</a>\n'
        f'<p style="color:var(--ocean-200);font-size:15px"><a href="{CTA_LINK}" style="color:var(--ocean-200)">'
        f'calendly.com/khaledazar/exit-builder</a></p>\n'
        f'<div class="cred">{esc(LIVMO_LINE)}</div>\n'
        f'<div class="dots"></div>'
    )
    return page("ink", logos, number, body)


# ---- build -----------------------------------------------------------------------------

def build(repo_root: Path, out_html: Path) -> Path:
    """Write the guidebook HTML to out_html and return the path."""
    repo_root, out_html = Path(repo_root), Path(out_html)
    checklist = read_checklist(repo_root)
    style, logos = extract_style(checklist), extract_logos(checklist)
    files, checks = load_json(repo_root, "files.json"), load_json(repo_root, "checks.json")
    steps = load_install_steps()

    pages = [cover_page(logos), what_is_page(logos), compare_page(logos), sba_page(logos)]
    for part, (_, keep) in enumerate(FILE_PAGES, start=1):
        pages.append(files_page(logos, len(pages) + 1, part, [f for f in files if keep(f)]))
    pages.append(spot_page(logos, len(pages) + 1, checks))
    pages.append(run_page(logos, len(pages) + 1, steps))
    pages.append(next_page(logos, len(pages) + 1))

    document = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                '<title>QoE Readiness Guidebook</title>\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                f'{style}</head>\n<body>{"".join(pages)}</body></html>\n')
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(document, encoding="utf-8", newline="\n")
    return out_html


def to_pdf(html_path: Path, pdf: Path, chrome: Path = CHROME) -> Path:
    """Print html_path to pdf with headless Chrome, without header and footer."""
    html_path, pdf = Path(html_path).resolve(), Path(pdf).resolve()
    if not Path(chrome).is_file():
        raise FileNotFoundError(f"Chrome not found at {chrome}")
    pdf.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(
            [str(chrome), "--headless", "--disable-gpu", f"--user-data-dir={profile}",
             "--no-pdf-header-footer", f"--print-to-pdf={pdf}", html_path.as_uri()],
            check=True, capture_output=True, timeout=180)
    if not pdf.is_file():
        raise RuntimeError("Chrome did not write the PDF")
    return pdf


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the QoE readiness guidebook.")
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO, help="repository root")
    parser.add_argument("--html", type=Path, default=OUT_HTML, help="HTML file to write")
    parser.add_argument("--pdf", type=Path, default=OUT_PDF, help="PDF file to write")
    parser.add_argument("--no-pdf", action="store_true", help="write the HTML only")
    args = parser.parse_args()
    out = build(args.repo, args.html)
    print(out)
    if not args.no_pdf:
        print(to_pdf(out, args.pdf))


if __name__ == "__main__":
    main()
