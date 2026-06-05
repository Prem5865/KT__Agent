import logging
import sys
from pathlib import Path
from typing import Optional


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )


def read_file_safe(path: Path, max_size: int = 500_000) -> Optional[str]:
    """Read a text file safely, returning None on error or if too large."""
    try:
        if path.stat().st_size > max_size:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except (OSError, PermissionError):
        return None


def is_binary_file(path: Path) -> bool:
    """Detect binary files by checking for null bytes in the first 1 KB."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(1024)
            return b"\x00" in chunk
    except (OSError, PermissionError):
        return True


def load_prompt(filename: str) -> str:
    """Load a prompt template from the prompts/ directory."""
    prompt_path = Path(__file__).parent.parent / "prompts" / filename
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return ""


def print_banner():
    banner = r"""
+--------------------------------------------------+
|       Codebase Analysis Agent                    |
|       Powered by Claude AI (Anthropic)           |
+--------------------------------------------------+"""
    print(banner)


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n... [truncated {len(text) - max_chars} chars]"
