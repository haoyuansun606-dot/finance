"""Copy runnable source snapshot into a version output folder."""

from __future__ import annotations

import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

# Shared modules required by V4 diversified variants
CORE_MODULES = [
    "version_bundle.py",
    "data_loader.py",
    "strategy_grouped.py",
    "strategy.py",
    "correlation_filter.py",
    "metrics.py",
    "schedule_rebalance.py",
    "expanded_study.py",
    "requirements.txt",
]


def resolve_output_dir(version_name: str) -> Path:
    """If script lives in output/<version>/src/, write results to version root."""
    here = Path(__file__).resolve().parent
    if here.name == "src":
        return here.parent
    return PROJECT_ROOT / "output" / version_name


def snapshot_version(out_dir: Path, entry_scripts: list[str]) -> Path:
    """
    Copy entry + core modules to out_dir/src/.
    Returns src_dir path.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    src_dir = out_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    for name in CORE_MODULES + entry_scripts:
        src = PROJECT_ROOT / name
        if not src.exists():
            continue
        shutil.copy2(src, src_dir / name)
        copied.append(name)

    run_txt = src_dir / "RUN.txt"
    run_txt.write_text(
        "在 permanent_portfolio 目录下运行（需联网拉数据时）:\n\n"
        f"  cd \"{src_dir}\"\n"
        + "\n".join(f"  python {name}" for name in entry_scripts if (src_dir / name).exists())
        + "\n\n"
        "或在版本文件夹内:\n\n"
        f"  cd \"{out_dir / 'src'}\"\n"
        + "\n".join(f"  python {name}" for name in entry_scripts if (src_dir / name).exists())
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
