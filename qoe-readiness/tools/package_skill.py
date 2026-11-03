"""Package the skill folder into dist/qoe-readiness-skill.zip.

The zip root folder is qoe-readiness/. It holds SKILL.md, LICENSE (when present), core/, data/,
and scripts/. Text files use LF line endings. It leaves out gpt-instructions.md, caches, and tests.
"""
import argparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SKILL_DIR = ROOT / "skill"
DEFAULT_OUT = ROOT / "dist" / "qoe-readiness-skill.zip"
ARCHIVE_ROOT = "qoe-readiness"
TOP_FILES = ("SKILL.md", "LICENSE")
FOLDERS = ("core", "data", "scripts")
SKIPPED_PARTS = {"__pycache__"}
SKIPPED_SUFFIXES = {".pyc", ".pyo"}
TEXT_SUFFIXES = {".md", ".json", ".py"}
FIXED_TIME = (2026, 11, 2, 0, 0, 0)  # a fixed time keeps the zip bytes stable between runs


def members(skill_dir: Path) -> list[Path]:
    """Return the files to package, sorted by relative path."""
    found = [skill_dir / name for name in TOP_FILES if (skill_dir / name).is_file()]
    for folder in FOLDERS:
        found.extend(p for p in (skill_dir / folder).rglob("*")
                     if p.is_file() and not SKIPPED_PARTS & set(p.parts) and p.suffix not in SKIPPED_SUFFIXES)
    return sorted(found, key=lambda p: p.relative_to(skill_dir).as_posix())


def archive_bytes(path: Path) -> bytes:
    """Read a file for the zip. Text files use LF endings, so the zip does not depend on git's checkout."""
    data = path.read_bytes()
    return data.replace(b"\r\n", b"\n") if path.suffix in TEXT_SUFFIXES or path.name == "LICENSE" else data


def package(skill_dir: Path, out_zip: Path) -> Path:
    """Write the skill zip to out_zip and return its path."""
    skill_dir, out_zip = Path(skill_dir), Path(out_zip)
    if not (skill_dir / "SKILL.md").is_file():
        raise FileNotFoundError(f"SKILL.md not found in {skill_dir}")
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in members(skill_dir):
            name = f"{ARCHIVE_ROOT}/{path.relative_to(skill_dir).as_posix()}"
            info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, archive_bytes(path))
    return out_zip


def main() -> None:
    parser = argparse.ArgumentParser(description="Package the QoE readiness skill as a zip.")
    parser.add_argument("--skill", type=Path, default=DEFAULT_SKILL_DIR, help="skill folder")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="zip file to write")
    args = parser.parse_args()
    print(package(args.skill, args.out))


if __name__ == "__main__":
    main()
