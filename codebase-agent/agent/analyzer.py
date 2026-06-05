"""
analyzer.py
-----------
Scans a local codebase folder and extracts structural metadata:
  - File inventory (language, size, lines)
  - Python AST parsing for classes, functions, imports
  - Regex-based extraction for JS/TS/Java/C# and other languages
  - API endpoint detection (Flask, FastAPI, Express, Django, Spring)
  - Entry point detection
  - Config/dependency file extraction
"""

import ast
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Any

from .utils import get_logger, read_file_safe, is_binary_file

logger = get_logger(__name__)

# Directories to skip entirely
SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    ".env", "dist", "build", ".idea", ".vscode", "coverage",
    ".pytest_cache", "htmlcov", ".eggs", "eggs", "target", "bin", "obj",
}

# Supported source file extensions
SUPPORTED_EXTENSIONS = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".jsx": "JSX",
    ".tsx": "TSX",
    ".java": "Java",
    ".cs": "C#",
    ".go": "Go",
    ".rb": "Ruby",
    ".php": "PHP",
    ".rs": "Rust",
    ".cpp": "C++",
    ".c": "C",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".sql": "SQL",
    ".sh": "Shell",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".xml": "XML",
    ".html": "HTML",
    ".css": "CSS",
    ".md": "Markdown",
}

# Dependency/config files to always include
CONFIG_FILES = {
    "requirements.txt", "package.json", "pom.xml", "build.gradle",
    "Dockerfile", "docker-compose.yml", "setup.py", "pyproject.toml",
    "Makefile", ".env.example", "go.mod", "Gemfile", "composer.json",
}

# Entry point filenames
ENTRY_POINT_NAMES = {
    "main.py", "app.py", "index.py", "server.py", "run.py", "wsgi.py", "asgi.py",
    "index.js", "app.js", "server.js", "main.js",
    "index.ts", "app.ts", "main.ts", "server.ts",
    "Application.java", "Main.java", "Program.cs", "main.go",
}

# Per-file content cap (characters sent to Claude)
FILE_CONTENT_CAP = 6000


class CodebaseAnalyzer:
    """
    Walks a project directory, parses source files, and returns a structured
    analysis dict that downstream agents consume.
    """

    def __init__(self, root_path: str, max_files: int = 50):
        self.root_path = Path(root_path).resolve()
        self.max_files = max_files

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self) -> Dict[str, Any]:
        """Main entry point. Returns full analysis dict."""
        logger.info("Scanning files in %s", self.root_path)
        files = self._scan_files()
        parsed = self._parse_files(files)
        config = self._extract_config(files)
        stats = self._compute_stats(parsed)

        return {
            "root_path": str(self.root_path),
            "project_name": self.root_path.name,
            "files": parsed,
            "config": config,
            "stats": stats,
            "file_tree": self._build_tree(),
        }

    # ------------------------------------------------------------------
    # File scanning
    # ------------------------------------------------------------------

    def _scan_files(self) -> List[Path]:
        """Collect all relevant source files, respecting max_files limit."""
        files: List[Path] = []
        for root, dirs, filenames in os.walk(self.root_path):
            dirs[:] = [
                d for d in dirs
                if d not in SKIP_DIRS and not d.startswith(".")
            ]
            for fname in filenames:
                fp = Path(root) / fname
                ext = fp.suffix.lower()
                if ext in SUPPORTED_EXTENSIONS or fname in CONFIG_FILES:
                    if not is_binary_file(fp):
                        files.append(fp)

        # Prioritize entry points and primary source languages
        def priority(p: Path) -> int:
            if p.name in ENTRY_POINT_NAMES:
                return 0
            if p.suffix in (".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".cs", ".go"):
                return 1
            return 2

        files.sort(key=lambda f: (priority(f), str(f)))
        return files[: self.max_files]

    # ------------------------------------------------------------------
    # File parsing
    # ------------------------------------------------------------------

    def _parse_files(self, files: List[Path]) -> List[Dict]:
        parsed = []
        for fp in files:
            content = read_file_safe(fp)
            if content is None:
                continue
            rel = str(fp.relative_to(self.root_path))
            info: Dict[str, Any] = {
                "path": rel,
                "language": SUPPORTED_EXTENSIONS.get(fp.suffix.lower(), "Unknown"),
                "size": fp.stat().st_size,
                "lines": len(content.splitlines()),
                "content": content[:FILE_CONTENT_CAP],
                "classes": [],
                "functions": [],
                "imports": [],
                "api_endpoints": [],
                "is_entry_point": self._is_entry_point(fp, content),
            }

            if fp.suffix == ".py":
                self._parse_python(info, content)
            else:
                self._parse_generic(info, content)

            parsed.append(info)
        return parsed

    # ------------------------------------------------------------------
    # Python AST parser
    # ------------------------------------------------------------------

    def _parse_python(self, info: Dict, content: str):
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return

        top_level_funcs: set = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = [
                    n.name
                    for n in ast.walk(node)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                bases: List[str] = []
                if hasattr(ast, "unparse"):
                    bases = [ast.unparse(b) for b in node.bases]
                info["classes"].append(
                    {
                        "name": node.name,
                        "line": node.lineno,
                        "methods": methods,
                        "bases": bases,
                    }
                )
                top_level_funcs.update(methods)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name not in top_level_funcs:
                    info["functions"].append(
                        {
                            "name": node.name,
                            "line": node.lineno,
                            "is_async": isinstance(node, ast.AsyncFunctionDef),
                            "args": [a.arg for a in node.args.args],
                        }
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    info["imports"].append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    info["imports"].append(node.module)

        info["api_endpoints"] = self._detect_endpoints_python(content)

    # ------------------------------------------------------------------
    # Generic regex parser (JS/TS/Java/C# etc.)
    # ------------------------------------------------------------------

    def _parse_generic(self, info: Dict, content: str):
        # Functions / methods
        func_patterns = [
            r"\bfunction\s+(\w+)\s*\(",                          # JS: function name(
            r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function|\()",  # JS arrow
            r"^\s*(?:public|private|protected|static|async)[\w\s]*\s+(\w+)\s*\([^)]*\)\s*(?:throws|->|\{|:)",  # Java/C#
            r"^\s*func\s+(\w+)\s*\(",                            # Go/Swift
            r"^\s*def\s+(\w+)\s*\(",                             # Ruby
        ]
        seen_funcs: set = set()
        for pattern in func_patterns:
            for m in re.finditer(pattern, content, re.MULTILINE):
                name = m.group(1)
                if name and len(name) > 1 and name not in seen_funcs:
                    seen_funcs.add(name)
                    line = content[: m.start()].count("\n") + 1
                    info["functions"].append({"name": name, "line": line})

        # Classes / interfaces
        for m in re.finditer(r"\b(?:class|interface|struct|enum)\s+(\w+)", content):
            info["classes"].append(
                {
                    "name": m.group(1),
                    "line": content[: m.start()].count("\n") + 1,
                }
            )

        # Imports
        import_patterns = [
            r"^import\s+[\"']([^\"']+)[\"']",         # JS/TS import
            r"^import\s+([\w.]+)",                     # Java/Go import
            r"require\s*\(\s*[\"']([^\"']+)[\"']\)",   # CommonJS require
            r"^from\s+([\w.]+)\s+import",              # Python-like
        ]
        seen_imports: set = set()
        for pattern in import_patterns:
            for m in re.finditer(pattern, content, re.MULTILINE):
                val = m.group(1)
                if val not in seen_imports:
                    seen_imports.add(val)
                    info["imports"].append(val)

        # API endpoints — Express/NestJS style
        for m in re.finditer(
            r"(?:app|router|this)\.(get|post|put|delete|patch)\s*\(\s*[\"']([^\"']+)[\"']",
            content,
            re.IGNORECASE,
        ):
            info["api_endpoints"].append(
                {"method": m.group(1).upper(), "path": m.group(2)}
            )

        # Spring/NestJS decorators
        for m in re.finditer(
            r"@(?:GetMapping|PostMapping|PutMapping|DeleteMapping|RequestMapping)\s*\(\s*[\"']?([^\"'\)]+)[\"']?\s*\)",
            content,
        ):
            method = m.group(0).split("(")[0].replace("@", "").replace("Mapping", "").upper()
            info["api_endpoints"].append({"method": method, "path": m.group(1)})

    # ------------------------------------------------------------------
    # API endpoint detection (Python frameworks)
    # ------------------------------------------------------------------

    def _detect_endpoints_python(self, content: str) -> List[Dict]:
        endpoints: List[Dict] = []

        # Flask / FastAPI decorators
        for m in re.finditer(
            r"@(?:app|router|blueprint|api_router)\."
            r"(get|post|put|delete|patch|options)\s*\(\s*[\"']([^\"']+)[\"']",
            content,
            re.IGNORECASE,
        ):
            endpoints.append({"method": m.group(1).upper(), "path": m.group(2)})

        # Django urlpatterns
        for m in re.finditer(r"(?:path|url)\s*\(\s*[\"']([^\"']+)[\"']", content):
            endpoints.append({"method": "GET|POST", "path": m.group(1)})

        return endpoints

    # ------------------------------------------------------------------
    # Entry point detection
    # ------------------------------------------------------------------

    def _is_entry_point(self, fp: Path, content: str) -> bool:
        if fp.name in ENTRY_POINT_NAMES:
            return True
        if '__name__' in content and '__main__' in content:
            return True
        return False

    # ------------------------------------------------------------------
    # Config / dependency files
    # ------------------------------------------------------------------

    def _extract_config(self, files: List[Path]) -> Dict[str, str]:
        config: Dict[str, str] = {}
        for fp in files:
            if fp.name in CONFIG_FILES:
                content = read_file_safe(fp)
                if content:
                    config[fp.name] = content[:2000]
        return config

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def _compute_stats(self, parsed: List[Dict]) -> Dict:
        langs: Dict[str, int] = {}
        for f in parsed:
            langs[f["language"]] = langs.get(f["language"], 0) + 1

        return {
            "total_files": len(parsed),
            "total_classes": sum(len(f["classes"]) for f in parsed),
            "total_functions": sum(len(f["functions"]) for f in parsed),
            "total_api_endpoints": sum(len(f["api_endpoints"]) for f in parsed),
            "total_lines": sum(f["lines"] for f in parsed),
            "languages": langs,
            "entry_points": [f["path"] for f in parsed if f["is_entry_point"]],
        }

    # ------------------------------------------------------------------
    # ASCII file tree
    # ------------------------------------------------------------------

    def _build_tree(self, max_depth: int = 4) -> str:
        lines: List[str] = [f"{self.root_path.name}/"]
        self._walk_tree(self.root_path, lines, "", 0, max_depth)
        return "\n".join(lines[:100])

    def _walk_tree(
        self,
        path: Path,
        lines: List[str],
        prefix: str,
        depth: int,
        max_depth: int,
    ):
        if depth >= max_depth:
            return
        try:
            entries = sorted(
                path.iterdir(),
                key=lambda p: (p.is_file(), p.name.lower()),
            )
            entries = [
                e for e in entries
                if e.name not in SKIP_DIRS and not e.name.startswith(".")
            ]
            for i, entry in enumerate(entries[:25]):
                is_last = i == len(entries) - 1
                connector = "└── " if is_last else "├── "
                lines.append(f"{prefix}{connector}{entry.name}")
                if entry.is_dir():
                    extension = "    " if is_last else "│   "
                    self._walk_tree(entry, lines, prefix + extension, depth + 1, max_depth)
        except PermissionError:
            pass
