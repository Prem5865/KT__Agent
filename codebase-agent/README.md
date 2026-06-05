# Codebase Analysis Agent

An AI-powered tool that scans any local project folder and automatically generates
comprehensive developer documentation using the Claude API (Anthropic).

## What It Generates

| Section | Description |
|---------|-------------|
| Executive Summary | High-level purpose and approach |
| Project Overview | Stats, language breakdown, file tree |
| Technical Architecture | Patterns, stack, modules, design decisions |
| Functional Flow | Step-by-step execution paths from entry point |
| Data Flow Analysis | Inputs → transformations → outputs |
| Component Relationships | Module dependencies, class hierarchy |
| File Inventory | Every analyzed file with metadata |
| API Endpoints | Auto-detected REST endpoints |
| Dependencies | Parsed from requirements/package files |
| Onboarding Guide | Setup steps tailored to the detected stack |

---

## Prerequisites

- Python 3.9 or higher
- An [Anthropic API key](https://console.anthropic.com/)

---

## Setup

### 1. Clone / Open in VS Code

Open the `codebase-agent/` folder in VS Code.

### 2. Create a virtual environment

```powershell
# Windows PowerShell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux / Git Bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set your API key

**Option A — Environment variable (recommended)**

```powershell
# Windows PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

```bash
# macOS / Linux
export ANTHROPIC_API_KEY="sk-ant-..."
```

**Option B — `.env` file**

Copy `.env.example` to `.env` and fill in your key:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

---

## Usage

```bash
# Analyze a folder — outputs BOTH PDF and Markdown by default
python main.py /path/to/your/project

# PDF only
python main.py /path/to/your/project --format pdf

# Markdown only
python main.py /path/to/your/project --format md

# Custom output base name (extensions added automatically)
python main.py /path/to/project --output output/frontend_report
#   → output/frontend_report.md  and  output/frontend_report.pdf

# Analyze the current directory
python main.py .

# Analyze more files (default: 50)
python main.py /path/to/project --max-files 80

# Use a faster/cheaper model
python main.py /path/to/project --model claude-sonnet-4-6

# Enable verbose logging
python main.py /path/to/project --verbose
```

### Available Models

| Model | Speed | Quality | Use when |
|-------|-------|---------|----------|
| `claude-opus-4-8` (default) | Slower | Best | Thorough analysis |
| `claude-sonnet-4-6` | Medium | Great | Balanced speed/quality |
| `claude-haiku-4-5-20251001` | Fastest | Good | Quick/large codebases |

---

## Project Structure

```
codebase-agent/
│
├── main.py                  # CLI entry point
│
├── agent/
│   ├── __init__.py
│   ├── analyzer.py          # File scanner + AST/regex parser
│   ├── flow_builder.py      # Claude calls for 4 flow documents
│   ├── doc_generator.py     # Assembles final Markdown report
│   ├── pdf_generator.py     # Converts Markdown → HTML → PDF (xhtml2pdf)
│   └── utils.py             # Helpers: logging, file I/O, banner
│
├── prompts/
│   └── analysis_prompt.txt  # System prompt guidelines
│
├── output/
│   ├── report.md            # Generated Markdown report
│   └── report.pdf           # Generated PDF report
│
├── .env.example             # API key template
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

---

## How It Works

```
Your codebase folder
        │
        ▼
[1] CodebaseAnalyzer
    - Walks directory tree
    - Parses Python files with AST
    - Parses JS/TS/Java/C# with regex
    - Detects entry points, API endpoints
    - Extracts dependency files
        │
        ▼
[2] FlowBuilder  (4 Claude API calls)
    - Functional Flow
    - Data Flow
    - Technical Architecture
    - Component Relationships
        │
        ▼
[3] DocumentationGenerator  (2 Claude API calls)
    - Executive Summary
    - Onboarding Guide
    + Structured sections (no LLM needed)
        │
        ▼
output/report.md
```

---

## Supported Languages

Python, JavaScript, TypeScript, JSX/TSX, Java, C#, Go, Ruby, PHP, Rust, C/C++,
Swift, Kotlin, SQL, Shell scripts, YAML, JSON, XML, HTML, CSS

---

## Tips

- Point the agent at a **single service or module** for the sharpest results.
- The `--max-files` flag (default 50) controls how much code is sent to Claude.  
  Increase it for larger projects; the agent prioritizes entry points and primary source files.
- Output is standard Markdown — open with **Markdown Preview Enhanced** in VS Code  
  (`Ctrl+Shift+V`) for a rendered view.
- Re-run any time the codebase changes to keep docs current.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ANTHROPIC_API_KEY is not set` | Set the env var or create a `.env` file |
| `ModuleNotFoundError: anthropic` | Run `pip install -r requirements.txt` |
| Report is thin / missing sections | Increase `--max-files` or check that `.py`/`.js` files exist |
| `SyntaxError` in analyzer | The target file has Python 2 syntax; the agent skips it gracefully |
| Slow on large codebases | Use `--model claude-sonnet-4-6` or lower `--max-files` |
