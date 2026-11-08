"""Tests for the repo docs and licenses (Task 12): the QoE README, the root README and LICENSE, the skill and tools licenses."""
import re
import zipfile
from pathlib import Path

import pytest

from test_content import long_sentences

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
README = ROOT / "README.md"
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")
START_TEXT = ("This skill was designed by LIVMO. LIVMO is not responsible for its output. You supply the files "
              "and approve every number, and the results are yours. The skill helps you prepare for a Quality of "
              "Earnings report. It does not replace one, and it gives no tax, legal, or accounting advice.")
ROOT_README_ROW = ("| [QoE Readiness](qoe-readiness/) | SaaS and small business owners before a sale or an "
                   "SBA-financed deal | Are my books ready for a Quality of Earnings report? |")
MIT_COPYRIGHT = "Copyright (c) 2026 LIVMO"

def md_links(path: Path) -> list[str]:
    """Return the local link targets of a markdown file, without anchors. Web links are skipped."""
    text = path.read_text(encoding="utf-8")
    targets = [t.split("#")[0] for t in LINK.findall(text) if not t.startswith(("http://", "https://", "mailto:"))]
    return [t for t in targets if t]


def readme_text() -> str:
    return README.read_text(encoding="utf-8")


def test_readme_links_resolve(qoe_root):
    links = md_links(qoe_root / "README.md")
    assert links, "the README should link its files"
    for link in links:
        assert (qoe_root / link).exists(), link


def test_readme_file_table_links_the_three_deliverables(qoe_root):
    links = set(md_links(qoe_root / "README.md"))
    assert "guidebook/qoe-readiness-guidebook.pdf" in links
    assert "dist/qoe-readiness-skill.zip" in links
    assert "examples/sample-saas-co/qoe-readiness-workbook.xlsx" in links


def test_readme_has_the_start_text_verbatim():
    assert START_TEXT in " ".join(readme_text().split())


def test_readme_install_steps_match_install_steps_file():
    steps = [ln for ln in (ROOT / "tools" / "install-steps.md").read_text(encoding="utf-8").splitlines()
             if re.match(r"^\d+\. ", ln)]
    assert len(steps) == 12
    text = readme_text()
    for step in steps:
        assert step in text, step
    # The routes are '##' in install-steps.md and '###' under '## Install' in the README.
    source = (ROOT / "tools" / "install-steps.md").read_text(encoding="utf-8")
    routes = re.findall(r"^## (.+)$", source, flags=re.M)
    assert routes == ["Claude.ai", "Claude Code", "ChatGPT custom GPT"]
    install = text.split("\n## Install\n", 1)[1].split("\n## ", 1)[0]
    assert re.findall(r"^### (.+)$", install, flags=re.M) == routes
    assert re.match(r"\s*### ", install), "the Install section opens with its first route"


def test_readme_and_install_steps_describe_the_start_text_as_an_instruction():
    for path in (README, ROOT / "tools" / "install-steps.md"):
        text = path.read_text(encoding="utf-8")
        assert "shows its start text first" not in text, path.name
        assert "shows this text first" not in text, path.name
    assert "instruct" in " ".join(readme_text().split()).split("## Files")[0]


def test_readme_says_the_sample_is_synthetic_and_paths_are_relative():
    text = " ".join(readme_text().split())
    assert "Sample SaaS Co." in text
    assert "synthetic" in text
    assert "relative to the `qoe-readiness/` folder" in text
    assert "run the sample commands from there" in text.lower()


def test_readme_sample_command_points_at_real_files():
    text = readme_text()
    assert "skill/scripts/build_workbook.py" in text
    assert (ROOT / "skill" / "scripts" / "build_workbook.py").is_file()
    assert "examples/sample-saas-co/progress.json" in text
    assert (ROOT / "examples" / "sample-saas-co" / "progress.json").is_file()


def test_readme_lists_the_checks_before_you_rely_on_it():
    text = " ".join(readme_text().split())
    assert "## Before you rely on it" in text
    assert "Google Sheets" in text
    assert "real export from each accounting system" in text
    assert "column layouts are not yet confirmed" in text.lower()
    assert "Skills upload location" in text
    assert "No live run in Claude.ai or ChatGPT has been done yet" in text
    assert "scripted dry run" in text


def test_readme_has_the_license_line():
    text = readme_text()
    assert "## License" in text
    assert "CC BY-NC-ND 4.0" in text
    assert "MIT" in text


def test_readme_sentences_at_most_25_words():
    # Each table cell is its own paragraph; the sentence splitter treats a table as one block otherwise.
    def cells(match: re.Match) -> str:
        return "\n\n".join(c.strip() for c in match.group(1).split("|"))

    text = re.sub(r"^\|(.*)\|\s*$", cells, readme_text(), flags=re.M)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    assert long_sentences(text) == []


def test_readme_has_no_em_or_en_dashes():
    assert "—" not in readme_text() and "–" not in readme_text()


def test_root_readme_lists_folder(repo_root):
    text = (repo_root / "README.md").read_text(encoding="utf-8")
    assert ROOT_README_ROW in text


def test_root_readme_keeps_the_existing_lines(repo_root):
    text = (repo_root / "README.md").read_text(encoding="utf-8")
    assert "[SaaS Sellability Checklist](saas/saas-sellability-checklist/)" in text
    assert "LIVMO is a tech-focused M&A advisory in San Diego." in text
    assert "https://calendly.com/khaledazar/exit-builder" in text


def test_root_readme_links_resolve(repo_root):
    text = (repo_root / "README.md").read_text(encoding="utf-8")
    targets = [t for t in LINK.findall(text) if not t.startswith(("http://", "https://"))]
    assert targets
    for target in targets:
        assert (repo_root / target).exists(), target


@pytest.mark.parametrize("folder", ["skill", "tools"])
def test_mit_license_files(qoe_root, folder):
    text = (qoe_root / folder / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("MIT License")
    assert MIT_COPYRIGHT in text
    assert "Permission is hereby granted, free of charge" in text
    assert 'THE SOFTWARE IS PROVIDED "AS IS"' in text


def test_licenses(qoe_root, repo_root):
    assert "MIT License" in (qoe_root / "skill" / "LICENSE").read_text(encoding="utf-8")
    assert "qoe-readiness/skill/" in (repo_root / "LICENSE").read_text(encoding="utf-8")


def test_root_license_scope_statement(repo_root):
    text = " ".join((repo_root / "LICENSE").read_text(encoding="utf-8").split())
    assert "Creative Commons Attribution-NonCommercial-NoDerivatives 4.0" in text  # existing text kept
    assert "SIL Open Font License 1.1" in text
    assert "`qoe-readiness/skill/` and `qoe-readiness/tools/` are licensed under the MIT License" in text \
        or "qoe-readiness/skill/ and qoe-readiness/tools/ are licensed under the MIT License" in text
    assert "qoe-readiness/skill/LICENSE" in text and "qoe-readiness/tools/LICENSE" in text


def test_zip_carries_the_skill_license(qoe_root):
    with zipfile.ZipFile(qoe_root / "dist" / "qoe-readiness-skill.zip") as archive:
        assert "qoe-readiness/LICENSE" in archive.namelist()
        assert MIT_COPYRIGHT in archive.read("qoe-readiness/LICENSE").decode("utf-8")
