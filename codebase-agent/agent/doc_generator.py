"""
doc_generator.py
----------------
Assembles the final Markdown report from analyzer output and flow data.
Supports selective section generation — only selected sections are included.
"""

import anthropic
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, Any, List, Optional, Set

from .utils import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are a senior software engineer writing precise, developer-facing documentation. "
    "Be concise, factual, and grounded in the actual codebase details provided."
)

# Ordered master list of ALL sections.
# Each entry: (key, display_title, source)
#   source = "flow"   → content comes from flows dict (FlowBuilder)
#           "ai"    → content from a Claude call here
#           "static" → built from analysis data, no Claude
SECTION_REGISTRY = [
    ("executive_summary",      "Executive Summary",                              "ai"),
    ("project_overview",       "Project Overview",                               "static"),
    ("architecture",           "Technical Architecture",                         "flow"),
    ("functional_flow",        "Functional Flow",                                "flow"),
    ("data_flow",              "Data Flow Analysis",                             "flow"),
    ("components",             "Component Relationships",                        "flow"),
    ("workflow",               "Workflow",                                       "flow"),
    ("inputs_outputs",         "Project Inputs & Outputs",                      "flow"),
    ("api_calls",              "API Calls Analysis",                             "flow"),
    ("component_data_flow",    "Data Flow Between Components (with API Context)","flow"),
    ("component_architecture", "Component Technical Architecture",               "flow"),
    ("tech_stack",             "Technology Stack",                               "flow"),
    ("file_inventory",         "File Inventory",                                 "static"),
    ("api_endpoints",          "API Endpoints",                                  "static"),
    ("dependencies",           "Dependencies",                                   "static"),
    ("onboarding",             "Developer Onboarding Guide",                     "ai"),
]

# Slug helper for anchor links
def _slug(title: str) -> str:
    return title.lower().replace(" ", "-").replace("(", "").replace(")", "").replace("&", "").replace(",", "").replace("/", "").replace("__", "-")


class DocumentationGenerator:

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic()
        self.model = model

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def generate(
        self,
        analysis: Dict[str, Any],
        flows: Dict[str, str],
        selected_sections: Optional[Set[str]] = None,
    ) -> str:
        """
        Build the full Markdown report.
        selected_sections: set of section keys to include; None = all.
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Determine which sections to render (preserve registry order)
        if selected_sections is None:
            active = [row for row in SECTION_REGISTRY]
        else:
            active = [row for row in SECTION_REGISTRY if row[0] in selected_sections]

        # ── Generate AI sections in parallel ──────────────────────────────
        ai_keys = [key for key, _, src in active if src == "ai"]
        ai_results: Dict[str, str] = {}

        if ai_keys:
            print(f"   Running {len(ai_keys)} AI section(s) in parallel: {ai_keys}")
            with ThreadPoolExecutor(max_workers=len(ai_keys)) as executor:
                futures = {}
                for key in ai_keys:
                    if key == "executive_summary":
                        futures[executor.submit(self._generate_executive_summary, analysis, flows)] = key
                    elif key == "onboarding":
                        futures[executor.submit(self._generate_onboarding, analysis)] = key
                for future in futures:
                    ai_results[futures[future]] = future.result()
            print("   [done] AI sections")

        # ── Assemble report ───────────────────────────────────────────────
        parts: List[str] = [
            f"# Codebase Analysis Report: `{analysis['project_name']}`",
            f"\n> **Generated:** {now}  ",
            f"> **Analyzed by:** Codebase Analysis Agent (Claude AI / Anthropic)  ",
            f"> **Root Path:** `{analysis['root_path']}`\n",
            "---\n",
            "## Table of Contents\n",
        ]

        # Dynamic TOC
        for i, (key, title, _) in enumerate(active, 1):
            anchor = _slug(title)
            parts.append(f"{i}. [{title}](#{i}-{anchor})")
        parts.append("\n---\n")

        # Dynamic sections
        for i, (key, title, src) in enumerate(active, 1):
            parts.append(f"\n---\n## {i}. {title}\n")
            if src == "ai":
                parts.append(ai_results.get(key, "_Section unavailable._"))
            elif src == "flow":
                parts.append(flows.get(key, f"_Section `{key}` was not selected for generation._"))
            elif src == "static":
                if key == "project_overview":
                    parts.append(self._build_overview(analysis))
                elif key == "file_inventory":
                    parts.append(self._build_file_inventory(analysis))
                elif key == "api_endpoints":
                    parts.append(self._build_api_section(analysis))
                elif key == "dependencies":
                    parts.append(self._build_dependencies(analysis))

        parts.append(f"\n---\n*Report generated by Codebase Analysis Agent | {now}*")
        return "\n".join(parts)

    # ------------------------------------------------------------------ #
    # AI-generated sections                                                #
    # ------------------------------------------------------------------ #

    def _generate_executive_summary(self, analysis: Dict, flows: Dict) -> str:
        stats = analysis["stats"]
        arch_excerpt = flows.get("architecture", flows.get("tech_stack", ""))[:600]
        prompt = f"""Write a concise **executive summary** (3-4 paragraphs) for this codebase.

Project name: {analysis['project_name']}
Stats: {stats['total_files']} files | {stats['total_classes']} classes | {stats['total_functions']} functions | {stats['total_lines']:,} lines
Languages: {', '.join(stats['languages'].keys())}
Entry points: {', '.join(stats['entry_points']) or 'None detected'}

Architecture excerpt:
{arch_excerpt}

Cover: purpose/domain, core technical approach, notable strengths, focus areas for new developers.
Write for a technical audience. Be specific. Do not use bullet points."""
        return self._call_claude(prompt, "executive_summary", max_tokens=800)

    def _generate_onboarding(self, analysis: Dict) -> str:
        stats = analysis["stats"]
        prompt = f"""Write a practical **Developer Onboarding Guide** for a developer new to this codebase.

Project: {analysis['project_name']}
Languages: {', '.join(stats['languages'].keys())}
Entry points: {', '.join(stats['entry_points']) or 'Not detected'}
Config files: {', '.join(analysis['config'].keys()) or 'None'}

Include:
1. **Prerequisites** — runtimes, tools, accounts
2. **Setup Steps** — numbered steps to run locally
3. **Running the Project** — exact commands
4. **Where to Start Reading** — recommended first files and why
5. **Key Concepts** — 3-5 domain/technical concepts a new dev must understand
6. **Common Tasks** — where to add a feature, fix a bug, add an endpoint

Be specific to this tech stack. Use numbered lists and code blocks."""
        return self._call_claude(prompt, "onboarding", max_tokens=1200)

    # ------------------------------------------------------------------ #
    # Static sections (no Claude)                                          #
    # ------------------------------------------------------------------ #

    def _build_overview(self, analysis: Dict) -> str:
        stats = analysis["stats"]
        lines = [
            "### Project Statistics\n",
            "| Metric | Value |", "|--------|-------|",
            f"| Total Files Analyzed | {stats['total_files']} |",
            f"| Total Classes | {stats['total_classes']} |",
            f"| Total Functions | {stats['total_functions']} |",
            f"| Total API Endpoints Detected | {stats['total_api_endpoints']} |",
            f"| Total Lines of Code | {stats['total_lines']:,} |",
            "", "### Language Breakdown\n",
            "| Language | Files |", "|----------|-------|",
        ]
        for lang, count in sorted(stats["languages"].items(), key=lambda x: -x[1]):
            lines.append(f"| {lang} | {count} |")
        lines += ["", "### Entry Points\n"]
        if stats["entry_points"]:
            for ep in stats["entry_points"]:
                lines.append(f"- `{ep}`")
        else:
            lines.append("_No entry points auto-detected._")
        lines += ["", "### Project Structure\n", "```", analysis["file_tree"], "```"]
        return "\n".join(lines)

    def _build_file_inventory(self, analysis: Dict) -> str:
        lines = [
            "| File | Language | Lines | Classes | Functions | Entry Point |",
            "|------|----------|------:|--------:|----------:|:-----------:|",
        ]
        for f in sorted(analysis["files"], key=lambda x: x["path"]):
            entry = "Yes" if f["is_entry_point"] else ""
            lines.append(
                f"| `{f['path']}` | {f['language']} | {f['lines']} | "
                f"{len(f['classes'])} | {len(f['functions'])} | {entry} |"
            )
        return "\n".join(lines)

    def _build_api_section(self, analysis: Dict) -> str:
        eps = [
            {**ep, "file": f["path"]}
            for f in analysis["files"]
            for ep in f["api_endpoints"]
        ]
        if not eps:
            return "_No API endpoints were detected in the analyzed files._"
        lines = [
            f"**{len(eps)} endpoint(s) detected:**\n",
            "| Method | Path | Defined In |",
            "|--------|------|------------|",
        ]
        for ep in eps:
            lines.append(f"| `{ep['method']}` | `{ep['path']}` | `{ep['file']}` |")
        return "\n".join(lines)

    def _build_dependencies(self, analysis: Dict) -> str:
        config = analysis["config"]
        lines = []
        blocks = [
            ("requirements.txt",  "text",       "Python (`requirements.txt`)"),
            ("pyproject.toml",    "toml",       "Python project config (`pyproject.toml`)"),
            ("package.json",      "json",       "Node.js (`package.json`)"),
            ("pom.xml",           "xml",        "Maven (`pom.xml`)"),
            ("go.mod",            "",           "Go modules (`go.mod`)"),
            ("Gemfile",           "ruby",       "Ruby (`Gemfile`)"),
            ("Dockerfile",        "dockerfile", "Docker (`Dockerfile`)"),
        ]
        for fname, lang, label in blocks:
            if fname in config:
                fence = f"```{lang}" if lang else "```"
                lines += [f"### {label}\n", fence, config[fname][:1200].strip(), "```\n"]
        if not lines:
            all_imp: set = set()
            for f in analysis["files"]:
                all_imp.update(f["imports"][:5])
            if all_imp:
                lines = ["_No dependency file found. Inferred imports:_\n", "```",
                         "\n".join(sorted(all_imp)[:40]), "```"]
            else:
                lines = ["_No dependency information detected._"]
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Shared Claude caller                                                  #
    # ------------------------------------------------------------------ #

    def _call_claude(self, prompt: str, section: str, max_tokens: int = 1024) -> str:
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except anthropic.APIError as e:
            logger.error("API error for %s: %s", section, e)
            return f"*Section unavailable — API error: {e}*"
        except Exception as e:
            logger.error("Error for %s: %s", section, e)
            return f"*Section unavailable: {e}*"
