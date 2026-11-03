"""Tests for the QoE readiness guidebook: HTML, brand reuse, content rules, and the PDF."""
import html as html_lib
import json
import re
import shutil
from pathlib import Path

import pdfplumber
import pytest

import build_guidebook
from test_content import long_sentences

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
GUIDEBOOK_HTML = ROOT / "guidebook" / "qoe-readiness-guidebook.html"
GUIDEBOOK_PDF = ROOT / "guidebook" / "qoe-readiness-guidebook.pdf"
CHECKLIST_HTML = (REPO / "saas" / "saas-sellability-checklist" / "detailed"
                  / "saas-sellability-checklist-1-under-500k-arr.html")
STAGE_1 = ROOT / "skill" / "core" / "stage-1-learn.md"
INSTALL_STEPS = ROOT / "tools" / "install-steps.md"
START_TEXT = ("This skill was designed by LIVMO. LIVMO is not responsible for its output. "
              "You supply the files and approve every number, and the results are yours. "
              "The skill helps you prepare for a Quality of Earnings report. "
              "It does not replace one, and it gives no tax, legal, or accounting advice.")
CTA_LINK = "https://calendly.com/khaledazar/exit-builder"
SBA_URL = "https://www.sba.gov/document/sop-50-10-lender-development-company-loan-programs"
# Dollar amounts the guidebook may show. Each comes from the SBA record or from a check threshold.
ALLOWED_DOLLARS = {"$3 million", "$100"}
FOOTER_SIZE_PT = 8.5  # footer text is set at 10.5px, about 7.9pt; body text is larger
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


# ---- helpers -----------------------------------------------------------------

def style_block(text: str) -> str:
    match = re.search(r"<style>.*?</style>", text, flags=re.S)
    assert match, "no style block"
    return match.group(0)


def page_sections(text: str) -> list[str]:
    return re.findall(r'<section class="page.*?</section>', text, flags=re.S)


def logo_sources(text: str) -> set[str]:
    return set(re.findall(r'<img src="(data:image/png;base64,[^"]+)"', text))


def visible_text(text: str) -> str:
    """The text a reader sees: no style block, no tags; block ends become line breaks."""
    text = re.sub(r"<style>.*?</style>", "", text, flags=re.S)
    text = re.sub(r"</(div|p|li|h\d|section|ul|ol|blockquote)>|<br\s*/?>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html_lib.unescape(text)


def knowledge_file_count() -> int:
    skill = ROOT / "skill"
    return sum(1 for d in ("core", "data", "scripts") for p in (skill / d).iterdir()
               if p.is_file() and p.suffix != ".pyc")


# ---- fixtures ------------------------------------------------------------------

@pytest.fixture(scope="module")
def html():
    return GUIDEBOOK_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def checklist_html():
    return CHECKLIST_HTML.read_text(encoding="utf-8")


@pytest.fixture
def files(data_dir):
    return json.loads((data_dir / "files.json").read_text(encoding="utf-8"))


@pytest.fixture
def checks(data_dir):
    return json.loads((data_dir / "checks.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def pdf_path():
    return GUIDEBOOK_PDF


# ---- brand and structure ---------------------------------------------------------

def test_guidebook_reuses_checklist_style(html, checklist_html):
    assert style_block(html) == style_block(checklist_html)


def test_guidebook_reuses_checklist_logos(html, checklist_html):
    assert logo_sources(html) and logo_sources(html) <= logo_sources(checklist_html)


def test_guidebook_page_order(html):
    titles = [re.search(r'class="title[^"]*"[^>]*>(.*?)</div>', p, flags=re.S).group(1)
              for p in page_sections(html)]
    plain = [re.sub(r"<[^>]+>", "", t) for t in titles]
    expected = ["QoE Readiness Guidebook", "What a QoE is", "QoE compared with other reports", "Why now",
                "The files buyers ask for", "The files buyers ask for", "The files buyers ask for",
                "What the spot checks look for", "How to run the skill", "Next step"]
    assert plain == expected


def test_guidebook_pages_use_checklist_classes(html):
    sections = page_sections(html)
    assert all(re.match(r'<section class="page g-(ink|white|cream|ocean)"', s) for s in sections)
    assert all('class="pageno"' in s for s in sections[1:])


def test_build_reproduces_committed_html(tmp_path, html):
    out = build_guidebook.build(REPO, tmp_path / "guidebook.html")
    assert out.read_text(encoding="utf-8") == html


# ---- content ----------------------------------------------------------------------

def test_guidebook_lists_every_file(html, files):
    text = html_lib.unescape(html)
    assert all(f["name"] in text for f in files)
    assert all(f["id"] in text for f in files)


def test_guidebook_gives_why_buyers_ask_for_every_file(html, files):
    text = html_lib.unescape(html)
    assert all(f["why_buyers_ask"] in text for f in files)


def test_guidebook_lists_every_spot_check(html, checks):
    text = html_lib.unescape(html)
    assert all(c["name"] in text for c in checks)


def test_guidebook_liability_on_every_page(html):
    pages = page_sections(html)
    assert len(pages) >= 8 and all("LIVMO is not responsible" in p for p in pages)


def test_guidebook_start_text_on_every_page(html):
    pages = [visible_text(p) for p in page_sections(html)]
    assert all(START_TEXT in re.sub(r"\s+", " ", p) for p in pages)


def test_guidebook_links_the_exit_assessment(html):
    assert f'href="{CTA_LINK}"' in html


def test_guidebook_license_named(html):
    assert "CC BY-NC-ND 4.0" in html


def test_guidebook_sentences_at_most_25_words(html):
    assert long_sentences(visible_text(html)) == []


def test_guidebook_has_no_em_or_en_dashes(html):
    assert not re.search("[\u2013\u2014]", html)


def test_guidebook_sba_quotes_come_from_the_record(html):
    """Each SBA quote on the guidebook sits word for word in the Stage 1 source record."""
    record = re.sub(r"\s+", " ", STAGE_1.read_text(encoding="utf-8"))
    quotes = re.findall(r'<blockquote[^>]*>(.*?)</blockquote>', html, flags=re.S)
    assert quotes
    for quote in quotes:
        assert re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", "", quote))).strip() in record


def test_guidebook_sba_claims_are_dated_and_cited(html):
    text = visible_text(html)
    assert "as of 2026-11-02" in text
    assert SBA_URL in html
    assert "SOP 50 10 8.1" in text


def test_guidebook_gives_no_cost_or_time_figures(html):
    text = visible_text(html)
    amounts = set(re.findall(r"\$\d[\d,]*(?: million)?", text))
    assert amounts <= ALLOWED_DOLLARS
    assert not re.search(r"\b\d+\s*(?:weeks?|days?)\b", text.replace("90 days", ""))


# ---- install steps ----------------------------------------------------------------

def test_install_steps_have_three_routes():
    steps = build_guidebook.load_install_steps(INSTALL_STEPS)
    assert list(steps) == ["Claude.ai", "Claude Code", "ChatGPT custom GPT"]
    assert all(len(v) >= 3 for v in steps.values())


def test_install_steps_name_the_artifacts():
    steps = build_guidebook.load_install_steps(INSTALL_STEPS)
    assert any("dist/qoe-readiness-skill.zip" in s for s in steps["Claude.ai"])
    assert any("~/.claude/skills/qoe-readiness/" in s for s in steps["Claude Code"])
    gpt = " ".join(steps["ChatGPT custom GPT"])
    assert "gpt-instructions.md" in gpt and "Code Interpreter" in gpt


def test_install_steps_count_matches_knowledge_files():
    gpt = " ".join(build_guidebook.load_install_steps(INSTALL_STEPS)["ChatGPT custom GPT"])
    assert f"{knowledge_file_count()} knowledge files" in gpt
    assert knowledge_file_count() == 19


def test_install_steps_sentences_at_most_25_words():
    text = INSTALL_STEPS.read_text(encoding="utf-8")
    assert long_sentences(text) == []
    assert not re.search("[\u2013\u2014]", text)


def test_guidebook_shows_every_install_step(html):
    text = visible_text(html)
    for steps in build_guidebook.load_install_steps(INSTALL_STEPS).values():
        for step in steps:
            assert re.sub(r"[`]", "", step) in text


# ---- PDF ----------------------------------------------------------------------------

def test_pdf_pages(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        assert len(pdf.pages) >= 8


def test_pdf_has_one_page_per_section(pdf_path, html):
    with pdfplumber.open(pdf_path) as pdf:
        assert len(pdf.pages) == len(page_sections(html))


def test_pdf_liability_on_every_page(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        texts = [re.sub(r"\s+", " ", p.extract_text() or "") for p in pdf.pages]
    assert all("LIVMO is not responsible" in t for t in texts)


def test_pdf_footer_is_clear_of_content(pdf_path):
    """On every page the lowest body word sits above the top of the footer text."""
    with pdfplumber.open(pdf_path) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(extra_attrs=["size"])
            footer = [w for w in words if w["size"] < FOOTER_SIZE_PT]
            body = [w for w in words if w["size"] >= FOOTER_SIZE_PT and w["text"] != str(number)]
            assert footer, f"page {number} has no footer"
            top = min(w["top"] for w in footer)
            overlap = [w["text"] for w in body if w["bottom"] > top - 4]
            assert overlap == [], f"page {number} body text reaches the footer: {overlap[:5]}"


def test_pdf_text_stays_inside_the_page(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            words = page.extract_words()
            assert all(0 <= w["x0"] and w["x1"] <= page.width + 0.5 and w["bottom"] <= page.height
                       for w in words), f"page {number} has text outside the page"


@pytest.mark.skipif(not CHROME.is_file(), reason="Chrome is not installed here")
def test_to_pdf_writes_a_pdf(tmp_path):
    html_copy = tmp_path / "guidebook.html"
    shutil.copyfile(GUIDEBOOK_HTML, html_copy)
    out = build_guidebook.to_pdf(html_copy, tmp_path / "guidebook.pdf")
    with pdfplumber.open(out) as pdf:
        assert len(pdf.pages) == len(page_sections(html_copy.read_text(encoding="utf-8")))
