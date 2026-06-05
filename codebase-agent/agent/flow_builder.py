"""
flow_builder.py
---------------
Uses Claude to generate documentation sections from parsed codebase metadata.
All selected sections are called in parallel via ThreadPoolExecutor.

Supports 10 sections (4 original + 6 new):
  functional_flow, data_flow, architecture, components,
  workflow, inputs_outputs, api_calls,
  component_data_flow, component_architecture, tech_stack
"""

import anthropic
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, Optional, Set

from .utils import get_logger, load_prompt, truncate

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are an expert software architect. "
    "Analyze codebases and generate precise, accurate technical documentation. "
    "Focus exclusively on what is actually present in the provided code — "
    "do not invent details or give generic advice."
)

SUMMARY_CAP = 40_000

# All section keys this builder can produce
ALL_FLOW_SECTIONS = {
    "functional_flow",
    "data_flow",
    "architecture",
    "components",
    "workflow",
    "inputs_outputs",
    "api_calls",
    "component_data_flow",
    "component_architecture",
    "tech_stack",
}


class FlowBuilder:

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic()
        self.model = model

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def build_flows(
        self,
        analysis: Dict[str, Any],
        selected_keys: Optional[Set[str]] = None,
    ) -> Dict[str, str]:
        """
        Generate only the requested sections in parallel.
        selected_keys: subset of ALL_FLOW_SECTIONS; None → original 4 sections.
        """
        if selected_keys is None:
            selected_keys = {"functional_flow", "data_flow", "architecture", "components"}

        keys = selected_keys & ALL_FLOW_SECTIONS
        if not keys:
            return {}

        code_summary = self._build_code_summary(analysis)

        # Map section key → generator lambda
        all_tasks = {
            "functional_flow":       lambda: self._get_functional_flow(code_summary, analysis),
            "data_flow":             lambda: self._get_data_flow(code_summary, analysis),
            "architecture":          lambda: self._get_architecture_summary(code_summary, analysis),
            "components":            lambda: self._get_component_relationships(code_summary, analysis),
            "workflow":              lambda: self._get_workflow(code_summary, analysis),
            "inputs_outputs":        lambda: self._get_inputs_outputs(code_summary, analysis),
            "api_calls":             lambda: self._get_api_calls(code_summary, analysis),
            "component_data_flow":   lambda: self._get_component_data_flow(code_summary, analysis),
            "component_architecture":lambda: self._get_component_architecture(code_summary, analysis),
            "tech_stack":            lambda: self._get_tech_stack(code_summary, analysis),
        }

        tasks = {k: all_tasks[k] for k in keys if k in all_tasks}

        results: Dict[str, str] = {}
        workers = min(4, len(tasks))
        print(f"   Running {len(tasks)} Claude section(s) in parallel (workers={workers})...")

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {executor.submit(fn): key for key, fn in tasks.items()}
            for future in as_completed(future_map):
                key = future_map[future]
                results[key] = future.result()
                print(f"   [done] {key}")

        return results

    # ------------------------------------------------------------------ #
    # Code summary builder                                                  #
    # ------------------------------------------------------------------ #

    def _build_code_summary(self, analysis: Dict) -> str:
        stats = analysis["stats"]
        parts = [
            f"Project: {analysis['project_name']}",
            f"Root: {analysis['root_path']}",
            f"Stats: {stats['total_files']} files | {stats['total_classes']} classes | "
            f"{stats['total_functions']} functions | {stats['total_lines']:,} lines",
            f"Languages: {', '.join(f'{k}({v})' for k, v in stats['languages'].items())}",
            f"Entry Points: {', '.join(stats['entry_points']) or 'Not detected'}",
            "",
            "=== PROJECT STRUCTURE ===",
            analysis["file_tree"],
            "",
        ]
        key_files   = [f for f in analysis["files"] if f["is_entry_point"]]
        other_files = [f for f in analysis["files"] if not f["is_entry_point"]]

        for f in key_files + other_files:
            parts.append(f"--- FILE: {f['path']} | {f['language']} | {f['lines']} lines ---")
            if f["classes"]:
                parts.append(f"  Classes   : {', '.join(c['name'] for c in f['classes'])}")
            if f["functions"]:
                parts.append(f"  Functions : {', '.join(fn['name'] for fn in f['functions'][:12])}")
            if f["api_endpoints"]:
                ep_str = ", ".join(f"{e['method']} {e['path']}" for e in f["api_endpoints"])
                parts.append(f"  Endpoints : {ep_str}")
            if f["imports"]:
                parts.append(f"  Imports   : {', '.join(f['imports'][:8])}")
            parts.append("")
            parts.append(f["content"][:3000])
            parts.append("")

        for name, content in analysis["config"].items():
            parts.append(f"=== CONFIG: {name} ===")
            parts.append(content[:800])
            parts.append("")

        return truncate("\n".join(parts), SUMMARY_CAP)

    # ------------------------------------------------------------------ #
    # Section prompt methods                                               #
    # ------------------------------------------------------------------ #

    def _get_functional_flow(self, cs: str, analysis: Dict) -> str:
        project = analysis["project_name"]
        entries = ", ".join(analysis["stats"]["entry_points"]) or "unknown"
        return self._call_claude(f"""Analyze project "{project}" and describe its FUNCTIONAL FLOW.
Entry points: {entries}

{cs}

---
Generate a detailed **Functional Flow** covering:
1. **Application Startup** — initialization, config loading, service wiring
2. **Main Execution Paths** — numbered step-by-step flows for primary use cases
3. **Key Function Call Chains** — which function calls which, across files
4. **Decision Points** — branches, conditionals, business logic gates
5. **Error Handling Flows** — how exceptions propagate
6. **Shutdown / Cleanup** — teardown sequence

Use `->` arrows for flow, numbered lists for steps, code blocks for signatures.
Reference actual function names and file paths. Do NOT invent details.""", "functional_flow")

    def _get_data_flow(self, cs: str, analysis: Dict) -> str:
        return self._call_claude(f"""Analyze project "{analysis['project_name']}" and describe its DATA FLOW.

{cs}

---
Generate a detailed **Data Flow Analysis** covering:
1. **Input Sources** — env vars, CLI args, HTTP requests, DB queries, user input
2. **Data Models & Schemas** — key classes/DTOs with their fields
3. **Transformation Pipeline** — parsing, validation, normalization, enrichment
4. **State Management** — where mutable state lives, how it is updated
5. **Output Destinations** — HTTP responses, DB writes, file writes, side effects
6. **API Request/Response Flows** — request lifecycle per endpoint
7. **Data Flow Diagram** — ASCII diagram showing data moving through the system

Use tables for data models, ASCII diagrams for overview. Reference actual names.""", "data_flow")

    def _get_architecture_summary(self, cs: str, analysis: Dict) -> str:
        langs = ", ".join(analysis["stats"]["languages"].keys())
        return self._call_claude(f"""Analyze project "{analysis['project_name']}" (languages: {langs}) — produce a TECHNICAL ARCHITECTURE SUMMARY.

{cs}

---
Generate a comprehensive **Technical Architecture Summary** covering:
1. **Architecture Pattern** — MVC, layered, microservice, event-driven, etc. Justify from code.
2. **Technology Stack** — frameworks, key libraries (from imports/config)
3. **Module/Layer Responsibilities** — what each module/package/folder does
4. **External Dependencies & Integrations** — third-party APIs, databases, auth
5. **Design Patterns** — with evidence from the code
6. **Configuration & Environment** — env vars, config files, CLI flags
7. **Scalability & Deployment Notes** — containers, cloud hints

Include a **Dependency Table** and a text-based **Architecture Diagram**.""", "architecture")

    def _get_component_relationships(self, cs: str, analysis: Dict) -> str:
        return self._call_claude(f"""Analyze project "{analysis['project_name']}" — map its COMPONENT RELATIONSHIPS.

{cs}

---
Generate a **Component Relationship Map** covering:
1. **Module Dependency Graph** — which files import from which (ASCII directed graph)
2. **Class Hierarchy** — inheritance trees and interface implementations
3. **Composition Relationships** — which classes own/use other classes
4. **Shared Utilities & Helpers** — common modules used across the codebase
5. **Service / Layer Boundaries** — how layers communicate
6. **Circular Dependency Warnings** — flag circular imports or tight coupling
7. **Coupling & Cohesion Notes** — areas worth refactoring

Use ASCII dependency graphs and tables. Flag warnings in a dedicated sub-section.""", "components")

    def _get_workflow(self, cs: str, analysis: Dict) -> str:
        return self._call_claude(f"""Analyze project "{analysis['project_name']}" — describe its END-TO-END WORKFLOW.

{cs}

---
Generate a detailed **Workflow Document** covering:
1. **System Overview** — what this system does from a user/operator perspective
2. **Trigger Points** — what initiates each workflow (user action, event, schedule, API call)
3. **Step-by-Step Workflow** — numbered flow from trigger to completion for each major workflow
4. **Decision Gates** — where the system branches based on conditions
5. **Integration Points** — where the system interacts with external services
6. **Success & Failure Paths** — what happens on success vs. error
7. **Workflow Diagram** — ASCII diagram of the main workflow

Use numbered steps, `->` arrows for flow direction, code blocks for key function calls.
Ground every step in actual code — reference real file and function names.""", "workflow")

    def _get_inputs_outputs(self, cs: str, analysis: Dict) -> str:
        return self._call_claude(f"""Analyze project "{analysis['project_name']}" — document all INPUTS AND OUTPUTS.

{cs}

---
Generate a complete **Project Inputs & Outputs** document covering:

**INPUTS:**
1. **User Inputs** — form fields, query params, request bodies (with data types)
2. **Configuration Inputs** — env vars, config files, CLI arguments
3. **External Data Inputs** — API responses consumed, database reads, file reads
4. **Event Inputs** — WebSocket messages, queue messages, webhooks

**OUTPUTS:**
1. **API Responses** — endpoints and their response shapes
2. **UI Renders** — pages/components rendered and what data they display
3. **File Outputs** — files written, exports generated
4. **External API Calls** — services called, request payloads sent
5. **State Changes** — database writes, cache updates, side effects

Use tables for structured inputs/outputs. Include data types and format where detectable.""", "inputs_outputs")

    def _get_api_calls(self, cs: str, analysis: Dict) -> str:
        return self._call_claude(f"""Analyze project "{analysis['project_name']}" — document all API CALLS.

{cs}

---
Generate a detailed **API Calls Analysis** covering:
1. **Outgoing HTTP Calls** — every external API call with method, endpoint, payload shape, response shape
2. **Internal API Endpoints** — every route defined in this codebase with method, path, handler function
3. **Authentication on Calls** — how auth tokens/headers are attached
4. **Error Handling for API Calls** — how failures are caught and handled
5. **API Call Patterns** — centralized client, per-feature calls, retry logic
6. **API Call Flow** — which component triggers which API call in response to what event

| Method | Endpoint | Caller File | Auth | Purpose |
Format each outgoing call as a table row. Include request/response types where visible.""", "api_calls")

    def _get_component_data_flow(self, cs: str, analysis: Dict) -> str:
        return self._call_claude(f"""Analyze project "{analysis['project_name']}" — describe DATA FLOW BETWEEN COMPONENTS with API context.

{cs}

---
Generate a detailed **Component Data Flow with API Context** covering:
1. **Component Interaction Map** — which components pass data to which others
2. **Props / Parameters Passed** — what data each component receives and from where
3. **API-Triggered Data Flows** — when an API call fires, what data propagates to which components
4. **State Propagation** — how shared state (Redux/Context/hooks) flows through the component tree
5. **Event Chains** — user action → API call → state update → re-render chain for each major feature
6. **Data Transformation at Boundaries** — how data is shaped before being passed between layers

For each major feature/module, draw a text-based diagram:
  [User Action] -> [Component] -> [API Call] -> [State Update] -> [Re-render]

Reference actual component names, hook names, and API function names.""", "component_data_flow")

    def _get_component_architecture(self, cs: str, analysis: Dict) -> str:
        return self._call_claude(f"""Analyze project "{analysis['project_name']}" — describe the COMPONENT TECHNICAL ARCHITECTURE including folder structure.

{cs}

---
Generate a **Component Technical Architecture** document covering:
1. **Folder Structure Breakdown** — annotated directory tree with each folder's responsibility
2. **Component Categories** — container components, presentational components, layout components, etc.
3. **Component Naming Conventions** — patterns observed in file/component naming
4. **File Organization Per Feature** — how a typical feature module is structured internally
5. **Shared vs Feature-Specific Components** — what lives in shared/ vs features/
6. **Component Lifecycle** — initialization, data fetching, rendering, cleanup patterns
7. **Component Communication Patterns** — props drilling, context, events, global state

Include the annotated folder tree as a code block. For each major directory, explain:
  - What it contains
  - Who owns/maintains it
  - What other directories depend on it""", "component_architecture")

    def _get_tech_stack(self, cs: str, analysis: Dict) -> str:
        langs = ", ".join(analysis["stats"]["languages"].keys())
        return self._call_claude(f"""Analyze project "{analysis['project_name']}" (detected languages: {langs}) — produce a comprehensive TECHNOLOGY STACK analysis.

{cs}

---
Generate a **Technology Stack** document covering:
1. **Core Languages & Runtimes** — language versions, runtime environments
2. **Frameworks & Libraries** — every framework detected with its version and purpose
3. **Build & Tooling** — build tool, bundler, linter, formatter, test runner
4. **State Management** — how application state is managed
5. **Styling Approach** — CSS framework, design system, styling methodology
6. **HTTP & API Layer** — HTTP client, API patterns (REST/GraphQL/etc.)
7. **Testing Stack** — test frameworks, testing approach detected
8. **DevOps / Infrastructure Hints** — Docker, CI config, deployment hints from config files

For each technology, provide:
| Technology | Version (if detectable) | Purpose | Evidence from Code |

Be specific — only list technologies with evidence in the provided code.""", "tech_stack")

    # ------------------------------------------------------------------ #
    # Shared Claude caller                                                  #
    # ------------------------------------------------------------------ #

    def _call_claude(self, prompt: str, section: str) -> str:
        logger.debug("Calling Claude for: %s", section)
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except anthropic.APIError as e:
            logger.error("API error for %s: %s", section, e)
            return f"*Section unavailable — API error: {e}*"
        except Exception as e:
            logger.error("Unexpected error for %s: %s", section, e)
            return f"*Section unavailable: {e}*"
