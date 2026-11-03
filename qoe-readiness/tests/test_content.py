"""Tests for the owner-facing stage content in skill/core/ and the export steps."""
import json
import re
from pathlib import Path

import pytest

import progress

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "skill" / "core"
SCRIPTS = ROOT / "skill" / "scripts"
SLUG = {1: "learn", 2: "files", 3: "inventory", 4: "spot-check", 5: "workbook"}
SECTIONS = ["Purpose", "Steps for the model", "Owner text", "Gate"]
MAX_WORDS = 25
STAGE1_DISCLAIMER = ("A buyer or lender will commission an independent QoE. This workbook is your own "
                     "preparation for that QoE. LIVMO designed this skill and is not responsible for its output.")
SKIPPED_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".git"}


# ---- helpers -----------------------------------------------------------------

def stage_path(stage: int) -> Path:
    return CORE / f"stage-{stage}-{SLUG[stage]}.md"


def read_stage(stage: int) -> str:
    return stage_path(stage).read_text(encoding="utf-8")


def sections(md: str) -> dict[str, str]:
    """Split a core file into its '## ' sections, keyed by heading text."""
    parts = re.split(r"^## (.+)$", md, flags=re.M)
    return {parts[i].strip(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def sentences(text: str, skip_quotes: bool = False) -> list[str]:
    """Split markdown into sentences. A list item is its own unit. Code fences and headings are dropped."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    units: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        current: list[str] = []
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if skip_quotes and stripped.startswith(">"):
                continue
            if re.match(r"^([-*]|\d+\.)\s", stripped):
                if current:
                    units.append(" ".join(current))
                    current = []
                stripped = re.sub(r"^([-*]|\d+\.)\s+(\[[ x]\]\s+)?", "", stripped)
            current.append(stripped)
        if current:
            units.append(" ".join(current))
    out: list[str] = []
    for unit in units:
        unit = re.sub(r"https?://\S+", "URL", unit)
        out.extend(s for s in re.split(r"(?<=[.!?])\"?\s+(?=[A-Z0-9\"(`$])", unit) if s.strip())
    return out


def long_sentences(text: str, skip_quotes: bool = False) -> list[str]:
    return [s for s in sentences(text, skip_quotes) if len(s.split()) > MAX_WORDS]


# ---- fixtures ------------------------------------------------------------------

@pytest.fixture(scope="module")
def core_dir():
    return CORE


@pytest.fixture
def presets(data_dir):
    return json.loads((data_dir / "export_presets.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def all_repo_text():
    """Every text file under qoe-readiness/, tests included. Binary files are skipped."""
    out = {}
    for path in ROOT.rglob("*"):
        if not path.is_file() or SKIPPED_DIRS & set(path.relative_to(ROOT).parts):
            continue
        try:
            out[str(path.relative_to(ROOT))] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
    return out


@pytest.fixture(scope="module")
def core_owner_text():
    """The text the owner reads: the Owner text section of each stage file, and all of exports.md."""
    parts = [sections(read_stage(n))["Owner text"] for n in SLUG]
    parts.append((CORE / "exports.md").read_text(encoding="utf-8"))
    return "\n\n".join(parts)


# ---- naming and style ------------------------------------------------------------

def test_no_third_party_names(all_repo_text, denylist):
    if not denylist:
        pytest.skip("denylist file not found; it lives outside the repo on purpose")
    hits = [(p, w) for p, t in all_repo_text.items() for w in denylist if w in t.lower()]
    assert hits == []


def test_sentences_at_most_25_words(core_owner_text):
    assert long_sentences(core_owner_text) == []


@pytest.mark.parametrize("stage", list(SLUG))
def test_model_steps_sentences_at_most_25_words(stage):
    """Model instructions follow the same limit. Verbatim government quotes (lines that start with '>') are exempt."""
    body = "\n\n".join(sections(read_stage(stage))[name] for name in ("Purpose", "Steps for the model", "Gate"))
    assert long_sentences(body, skip_quotes=True) == []


def test_no_em_or_en_dashes_in_core():
    hits = [p.name for p in CORE.glob("*.md") if re.search("[–—]", p.read_text(encoding="utf-8"))]
    assert hits == []


@pytest.mark.parametrize("stage", list(SLUG))
def test_owner_text_has_no_code_quote_or_table(stage):
    owner = sections(read_stage(stage))["Owner text"]
    assert "```" not in owner
    assert not re.search(r"^\s*(>|\|)", owner, flags=re.M)


# ---- structure ---------------------------------------------------------------------

@pytest.mark.parametrize("stage", list(SLUG))
def test_stage_file_has_four_sections_in_order(stage):
    assert list(sections(read_stage(stage))) == SECTIONS


def test_gate_text_matches_code(data_dir):
    for stage in (1, 2, 3, 4):
        gate = sections(read_stage(stage))["Gate"]
        items = progress.gate_status(progress.new_state(), stage, data_dir)
        assert [f"- [ ] {item.text}" for item in items] == [
            line.strip() for line in gate.splitlines() if line.strip().startswith("- [ ]")]


def test_scripts_named_in_core_exist():
    for path in CORE.glob("*.md"):
        for name in re.findall(r"\b([a-z_]+\.py)\b", path.read_text(encoding="utf-8")):
            assert (SCRIPTS / name).is_file(), f"{path.name} names {name}"


def test_cli_flags_named_in_core_exist():
    source = "\n".join(p.read_text(encoding="utf-8") for p in SCRIPTS.glob("*.py"))
    for path in CORE.glob("*.md"):
        for flag in re.findall(r"(?<![\w-])(--[a-z][a-z-]+)", path.read_text(encoding="utf-8")):
            assert f'"{flag}"' in source, f"{path.name} names {flag}"


# ---- stage 1 --------------------------------------------------------------------------

def test_stage1_has_disclaimer(core_dir):
    assert STAGE1_DISCLAIMER in (core_dir / "stage-1-learn.md").read_text(encoding="utf-8")


def test_stage1_owner_text_covers_every_education_point():
    owner = sections(read_stage(1))["Owner text"].lower()
    for term in ("audit", "review", "compilation", "accrual", "tax return", "does not give an opinion",
                 "adjusted ebitda", "proof of cash", "proof of revenue", "revenue analysis",
                 "net working capital", "peg", "net debt", "debt-like", "sell-side", "buy-side",
                 "$3 million", "for the benefit of the lender", "retrade", "does not replace"):
        assert term in owner, term


def test_stage1_asks_every_intake_question(data_dir):
    steps = sections(read_stage(1))["Steps for the model"]
    assert "intake.json" in steps
    assert "required_when" in steps
    assert "disclaimer_acknowledged" in steps


def test_sba_claim_dated(core_dir):
    assert re.search(r"sba\.gov.*as of \d{4}-\d{2}-\d{2}",
                     (core_dir / "stage-1-learn.md").read_text(encoding="utf-8"), re.S)


def test_sba_record_has_required_wording():
    text = read_stage(1)
    for needle in ("SOP 50 10 8.1", "Quality of Earnings", "$3 million", "for the benefit of the Lender",
                   "October 1, 2026", "https://www.sba.gov/document/sop-50-10-lender-development-company-loan-programs",
                   "as of 2026-11-02"):
        assert needle in text, needle


# ---- stage 2 ----------------------------------------------------------------------------

def test_stage2_uses_catalog_and_module_rules():
    steps = sections(read_stage(2))["Steps for the model"]
    for needle in ("files.json", "active_modules", "modules_confirmed", "file_list_shown", "critical"):
        assert needle in steps, needle


# ---- stage 3 ------------------------------------------------------------------------------

def test_stage3_tells_the_model_how_to_store_and_convert():
    steps = sections(read_stage(3))["Steps for the model"]
    for needle in ("canonical_path", "absolute", "normalize_runs", "normalize_generic", "propose_account_map",
                   "apply_account_map", "account_map_confirmed", "meets_floor", "one export per month"):
        assert needle in steps, needle


def test_stage3_reads_pdfs_and_waits_for_owner_confirmation():
    steps = sections(read_stage(3))["Steps for the model"].lower()
    for needle in ("bank statement", "4 monthly totals", "gross receipts", "period-end", "after the owner confirms"):
        assert needle in steps, needle


def test_stage3_has_reason_codes_and_gap_help(data_dir):
    owner = sections(read_stage(3))["Owner text"].lower()
    steps = sections(read_stage(3))["Steps for the model"]
    for needle in ("never_kept", "unknown", "exports.md", "why_buyers_ask"):
        assert needle in steps, needle
    for needle in ("bookkeeper", "payroll", "bank"):
        assert needle in owner, needle


# ---- stage 4 -------------------------------------------------------------------------------

def test_stage4_runs_checks_and_passes_only_asked_answers():
    steps = sections(read_stage(4))["Steps for the model"]
    for needle in ("run_checks.py", "--answers", "model_review", "for review", "owner_question",
                   "only the answers", "fix", "explain", "accept"):
        assert needle in steps, needle


def test_stage4_owner_states_every_adjustment_amount():
    steps = sections(read_stage(4))["Steps for the model"]
    assert "never propose" in steps.lower()
    assert "owner states every amount" in steps.lower()
    for needle in ("owner_stated", "approved", "edited", "rejected", "amounts"):
        assert needle in steps, needle


# ---- stage 5 and cash basis -----------------------------------------------------------------

def test_stage5_builds_workbook_and_shows_summary():
    steps = sections(read_stage(5))["Steps for the model"]
    for needle in ("build_workbook.py", "--state", "--canonical", "--out", "top_findings", "reported_ebitda",
                   "adjusted_ebitda", "next_step", "gate_passed"):
        assert needle in steps, needle


@pytest.mark.parametrize("stage", [3, 4, 5])
def test_cash_basis_owner_gets_the_accrual_finding_explained(stage):
    text = read_stage(stage).lower()
    assert "cash basis" in text
    assert "k21" in text


# ---- exports.md -------------------------------------------------------------------------------

def test_exports_cover_every_preset(core_dir, presets):
    md = (core_dir / "exports.md").read_text(encoding="utf-8")
    assert all(p["report_name"] in md for s in presets.values() for p in s.values())


def test_exports_repeat_every_menu_path_and_setting(core_dir, presets):
    md = (core_dir / "exports.md").read_text(encoding="utf-8")
    for system in presets.values():
        for preset in system.values():
            assert preset["menu_path"] in md
            assert all(setting in md for setting in preset["settings"])


def test_exports_say_columns_are_not_confirmed(core_dir):
    md = (core_dir / "exports.md").read_text(encoding="utf-8").lower()
    assert "not yet confirmed" in md
    assert "tell the skill" in md
    assert "missing" in md


def test_exports_advise_csv_for_quickbooks_desktop(core_dir):
    md = (core_dir / "exports.md").read_text(encoding="utf-8")
    assert "comma separated values" in md
    assert "CSV over Excel" in md


def test_exports_name_per_month_runs_for_xero(core_dir):
    md = (core_dir / "exports.md").read_text(encoding="utf-8").lower()
    assert "one export for each month" in md
