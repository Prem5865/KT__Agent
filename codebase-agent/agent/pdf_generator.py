"""
pdf_generator.py
----------------
Converts the Markdown report string into a styled PDF.

Pipeline:
    Markdown  --[sanitize_unicode]--> clean Markdown
              --[markdown lib]------> HTML
              --[xhtml2pdf]---------> PDF

xhtml2pdf compatibility constraints:
  - Built-in fonts (Helvetica/Arial/Courier) only cover Latin-1 (U+0000–U+00FF).
    Any character outside that range renders as a BLACK SQUARE.
    Fix: _sanitize_unicode() replaces every non-Latin-1 character with a readable
    ASCII equivalent BEFORE the HTML conversion step.
  - No CSS `content:` / `counter()` — crashes the CSS parser.
  - No `tr:nth-child(even)` — unsupported; rows are striped in Python instead.
  - No `border-radius`, `overflow`, `page-break-after: avoid`.
  - `@page` must be a simple block with no sub-rules (@bottom-center etc.).
"""

import re
from pathlib import Path

import markdown
from xhtml2pdf import pisa

from .utils import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Unicode → ASCII replacement table
#
# xhtml2pdf uses ReportLab's built-in Type-1 fonts which only cover Latin-1.
# Every code-point > U+00FF that Claude's output or the file-tree might contain
# must be mapped to a safe ASCII equivalent here.
# ---------------------------------------------------------------------------
_UNICODE_MAP = str.maketrans({
    # Smart / curly quotes
    '‘': "'",    # left single quotation mark  '
    '’': "'",    # right single quotation mark '
    '‚': ',',    # single low-9 quotation mark  ‚
    '‛': "'",    # single high-reversed-9       ‛
    '“': '"',    # left double quotation mark   "
    '”': '"',    # right double quotation mark  "
    '„': '"',    # double low-9 quotation mark  „
    '‟': '"',    # double high-reversed-9        ‟
    '‹': '<',    # single left angle quotation  ‹
    '›': '>',    # single right angle quotation ›
    '«': '<<',   # left-pointing double angle   «
    '»': '>>',   # right-pointing double angle  »
    # Dashes
    '–': '-',    # en dash                      –
    '—': '--',   # em dash                      —
    '―': '--',   # horizontal bar               ―
    '−': '-',    # minus sign                   −
    # Arrows (very common in flow descriptions)
    '←': '<-',   # ←
    '↑': '^',    # ↑
    '→': '->',   # →
    '↓': 'v',    # ↓
    '⇐': '<=',   # ⇐
    '⇒': '=>',   # ⇒
    '⇔': '<=>',  # ⇔
    '⇦': '<-',   # ⇦
    '⇨': '->',   # ⇨
    # Ellipsis
    '…': '...',  # …
    # Bullets / list markers
    '•': '*',    # bullet                       •
    '‣': '>',    # triangular bullet            ‣
    '▪': '*',    # small black square           ▪
    '►': '>',    # black right-pointing pointer ►
    '●': '*',    # black circle                 ●
    '○': 'o',    # white circle                 ○
    '·': '*',    # middle dot                   ·
    # Check marks / status icons
    '✓': '(ok)', # ✓
    '✔': '(ok)', # ✔
    '✕': '(x)',  # ✕
    '✖': '(x)',  # ✖
    '✗': '(x)',  # ✗
    '✘': '(x)',  # ✘
    '✅': '[ok]', # ✅
    '❌': '[x]',  # ❌
    '⚠': '[!]',  # ⚠
    'ℹ': '(i)',  # ℹ
    # Box-drawing characters  ← these appear in the file-tree section
    '─': '-',    # ─  light horizontal
    '━': '-',    # ━  heavy horizontal
    '│': '|',    # │  light vertical
    '┃': '|',    # ┃  heavy vertical
    '┌': '+',    # ┌
    '┏': '+',    # ┏
    '┐': '+',    # ┐
    '┓': '+',    # ┓
    '└': '+',    # └
    '┗': '+',    # ┗
    '┘': '+',    # ┘
    '┛': '+',    # ┛
    '├': '+',    # ├
    '┟': '+',    # ┟
    '┣': '+',    # ┣
    '┤': '+',    # ┤
    '┫': '+',    # ┫
    '┬': '+',    # ┬
    '┳': '+',    # ┳
    '┴': '+',    # ┴
    '┻': '+',    # ┻
    '┼': '+',    # ┼
    '╋': '+',    # ╋
    '═': '=',    # ═  double horizontal
    '║': '|',    # ║  double vertical
    '╔': '+',    # ╔
    '╗': '+',    # ╗
    '╚': '+',    # ╚
    '╝': '+',    # ╝
    '╠': '+',    # ╠
    '╣': '+',    # ╣
    '╦': '+',    # ╦
    '╩': '+',    # ╩
    '╬': '+',    # ╬
    # Mathematical symbols
    '×': 'x',    # multiplication sign  ×
    '÷': '/',    # division sign         ÷
    '≈': '~=',   # almost equal to       ≈
    '≠': '!=',   # not equal to          ≠
    '≤': '<=',   # less-than or equal    ≤
    '≥': '>=',   # greater-than or equal ≥
    '∞': 'inf',  # infinity              ∞
    '∑': 'sum',  # n-ary summation       ∑
    '∏': 'prod', # n-ary product         ∏
    '∂': 'd',    # partial differential  ∂
    # Greek letters (may appear in technical docs)
    'α': 'alpha',
    'β': 'beta',
    'γ': 'gamma',
    'δ': 'delta',
    'λ': 'lambda',
    'π': 'pi',
    'σ': 'sigma',
    'τ': 'tau',
    'ω': 'omega',
    # Miscellaneous symbols
    ' ': ' ',    # non-breaking space
    '®': '(R)',  # registered sign  ®
    '©': '(C)',  # copyright sign   ©
    '™': '(TM)', # trade mark sign  ™
    '°': 'deg',  # degree sign      °
    '±': '+/-',  # plus-minus sign  ±
    '²': '^2',   # superscript two  ²
    '³': '^3',   # superscript three ³
    '’': "'",    # (duplicate safety)
    'ﬁ': 'fi',   # fi ligature  ﬁ
    'ﬂ': 'fl',   # fl ligature  ﬂ
    '​': '',     # zero-width space
    '﻿': '',     # BOM / zero-width no-break space
})


# ---------------------------------------------------------------------------
# CSS — only properties xhtml2pdf reliably supports
# ---------------------------------------------------------------------------
_CSS = """
@page {
    size: A4;
    margin: 2.2cm 2cm 2.5cm 2cm;
}

body {
    font-family: Arial, Helvetica, sans-serif;
    font-size: 10pt;
    line-height: 1.5;
    color: #1a1a1a;
}

h1 {
    font-size: 18pt;
    color: #1a237e;
    border-bottom: 2px solid #1a237e;
    padding-bottom: 4px;
    margin-top: 0pt;
    margin-bottom: 8pt;
}
h2 {
    font-size: 14pt;
    color: #283593;
    border-bottom: 1px solid #9fa8da;
    padding-bottom: 3px;
    margin-top: 18pt;
    margin-bottom: 6pt;
}
h3 {
    font-size: 11.5pt;
    color: #3949ab;
    margin-top: 12pt;
    margin-bottom: 4pt;
}
h4 {
    font-size: 10.5pt;
    color: #5c6bc0;
    margin-top: 8pt;
}

code {
    background: #eeeeee;
    padding: 1px 3px;
    font-family: Courier New, Courier, monospace;
    font-size: 9pt;
    color: #c62828;
}

pre {
    background: #f5f5f5;
    padding: 7pt 9pt;
    font-family: Courier New, Courier, monospace;
    font-size: 8pt;
    line-height: 1.4;
    border-left: 4px solid #5c6bc0;
    margin: 6pt 0 8pt 0;
}
pre code {
    background: none;
    padding: 0;
    color: #1a1a1a;
    font-size: 8pt;
}

table {
    border-collapse: collapse;
    width: 100%;
    margin: 8pt 0 12pt 0;
    font-size: 9pt;
}
th {
    background-color: #3949ab;
    color: #ffffff;
    padding: 5pt 8pt;
    text-align: left;
    font-weight: bold;
}
td {
    padding: 4pt 8pt;
    border: 1px solid #c5cae9;
    vertical-align: top;
}
tr.even td {
    background-color: #e8eaf6;
}

blockquote {
    border-left: 4px solid #7986cb;
    margin: 4pt 0 12pt 0;
    padding: 6pt 12pt;
    background: #f3f4ff;
    color: #37474f;
    font-size: 9.5pt;
}

hr {
    border-top: 1px solid #c5cae9;
    margin: 14pt 0;
}

ul, ol {
    margin: 4pt 0;
    padding-left: 16pt;
}
li {
    margin: 2pt 0;
}

a { color: #3949ab; }
strong { color: #1a237e; }
em { color: #444; }
"""


class PDFGenerator:
    """
    Converts a Markdown string (the full analysis report) to a styled PDF.
    """

    def generate(self, markdown_text: str, output_path: str) -> bool:
        """
        Convert *markdown_text* to PDF and write to *output_path*.
        Returns True on success, False on failure.
        """
        # Step 1 — sanitise Unicode so no character falls outside Latin-1
        clean_text = self._sanitize_unicode(markdown_text)

        # Step 2 — convert to HTML
        logger.info("Converting Markdown to HTML")
        html = self._markdown_to_html(clean_text)

        # Step 3 — render to PDF
        logger.info("Rendering HTML to PDF via xhtml2pdf")
        return self._html_to_pdf(html, output_path)

    # ------------------------------------------------------------------
    # Unicode sanitisation  (applied BEFORE markdown conversion)
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_unicode(text: str) -> str:
        """
        Replace every character outside Latin-1 with a readable ASCII stand-in.

        Two passes:
          1. Named replacements from _UNICODE_MAP (arrows, dashes, box-drawing, etc.)
          2. Catch-all: any remaining char > U+00FF is replaced with '?'
        """
        # Pass 1 — known replacements
        text = text.translate(_UNICODE_MAP)

        # Pass 2 — catch any remaining non-Latin-1 character
        sanitized = []
        for ch in text:
            if ord(ch) > 0xFF:
                sanitized.append('?')
            else:
                sanitized.append(ch)
        return ''.join(sanitized)

    # ------------------------------------------------------------------
    # Markdown → HTML
    # ------------------------------------------------------------------

    def _markdown_to_html(self, text: str) -> str:
        title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        doc_title = title_match.group(1) if title_match else "Codebase Analysis Report"
        doc_title = doc_title.replace("`", "")

        md = markdown.Markdown(
            extensions=["tables", "fenced_code", "nl2br", "sane_lists"]
        )
        body_html = md.convert(text)

        body_html = self._stripe_table_rows(body_html)
        body_html = self._wrap_pre_lines(body_html, max_chars=110)

        return (
            "<!DOCTYPE html>\n"
            "<html lang='en'>\n"
            "<head>\n"
            "  <meta charset='UTF-8'>\n"
            f"  <title>{doc_title}</title>\n"
            "  <style>\n"
            f"{_CSS}\n"
            "  </style>\n"
            "</head>\n"
            "<body>\n"
            f"{body_html}\n"
            "</body>\n"
            "</html>"
        )

    # ------------------------------------------------------------------
    # HTML post-processing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _stripe_table_rows(html: str) -> str:
        """Add class='even' to every second <tr> — replaces unsupported nth-child CSS."""
        def replace_tbody(m: re.Match) -> str:
            tbody = m.group(0)
            parts = re.split(r"(?=<tr)", tbody, flags=re.IGNORECASE)
            row_idx = 0
            result = []
            for part in parts:
                if re.match(r"<tr", part, re.IGNORECASE):
                    if row_idx % 2 == 1:
                        part = re.sub(
                            r"<tr(\s*)", r'<tr class="even"\1',
                            part, count=1, flags=re.IGNORECASE,
                        )
                    row_idx += 1
                result.append(part)
            return "".join(result)

        return re.sub(
            r"<tbody>.*?</tbody>", replace_tbody, html,
            flags=re.DOTALL | re.IGNORECASE,
        )

    @staticmethod
    def _wrap_pre_lines(html: str, max_chars: int = 110) -> str:
        """Truncate long lines inside <pre> to prevent page-width overflow."""
        def shorten(m: re.Match) -> str:
            lines = m.group(1).split("\n")
            return "<pre>" + "\n".join(
                line[:max_chars] + " ..." if len(line) > max_chars else line
                for line in lines
            ) + "</pre>"

        return re.sub(r"<pre>(.*?)</pre>", shorten, html, flags=re.DOTALL | re.IGNORECASE)

    # ------------------------------------------------------------------
    # HTML → PDF
    # ------------------------------------------------------------------

    def _html_to_pdf(self, html: str, output_path: str) -> bool:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(out, "wb") as pdf_file:
                result = pisa.CreatePDF(
                    src=html.encode("utf-8"),
                    dest=pdf_file,
                    encoding="utf-8",
                )
            if result.err:
                logger.error("xhtml2pdf reported %d error(s)", result.err)
                if out.exists() and out.stat().st_size > 1024:
                    logger.warning(
                        "PDF exists (%d bytes) despite errors — likely usable",
                        out.stat().st_size,
                    )
                    return True
                return False

            logger.info("PDF written: %s (%d bytes)", out, out.stat().st_size)
            return True

        except Exception as exc:
            logger.error("PDF generation failed: %s", exc)
            self._plain_text_fallback(html, out)
            return False

    # ------------------------------------------------------------------
    # Plain-text fallback
    # ------------------------------------------------------------------

    @staticmethod
    def _plain_text_fallback(html: str, out: Path):
        txt_path = out.with_suffix(".txt")
        clean = re.sub(r"<[^>]+>", "", html)
        clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
        try:
            txt_path.write_text(clean, encoding="utf-8")
            print(f"  [Fallback] Plain text saved to: {txt_path}")
        except Exception as e:
            logger.error("Fallback write failed: %s", e)
