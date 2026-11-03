"""Tests for the Claude and GPT adapters and the skill package."""
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import package_skill
from test_content import long_sentences

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skill"
DIST_ZIP = ROOT / "dist" / "qoe-readiness-skill.zip"
START_TEXT = ("This skill was designed by LIVMO. LIVMO is not responsible for its output. "
              "You supply the files and approve every number, and the results are yours. "
              "The skill helps you prepare for a Quality of Earnings report. "
              "It does not replace one, and it gives no tax, legal, or accounting advice.")
KNOWLEDGE_DIRS = ("core", "data", "scripts")
PATH_PATTERN = re.compile(r"(?<![\w/.\-])((?:core|data|scripts)/[A-Za-z0-9_\-]+\.(?:md|json|py))")


# ---- helpers -----------------------------------------------------------------

def frontmatter(text: str) -> dict:
    match = re.match(r"---\n(.*?)\n---\n", text, flags=re.S)
    assert match, "SKILL.md has no frontmatter"
    pairs = (line.split(":", 1) for line in match.group(1).splitlines() if ":" in line)
    return {key.strip(): value.strip() for key, value in pairs}


def body(text: str) -> str:
    return re.sub(r"\A---\n.*?\n---\n", "", text, count=1, flags=re.S)


def referenced_paths(text: str) -> set[str]:
    return set(PATH_PATTERN.findall(text))


def knowledge_files(skill_dir: Path) -> set[str]:
    """Every file the GPT needs as knowledge: files in core, data, and scripts. Caches are skipped."""
    return {p.relative_to(skill_dir).as_posix() for d in KNOWLEDGE_DIRS
            for p in (skill_dir / d).iterdir() if p.is_file() and p.suffix != ".pyc"}


def expected_zip_members(skill_dir: Path) -> dict[str, bytes]:
    """The files the package must hold, keyed by archive name, read straight from the skill folder."""
    wanted = {"SKILL.md"} | ({"LICENSE"} if (skill_dir / "LICENSE").is_file() else set()) | knowledge_files(skill_dir)
    return {f"qoe-readiness/{name}": (skill_dir / name).read_bytes() for name in wanted}


@pytest.fixture(scope="module")
def skill_dir():
    return SKILL_DIR


@pytest.fixture(scope="module")
def skill_md():
    return (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def gpt_md():
    return (SKILL_DIR / "gpt-instructions.md").read_text(encoding="utf-8")


# ---- Claude adapter ----------------------------------------------------------------

def test_skill_frontmatter(skill_md):
    fm = frontmatter(skill_md)
    assert fm["name"] == "qoe-readiness"
    assert re.fullmatch(r"[a-z0-9-]{1,64}", fm["name"]) and 0 < len(fm["description"]) <= 1024
    assert "use" in fm["description"].lower()


def test_start_text_first(skill_md, gpt_md):
    for text in (body(skill_md), gpt_md):
        assert text.count(START_TEXT) == 1
        assert text.index(START_TEXT) < text.index("Stage 1")


def test_start_text_is_the_first_instruction(skill_md, gpt_md):
    for text in (body(skill_md), gpt_md):
        assert "first message" in text[:text.index(START_TEXT)]


def test_pointers_resolve(skill_dir, skill_md, gpt_md):
    for rel in referenced_paths(skill_md) | referenced_paths(gpt_md):
        assert (skill_dir / rel).is_file(), rel


def test_every_core_data_script_referenced(skill_dir, skill_md):
    assert knowledge_files(skill_dir) <= referenced_paths(skill_md)


def test_gpt_mentions_every_knowledge_file(skill_dir, gpt_md):
    assert knowledge_files(skill_dir) <= referenced_paths(gpt_md)


def test_stage_order_in_both_adapters(skill_md, gpt_md):
    for text in (body(skill_md), gpt_md):
        positions = [text.index(f"core/stage-{n}-") for n in range(1, 6)]
        assert positions == sorted(positions)


def test_gate_rule_in_both_adapters(skill_md, gpt_md):
    for text in (body(skill_md), gpt_md):
        for phrase in ("Hard floor", "12 consecutive months", "latest closed month",
                       "general ledger or the bank statements", "gate_passed"):
            assert phrase in text, phrase


def test_adapters_hold_no_stage_content(skill_md, gpt_md):
    """No sentence of 10 words or more from a core file appears in an adapter."""
    core_text = " ".join(p.read_text(encoding="utf-8") for p in sorted((SKILL_DIR / "core").iterdir()))
    long_core = {s.strip() for s in re.split(r"(?<=[.!?])\s+", core_text) if len(s.split()) >= 10}
    for text in (skill_md, gpt_md):
        assert [s for s in long_core if s in text] == []


# ---- style of both adapters --------------------------------------------------------

def test_sentences_at_most_25_words(skill_md, gpt_md):
    for text in (skill_md, gpt_md):
        assert long_sentences(body(text)) == []


def test_no_em_or_en_dashes(skill_md, gpt_md):
    for text in (skill_md, gpt_md):
        assert not re.search("[–—]", text)


# ---- GPT adapter -------------------------------------------------------------------

def test_gpt_limits(skill_dir, gpt_md):
    assert len(gpt_md) <= 8000
    assert len(knowledge_files(skill_dir)) <= 20


def test_gpt_turns_on_code_interpreter(gpt_md):
    assert "Turn on Code Interpreter." in gpt_md


def test_gpt_says_to_store_absolute_canonical_paths(gpt_md):
    assert "canonical_path" in gpt_md and "absolute" in gpt_md


def _setup_snippet(gpt_md: str) -> str:
    blocks = re.findall(r"```python\n(.*?)```", gpt_md, flags=re.S)
    setup = [b for b in blocks if "shutil" in b]
    assert len(setup) == 1, "gpt-instructions.md needs exactly one setup snippet that copies files"
    return setup[0]


def test_gpt_setup_snippet_builds_the_layout_the_scripts_expect(tmp_path, skill_dir, gpt_md):
    """Run the setup snippet on a flat folder, as in /mnt/data, and check the result."""
    flat = tmp_path / "mnt_data"
    flat.mkdir()
    for rel in knowledge_files(skill_dir):
        (flat / Path(rel).name).write_bytes((skill_dir / rel).read_bytes())
    (flat / "progress.json").write_text("{}", encoding="utf-8")  # an owner upload must stay out of data/
    code = _setup_snippet(gpt_md).replace("/mnt/data", flat.as_posix())
    subprocess.run([sys.executable, "-I", "-c", code], check=True, cwd=tmp_path)
    project = flat / "qoe-readiness"
    for rel in knowledge_files(skill_dir):
        if rel.startswith(("data/", "scripts/")):
            assert (project / rel).read_bytes() == (skill_dir / rel).read_bytes(), rel
    assert not (project / "data" / "progress.json").exists()
    probe = "import sys; sys.path.insert(0, 'scripts'); import build_workbook; print(build_workbook.DEFAULT_DATA_DIR)"
    out = subprocess.run([sys.executable, "-I", "-c", probe], check=True, cwd=project,
                         capture_output=True, text=True).stdout.strip()
    assert Path(out).resolve() == (project / "data").resolve()


# ---- package -----------------------------------------------------------------------

def test_zip_contents(tmp_path, skill_dir):
    names = zipfile.ZipFile(package_skill.package(skill_dir, tmp_path / "s.zip")).namelist()
    assert "qoe-readiness/SKILL.md" in names
    assert not any("gpt-instructions" in n or "__pycache__" in n or "tests" in n for n in names)
    assert all(n.startswith("qoe-readiness/") for n in names)


def test_zip_includes_license_when_present(tmp_path):
    skill = tmp_path / "skill"
    for rel in ("SKILL.md", "gpt-instructions.md", "core/a.md", "data/b.json", "scripts/c.py",
                "scripts/__pycache__/c.pyc"):
        (skill / rel).parent.mkdir(parents=True, exist_ok=True)
        (skill / rel).write_text("x", encoding="utf-8")
    without = zipfile.ZipFile(package_skill.package(skill, tmp_path / "a.zip")).namelist()
    assert "qoe-readiness/LICENSE" not in without
    (skill / "LICENSE").write_text("MIT", encoding="utf-8")
    with_license = zipfile.ZipFile(package_skill.package(skill, tmp_path / "b.zip")).namelist()
    assert sorted(with_license) == sorted(["qoe-readiness/SKILL.md", "qoe-readiness/LICENSE",
                                           "qoe-readiness/core/a.md", "qoe-readiness/data/b.json",
                                           "qoe-readiness/scripts/c.py"])


def test_committed_zip_matches_current_skill_files(skill_dir):
    assert DIST_ZIP.is_file(), "run: python tools/package_skill.py"
    with zipfile.ZipFile(DIST_ZIP) as archive:
        actual = {name: archive.read(name) for name in archive.namelist()}
    expected = expected_zip_members(skill_dir)
    assert sorted(actual) == sorted(expected)
    assert [n for n in expected if actual[n] != expected[n]] == []


def test_package_cli_writes_the_zip(tmp_path):
    out = tmp_path / "cli.zip"
    subprocess.run([sys.executable, str(ROOT / "tools" / "package_skill.py"), "--out", str(out)],
                   check=True, cwd=ROOT)
    assert zipfile.ZipFile(out).namelist()
