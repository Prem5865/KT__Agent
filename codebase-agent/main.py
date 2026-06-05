"""
main.py
-------
CLI entry point for the Codebase Analysis Agent.

Usage:
    python main.py <folder>                          # Analyze (outputs PDF + MD)
    python main.py <folder> --format pdf             # PDF only
    python main.py <folder> --format md              # Markdown only
    python main.py <folder> --format both            # Both (default)
    python main.py <folder> --output my_report       # Custom base name (no extension)
    python main.py <folder> --model claude-sonnet-4-6
    python main.py <folder> --max-files 80
    python main.py <folder> --verbose

Example:
    python main.py ../my-project
    python main.py . --format pdf --output output/frontend_report
"""

import argparse
import os
import sys
from pathlib import Path

# ── Load .env if ANTHROPIC_API_KEY is not already in the environment ──────────
if not os.environ.get("ANTHROPIC_API_KEY"):
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("ANTHROPIC_API_KEY="):
                os.environ["ANTHROPIC_API_KEY"] = (
                    line.split("=", 1)[1].strip().strip('"').strip("'")
                )
                break

if not os.environ.get("ANTHROPIC_API_KEY"):
    print(
        "\n[ERROR] ANTHROPIC_API_KEY is not set.\n"
        "  Option 1: Set it in your shell:\n"
        "            Windows:  $env:ANTHROPIC_API_KEY = 'sk-ant-...'\n"
        "            Mac/Linux: export ANTHROPIC_API_KEY='sk-ant-...'\n"
        "  Option 2: Create a .env file in this folder:\n"
        "            ANTHROPIC_API_KEY=sk-ant-...\n"
    )
    sys.exit(1)

from agent.analyzer import CodebaseAnalyzer
from agent.flow_builder import FlowBuilder
from agent.doc_generator import DocumentationGenerator
from agent.utils import setup_logging, print_banner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="codebase-agent",
        description="Codebase Analysis Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default=".",
        help="Path to the codebase folder to analyze (default: current directory)",
    )
    parser.add_argument(
        "--output",
        default="output/report",
        metavar="BASE_PATH",
        help=(
            "Output file base path without extension (default: output/report). "
            "Extensions .md and/or .pdf are appended automatically."
        ),
    )
    parser.add_argument(
        "--format",
        default="both",
        choices=["pdf", "md", "both"],
        help="Output format: pdf | md | both (default: both)",
    )
    parser.add_argument(
        "--model",
        default="claude-opus-4-8",
        choices=[
            "claude-opus-4-8",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
        ],
        help="Claude model to use (default: claude-opus-4-8)",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=50,
        metavar="N",
        help="Maximum number of source files to analyze (default: 50)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose/debug logging",
    )
    return parser.parse_args()


def _strip_ext(p: str) -> str:
    """Remove .md or .pdf extension from a path string so callers can pass either form."""
    for ext in (".md", ".pdf"):
        if p.lower().endswith(ext):
            return p[: -len(ext)]
    return p


def main():
    args = parse_args()
    setup_logging(args.verbose)
    print_banner()

    # Resolve and validate target folder
    folder_path = Path(args.folder).resolve()
    if not folder_path.exists():
        print(f"\n[ERROR] Folder not found: {folder_path}")
        sys.exit(1)
    if not folder_path.is_dir():
        print(f"\n[ERROR] Not a directory: {folder_path}")
        sys.exit(1)

    base = _strip_ext(args.output)
    md_path = Path(base + ".md")
    pdf_path = Path(base + ".pdf")
    want_pdf = args.format in ("pdf", "both")
    want_md = args.format in ("md", "both")

    print(f"\nTarget folder : {folder_path}")
    print(f"Output format : {args.format.upper()}")
    if want_md:
        print(f"Markdown      : {md_path.resolve()}")
    if want_pdf:
        print(f"PDF           : {pdf_path.resolve()}")
    print(f"Model         : {args.model}")
    print(f"Max files     : {args.max_files}")

    # ── Step 1: Scan & parse the codebase ────────────────────────────────────
    print("\n[1/3] Scanning codebase ...")
    analyzer = CodebaseAnalyzer(str(folder_path), max_files=args.max_files)
    analysis = analyzer.analyze()
    stats = analysis["stats"]
    print(
        f"      Found {stats['total_files']} files  |  "
        f"{stats['total_classes']} classes  |  "
        f"{stats['total_functions']} functions  |  "
        f"{stats['total_lines']:,} lines"
    )
    if stats["entry_points"]:
        print(f"      Entry points: {', '.join(stats['entry_points'])}")

    # ── Step 2: Build flows via Claude ───────────────────────────────────────
    print("\n[2/3] Building flows with Claude ...")
    flow_builder = FlowBuilder(model=args.model)
    flows = flow_builder.build_flows(analysis)

    # ── Step 3: Generate Markdown report ─────────────────────────────────────
    print("\n[3/3] Generating documentation ...")
    doc_generator = DocumentationGenerator(model=args.model)
    report_md = doc_generator.generate(analysis, flows)

    # ── Write Markdown ────────────────────────────────────────────────────────
    if want_md:
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(report_md, encoding="utf-8")
        word_count = len(report_md.split())
        print(f"\n  Markdown saved : {md_path.resolve()}")
        print(f"  Size           : {len(report_md):,} chars | ~{word_count:,} words")

    # ── Write PDF ─────────────────────────────────────────────────────────────
    if want_pdf:
        print("\n  Converting to PDF ...")
        try:
            from agent.pdf_generator import PDFGenerator
            pdf_gen = PDFGenerator()
            success = pdf_gen.generate(report_md, str(pdf_path))
            if success:
                size_kb = pdf_path.stat().st_size // 1024
                print(f"  PDF saved      : {pdf_path.resolve()}")
                print(f"  Size           : {size_kb:,} KB")
            else:
                print("  [WARN] PDF conversion reported errors — check output above.")
        except ImportError:
            print(
                "\n  [ERROR] PDF dependencies not installed.\n"
                "  Run:  pip install markdown xhtml2pdf\n"
                "  Or:   pip install -r requirements.txt"
            )
            sys.exit(1)

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\nDone!")
    if want_md:
        print(f"  Open Markdown in VS Code : code \"{md_path.resolve()}\"")
    if want_pdf:
        print(f"  Open PDF                 : start \"{pdf_path.resolve()}\"")


if __name__ == "__main__":
    main()
