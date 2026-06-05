"""
app.py  —  Streamlit UI for the Codebase Analysis Agent
--------------------------------------------------------
Run:   streamlit run app.py
"""

import os
import zipfile
import tempfile
from pathlib import Path
from typing import Optional, Tuple

import streamlit as st

# ── Page config (must be first Streamlit call) ─────────────────────────────
st.set_page_config(
    page_title="Codebase Analysis Agent",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ─────────────────────────────────────────────────────────────────────
# Uses Streamlit's own CSS variables (--text-color, --secondary-background-color,
# --primary-color) so every custom element adapts automatically to both
# light mode and dark mode without any media queries.
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* ── Hero banner
   Self-contained dark gradient — readable in both modes. ── */
.hero {
    background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 60%, #3b82f6 100%);
    border-radius: 16px;
    padding: 2.5rem 3rem;
    margin-bottom: 2rem;
    color: white;
    box-shadow: 0 8px 32px rgba(59,130,246,0.25);
}
.hero h1 { font-size: 2.2rem; font-weight: 700; margin: 0 0 0.5rem 0; color: #ffffff; }
.hero p  { font-size: 1.05rem; color: #93c5fd; margin: 0; }

/* ── Section labels ── */
.section-label {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    color: #818cf8;          /* indigo-400: visible on both light & dark */
    text-transform: uppercase;
    margin-bottom: 0.3rem;
    display: block;
}

/* ── Metric cards
   Uses --secondary-background-color so Streamlit's theme controls the fill. ── */
[data-testid="metric-container"] {
    background: var(--secondary-background-color);
    border: 1px solid rgba(128,128,128,0.2);
    border-radius: 12px;
    padding: 1rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
[data-testid="metric-container"] [data-testid="stMetricLabel"] {
    font-size: 0.8rem;
    color: var(--text-color);
    opacity: 0.65;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    font-size: 1.6rem;
    font-weight: 700;
    color: var(--primary-color);
}

/* ── Download card
   Uses Streamlit CSS vars — no hardcoded light/dark colour. ── */
.download-card {
    background: var(--secondary-background-color);
    border: 1px solid rgba(128,128,128,0.22);
    border-radius: 14px;
    padding: 1.5rem;
    box-shadow: 0 2px 12px rgba(0,0,0,0.1);
    text-align: center;
    margin-bottom: 0.5rem;
}
.download-card h3 {
    color: var(--text-color);
    margin: 0.5rem 0 0.3rem 0;
    font-size: 1.1rem;
}
.download-card p {
    color: var(--text-color);
    opacity: 0.6;
    font-size: 0.88rem;
    margin: 0 0 1rem 0;
}

/* ── Download buttons ── */
.stDownloadButton > button {
    background: linear-gradient(135deg, #1e3a8a, #3b82f6) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 10px !important;
    padding: 0.65rem 1.5rem !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    width: 100%;
    box-shadow: 0 4px 12px rgba(59,130,246,0.35) !important;
    transition: all 0.2s !important;
}
.stDownloadButton > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 16px rgba(59,130,246,0.5) !important;
}

/* ── Analyse button ── */
div[data-testid="stButton"] > button[kind="primary"] {
    background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
    color: #ffffff;
    border: none;
    border-radius: 10px;
    padding: 0.8rem 2rem;
    font-size: 1.05rem;
    font-weight: 600;
    width: 100%;
    box-shadow: 0 4px 16px rgba(59,130,246,0.35);
    transition: all 0.2s;
}
div[data-testid="stButton"] > button[kind="primary"]:hover {
    box-shadow: 0 6px 20px rgba(59,130,246,0.5);
    transform: translateY(-1px);
}
div[data-testid="stButton"] > button[kind="primary"]:disabled {
    background: rgba(128,128,128,0.3) !important;
    color: rgba(128,128,128,0.7) !important;
    box-shadow: none !important;
    transform: none !important;
    cursor: not-allowed;
}

/* ── Sidebar
   NO background override — let Streamlit's theme control the sidebar fill.
   Only typography weight is set here. ── */
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stSlider label,
[data-testid="stSidebar"] .stTextInput label,
[data-testid="stSidebar"] .stRadio label {
    font-weight: 600;
    color: var(--text-color) !important;
}

/* ── Sidebar divider ── */
[data-testid="stSidebar"] hr {
    border-color: rgba(128,128,128,0.2);
}

/* ── Tip box
   Uses semi-transparent indigo that reads well on any background. ── */
.tip-box {
    background: rgba(99,102,241,0.1);
    border-left: 4px solid #818cf8;
    border-radius: 0 8px 8px 0;
    padding: 0.8rem 1rem;
    font-size: 0.88rem;
    color: var(--text-color);
    margin-top: 1rem;
    line-height: 1.6;
}
.tip-box b { color: #818cf8; }
</style>
""", unsafe_allow_html=True)


# ── Constants ────────────────────────────────────────────────────────────────
_SKIP_DIRS = {
    "node_modules", ".git", ".svn", ".hg",
    "__pycache__", ".pytest_cache", ".mypy_cache",
    "dist", "build", ".next", ".nuxt", "out",
    ".venv", "venv", "env",
    "coverage", ".nyc_output", "htmlcov",
    ".idea", ".vscode",
    "target", "bin", "obj", ".gradle", ".mvn",
}

MODEL_OPTIONS = {
    "claude-sonnet-4-6":          "Sonnet 4.6  —  Recommended (fast, high quality)",
    "claude-opus-4-8":            "Opus 4.8  —  Best quality (slower)",
    "claude-haiku-4-5-20251001":  "Haiku 4.5  —  Fastest & cheapest",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_env_key() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ANTHROPIC_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                os.environ["ANTHROPIC_API_KEY"] = key
                return key
    return ""


def _should_skip(zip_path: str) -> bool:
    return any(p in _SKIP_DIRS for p in zip_path.replace("\\", "/").split("/"))


def _extract_zip(uploaded_file, dest_dir: str) -> Tuple[str, int, int]:
    extracted = skipped = 0
    with zipfile.ZipFile(uploaded_file) as zf:
        for member in zf.infolist():
            if _should_skip(member.filename):
                skipped += 1
                continue
            target = Path(dest_dir) / member.filename
            try:
                target.resolve().relative_to(Path(dest_dir).resolve())
            except ValueError:
                skipped += 1
                continue
            zf.extract(member, dest_dir)
            extracted += 1

    entries = [e for e in Path(dest_dir).iterdir() if not e.name.startswith(("__", "."))]
    root = str(entries[0]) if len(entries) == 1 and entries[0].is_dir() else dest_dir
    return root, extracted, skipped


def _run_pipeline(
    folder, model, max_files, progress, selected_sections: set
) -> Tuple[str, Optional[bytes], dict]:
    from agent.analyzer import CodebaseAnalyzer
    from agent.flow_builder import FlowBuilder, ALL_FLOW_SECTIONS
    from agent.doc_generator import DocumentationGenerator
    from agent.pdf_generator import PDFGenerator

    # Step 1 — Scan
    progress.write("**Step 1 / 4** — Scanning and parsing files...")
    analyzer = CodebaseAnalyzer(folder, max_files=max_files)
    analysis = analyzer.analyze()
    s = analysis["stats"]
    progress.write(
        f"   Found **{s['total_files']}** files · **{s['total_classes']}** classes · "
        f"**{s['total_functions']}** functions · **{s['total_lines']:,}** lines"
    )

    # Step 2 — Parallel Claude calls (only for selected flow sections)
    flow_keys = selected_sections & ALL_FLOW_SECTIONS
    if flow_keys:
        progress.write(
            f"**Step 2 / 4** — Running **{len(flow_keys)}** analysis section(s) in parallel: "
            f"`{'`, `'.join(sorted(flow_keys))}`"
        )
        flows = FlowBuilder(model=model).build_flows(analysis, selected_keys=flow_keys)
        progress.write(f"   {len(flows)} flow section(s) complete.")
    else:
        flows = {}
        progress.write("**Step 2 / 4** — No AI flow sections selected, skipping.")

    # Step 3 — Documentation assembly (AI + static, only selected)
    progress.write("**Step 3 / 4** — Assembling documentation...")
    report_md = DocumentationGenerator(model=model).generate(
        analysis, flows, selected_sections=selected_sections
    )
    progress.write("   Documentation assembled.")

    # Step 4 — PDF
    progress.write("**Step 4 / 4** — Converting to PDF...")
    pdf_bytes: Optional[bytes] = None
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf_path = Path(tmp.name)
    try:
        ok = PDFGenerator().generate(report_md, str(pdf_path))
        if ok and pdf_path.exists() and pdf_path.stat().st_size > 0:
            pdf_bytes = pdf_path.read_bytes()
            progress.write(f"   PDF ready — {len(pdf_bytes) // 1024:,} KB")
        else:
            progress.write("   PDF could not be generated — Markdown still available.")
    finally:
        pdf_path.unlink(missing_ok=True)

    return report_md, pdf_bytes, s


# ── Sidebar ──────────────────────────────────────────────────────────────────

def _sidebar() -> Tuple[str, str, int, str]:
    with st.sidebar:
        st.markdown("## ⚙️ Settings")
        st.divider()

        # ── API Key ──────────────────────────────────────────────────────
        env_key = _load_env_key()
        if env_key:
            st.session_state["api_key"] = env_key
            st.success("API key loaded", icon="✅")
        else:
            st.markdown("**Anthropic API Key**")
            entered = st.text_input(
                "API Key",
                type="password",
                value=st.session_state.get("api_key", ""),
                placeholder="sk-ant-...",
                label_visibility="collapsed",
            )
            if entered:
                st.session_state["api_key"] = entered
            st.caption("[Get your key →](https://console.anthropic.com)")

        st.divider()

        # ── Model ────────────────────────────────────────────────────────
        st.markdown("**Model**")
        model_key = st.radio(
            "Model",
            options=list(MODEL_OPTIONS.keys()),
            format_func=lambda k: MODEL_OPTIONS[k],
            index=0,
            label_visibility="collapsed",
        )

        st.divider()

        # ── Max files ────────────────────────────────────────────────────
        st.markdown("**Max files to analyse**")
        max_files = st.slider(
            "Max files",
            min_value=10, max_value=100, value=50, step=10,
            label_visibility="collapsed",
            help="More files = more thorough but slower.",
        )

        st.divider()

        # ── Output format ────────────────────────────────────────────────
        st.markdown("**Output Format**")
        fmt = st.radio(
            "Format",
            options=["Both (PDF + Markdown)", "PDF only", "Markdown only"],
            label_visibility="collapsed",
        )

        st.divider()

        st.markdown("""
<div class="tip-box">
<b>Tips for faster results</b><br>
• Sonnet is 3x faster than Opus<br>
• Pick a single section for a quick report<br>
• Haiku is best for very large repos
</div>
""", unsafe_allow_html=True)

    return st.session_state.get("api_key", ""), model_key, max_files, fmt


# ── Section dropdown catalogue ────────────────────────────────────────────────
# Each entry: (display label, set of internal keys to generate)
# "Full Report" generates everything; individual options generate one section.

_ALL_KEYS = {
    "executive_summary", "project_overview", "architecture", "functional_flow",
    "data_flow", "components", "workflow", "inputs_outputs", "api_calls",
    "component_data_flow", "component_architecture", "tech_stack",
    "file_inventory", "api_endpoints", "dependencies", "onboarding",
}

DROPDOWN_OPTIONS = [
    ("Full Report  (all sections)",                          _ALL_KEYS),
    ("Executive Summary",                                    {"executive_summary"}),
    ("Project Overview",                                     {"project_overview"}),
    ("Technical Architecture",                               {"architecture"}),
    ("Functional Flow",                                      {"functional_flow"}),
    ("Data Flow Analysis",                                   {"data_flow"}),
    ("Component Relationships",                              {"components"}),
    ("Workflow",                                             {"workflow"}),
    ("Project Inputs & Outputs",                            {"inputs_outputs"}),
    ("API Calls Analysis",                                   {"api_calls"}),
    ("Data Flow Between Components  (with API Context)",     {"component_data_flow"}),
    ("Component Technical Architecture + Folder Structure",  {"component_architecture"}),
    ("Technology Stack",                                     {"tech_stack"}),
    ("File Inventory",                                       {"file_inventory"}),
    ("API Endpoints",                                        {"api_endpoints"}),
    ("Dependencies",                                         {"dependencies"}),
    ("Developer Onboarding Guide",                           {"onboarding"}),
]


# ── Main UI ──────────────────────────────────────────────────────────────────

def main():
    api_key, model, max_files, output_format = _sidebar()

    # ── Hero ────────────────────────────────────────────────────────────────
    st.markdown("""
<div class="hero">
    <h1>🔍 Codebase Analysis Agent</h1>
    <p>Upload your project as a ZIP, choose what to generate, and download
       a complete AI-powered documentation report in minutes.</p>
</div>
""", unsafe_allow_html=True)

    # ── Step 1 — Upload ──────────────────────────────────────────────────────
    st.markdown('<span class="section-label">Step 1 — Upload your project</span>', unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        "Drag and drop your project ZIP here, or click Browse files",
        type=["zip"],
        help="node_modules, .git, dist, build are automatically skipped — ZIP size doesn't matter.",
    )

    if uploaded_file:
        size_mb = uploaded_file.size / (1024 * 1024)
        st.success(
            f"**{uploaded_file.name}** ready ({size_mb:.1f} MB) — "
            "node_modules, .git, dist will be skipped automatically.",
            icon="📦",
        )

    st.divider()

    # ── Step 2 — Choose what to generate ────────────────────────────────────
    st.markdown('<span class="section-label">Step 2 — Choose what to generate</span>', unsafe_allow_html=True)
    st.markdown("#### Select a document type")

    dropdown_labels = [label for label, _ in DROPDOWN_OPTIONS]

    chosen_label = st.selectbox(
        "Document type",
        options=dropdown_labels,
        index=0,
        label_visibility="collapsed",
        help="Select 'Full Report' for complete documentation, or pick one section to generate a focused document.",
    )

    # Map chosen label → set of section keys
    selected_sections = next(keys for lbl, keys in DROPDOWN_OPTIONS if lbl == chosen_label)

    # Description chip
    DESCRIPTIONS = {
        "Full Report  (all sections)":
            "Generates all 16 sections — architecture, flows, components, onboarding, and more.",
        "Executive Summary":
            "High-level overview: what the project does, its architecture style, and key strengths.",
        "Project Overview":
            "Stats, language breakdown, entry points, and the project folder structure.",
        "Technical Architecture":
            "Architecture pattern, technology stack, modules, design patterns, and deployment hints.",
        "Functional Flow":
            "Step-by-step execution paths, function call chains, and error handling flows.",
        "Data Flow Analysis":
            "Inputs, data models, transformations, state management, and output destinations.",
        "Component Relationships":
            "Module dependency graph, class hierarchy, shared utilities, and coupling analysis.",
        "Workflow":
            "End-to-end workflow: triggers, steps, decision gates, integration points, and diagrams.",
        "Project Inputs & Outputs":
            "Every input the system accepts and every output it produces, with data types.",
        "API Calls Analysis":
            "All outgoing HTTP calls, internal endpoints, auth patterns, and error handling.",
        "Data Flow Between Components  (with API Context)":
            "How data moves between components including API call context and state propagation.",
        "Component Technical Architecture + Folder Structure":
            "Annotated folder tree, component categories, naming conventions, and ownership.",
        "Technology Stack":
            "Full technology stack table — frameworks, build tools, styling, testing, DevOps.",
        "File Inventory":
            "Table of every analyzed file with language, lines, classes, and functions.",
        "API Endpoints":
            "Auto-detected REST endpoints with method, path, and source file.",
        "Dependencies":
            "Project dependencies parsed from requirements.txt, package.json, and other config files.",
        "Developer Onboarding Guide":
            "Setup steps, how to run, where to start reading, key concepts, and common tasks.",
    }
    desc = DESCRIPTIONS.get(chosen_label, "")
    if desc:
        st.caption(f"**{chosen_label.strip()}** — {desc}")

    st.divider()
    
    # ── Step 3 — Analyse ────────────────────────────────────────────────────
    st.markdown('<span class="section-label">Step 3 — Run analysis</span>', unsafe_allow_html=True)

    can_run = bool(uploaded_file and api_key)
    if uploaded_file and not api_key:
        st.warning("Enter your Anthropic API key in the sidebar to continue.", icon="🔑")
    elif not uploaded_file:
        st.info("Upload a project ZIP in Step 1 to get started.", icon="⬆️")

    if can_run:
        c1, c2, c3 = st.columns(3)
        c1.info(f"Model: **{model.split('-')[1].capitalize()}**", icon="🤖")
        c2.info(f"Max files: **{max_files}**", icon="📁")
        c3.info(f"Format: **{output_format}**", icon="📄")

    clicked = st.button(
        "🔍  Generate Document",
        type="primary",
        disabled=not can_run,
        use_container_width=True,
    )

    # ── Pipeline ─────────────────────────────────────────────────────────────
    if clicked and can_run:
        for k in ("result_md", "result_pdf", "result_stats", "project_name"):
            st.session_state.pop(k, None)

        os.environ["ANTHROPIC_API_KEY"] = api_key

        with tempfile.TemporaryDirectory() as tmpdir:
            with st.status("Analysing your codebase...", expanded=True) as status:
                try:
                    status.write("**Extracting ZIP** (skipping build artifacts)...")
                    folder, n_ext, n_skip = _extract_zip(uploaded_file, tmpdir)
                    project_name = Path(folder).name
                    status.write(
                        f"   Project: **{project_name}** — "
                        f"{n_ext} files extracted, {n_skip:,} skipped"
                    )

                    report_md, pdf_bytes, stats = _run_pipeline(
                        folder, model, max_files, status, selected_sections
                    )

                    st.session_state["result_md"]    = report_md
                    st.session_state["result_pdf"]   = pdf_bytes
                    st.session_state["result_stats"] = stats
                    st.session_state["project_name"] = project_name

                    status.update(
                        label="✅ Analysis complete! Your report is ready below.",
                        state="complete",
                        expanded=False,
                    )

                except zipfile.BadZipFile:
                    status.update(label="Invalid ZIP file", state="error")
                    st.error("The uploaded file is not a valid ZIP archive.", icon="❌")
                except Exception as exc:
                    status.update(label="Analysis failed", state="error")
                    st.error(f"Error: {exc}", icon="❌")
                    with st.expander("Full error details"):
                        st.exception(exc)

    # ── Results ──────────────────────────────────────────────────────────────
    if st.session_state.get("result_md"):
        st.divider()
        project_name = st.session_state.get("project_name", "project")
        report_md    = st.session_state["result_md"]
        pdf_bytes    = st.session_state.get("result_pdf")
        stats        = st.session_state.get("result_stats", {})

        st.markdown(f'<span class="section-label">Step 3 — Download your report</span>', unsafe_allow_html=True)
        st.markdown(f"### Report ready: `{project_name}`")

        # Metrics
        if stats:
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Files Analysed",  stats.get("total_files", 0))
            m2.metric("Classes",         stats.get("total_classes", 0))
            m3.metric("Functions",       stats.get("total_functions", 0))
            m4.metric("API Endpoints",   stats.get("total_api_endpoints", 0))
            m5.metric("Lines of Code",   f"{stats.get('total_lines', 0):,}")

        st.markdown("")

        # Download cards
        want_pdf = output_format != "Markdown only"
        want_md  = output_format != "PDF only"
        dl1, dl2 = st.columns(2)

        with dl1:
            st.markdown("""
<div class="download-card">
    <div style="font-size:2.5rem">📄</div>
    <h3>PDF Report</h3>
    <p>Formatted document with styled tables,<br>code blocks, and colour-coded headings.</p>
</div>""", unsafe_allow_html=True)
            if want_pdf:
                if pdf_bytes:
                    st.download_button(
                        "⬇  Download PDF",
                        data=pdf_bytes,
                        file_name=f"{project_name}_report.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
                else:
                    st.warning("PDF generation failed. Download Markdown instead.", icon="⚠️")

        with dl2:
            st.markdown("""
<div class="download-card">
    <div style="font-size:2.5rem">📝</div>
    <h3>Markdown Report</h3>
    <p>Raw Markdown — open in VS Code,<br>Notion, Confluence, or any editor.</p>
</div>""", unsafe_allow_html=True)
            if want_md:
                st.download_button(
                    "⬇  Download Markdown",
                    data=report_md.encode("utf-8"),
                    file_name=f"{project_name}_report.md",
                    mime="text/markdown",
                    use_container_width=True,
                )

        # Preview
        st.divider()
        st.markdown("### Report Preview")

        tab1, tab2 = st.tabs(["Rendered Preview", "Raw Markdown"])
        with tab1:
            preview = "\n".join(report_md.split("\n")[:120])
            st.markdown(preview)
            if report_md.count("\n") > 120:
                st.caption(f"Showing first 120 lines. Download the full report for all {report_md.count(chr(10)):,} lines.")
        with tab2:
            st.code("\n".join(report_md.split("\n")[:80]), language="markdown")

        # Re-analyse
        st.divider()
        if st.button("↩  Analyse another project", use_container_width=False):
            for k in ("result_md", "result_pdf", "result_stats", "project_name"):
                st.session_state.pop(k, None)
            st.rerun()


if __name__ == "__main__":
    main()
