"""Copy runnable source snapshot into a version output folder."""

from __future__ import annotations

import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = Path(__file__).resolve().parent


def resolve_output_dir(version_name: str) -> Path:
    """If script lives in output/<version>/src/, write results to version root."""
    here = Path(__file__).resolve().parent
    if here.name == "src" and here.parent.parent.name == "output":
        return here.parent
    return PROJECT_ROOT / "output" / version_name


def _copy_src_tree(dest: Path) -> list[str]:
    copied: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*")):
        if path.is_dir() or path.name == "__pycache__":
            continue
        rel = path.relative_to(SRC_ROOT)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied.append(str(rel).replace("\\", "/"))
    req = PROJECT_ROOT / "requirements.txt"
    if req.exists():
        shutil.copy2(req, dest / "requirements.txt")
        copied.append("requirements.txt")
    return copied


def snapshot_version(out_dir: Path, entry_scripts: list[str | Path]) -> Path:
    """
    Copy src package + current repository entry scripts to out_dir/src/.
    Returns src_dir path.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    src_dir = out_dir / "src"
    if src_dir.exists():
        shutil.rmtree(src_dir)
    src_dir.mkdir(parents=True, exist_ok=True)

    copied = _copy_src_tree(src_dir)
    copied_entries: list[tuple[Path, Path]] = []
    bootstrap = PROJECT_ROOT / "versions" / "_bootstrap.py"
    if bootstrap.exists():
        target = src_dir / "versions" / "_bootstrap.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bootstrap, target)
        copied.append("versions/_bootstrap.py")

    for entry in entry_scripts:
        rel_entry = Path(entry)
        src = PROJECT_ROOT / rel_entry
        if not src.exists():
            continue
        target = src_dir / rel_entry
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        rel_text = rel_entry.as_posix()
        copied.append(rel_text)
        copied_entries.append((rel_entry, target))

    run_txt = src_dir / "RUN.txt"
    root_commands = "\n".join(f"  python {rel.as_posix()}" for rel, _ in copied_entries)
    snapshot_commands = "\n".join(f"  python {target.relative_to(src_dir).as_posix()}" for _, target in copied_entries)
    run_txt.write_text(
        "在项目根目录下运行（需联网拉数据时）:\n\n"
        f"  cd \"{PROJECT_ROOT}\"\n"
        + root_commands
        + "\n\n"
        "或在版本文件夹内（使用快照源码）:\n\n"
        f"  cd \"{src_dir}\"\n"
        + snapshot_commands
        + "\n",
        encoding="utf-8",
    )

    manifest = out_dir / "src_manifest.txt"
    manifest.write_text("\n".join(copied) + "\n", encoding="utf-8")
    return src_dir


def append_readme_note(out_dir: Path, note: str) -> None:
    readme = out_dir / "README.txt"
    text = readme.read_text(encoding="utf-8") if readme.exists() else ""
    block = f"\n源码: src/ ({note})\n运行说明: src/RUN.txt\n"
    if "源码: src/" not in text:
        readme.write_text(text.rstrip() + block, encoding="utf-8")
