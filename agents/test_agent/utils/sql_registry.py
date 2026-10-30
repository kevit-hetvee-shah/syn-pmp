"""Approved SQL template registry.

Pattern follows the "DeckSmith" approach (docs/build-decks-your-business-can-
trust-from-gold-data-products-on-databricks): each question the business can
ask is a reviewed template with typed parameters, stored as a `.sql` file
with header-comment metadata. The planner (a future LLM agent) only ever
picks a template ID and fills in its declared parameters — it never writes
or sees free SQL. An unknown template ID or an invalid parameter value is
rejected before anything would run.

This module parses and validates templates; it does NOT execute them —
execution lives in databricks_executor.py, which runs `executable_sql`
through the real warehouse driver's own bind-variable mechanism (never by
string-formatting a value into SQL text). `render()` below produces a
human/audit-readable rendering only (for the "complete source" provenance
record — see the DeckSmith article's `template_id` + `tables` +
`executed SQL` + `bound parameters` + `as_of` fact-entry shape), not
something to send to a database.

Longer-term note: the AI Foundry "Tools and Files" doc says Databricks is
"intentionally not a built-in connector — connect it through an MCP/Gateway
endpoint instead," i.e. the sanctioned production path is the AI Foundry MCP
Gateway → Databricks MCP (with AgentCore Identity's on-behalf-of token for
row-level security), not a direct driver connection from application code.
databricks_executor.py's direct `databricks-sql-connector` use is a pragmatic
local-dev/testing shortcut, not that sanctioned path — flagged explicitly so
this doesn't get mistaken for the production wiring later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "sql" / "templates"

_HEADER_LINE = re.compile(r"^--\s*(\w+):\s*(.*)$")
_TABLE_PLACEHOLDER = re.compile(r"\{\{table:([\w.]+)\}\}")
_PARAM_LINE = re.compile(
    r"^(?P<name>\w+)\s+(?P<type>\w+)\s*(?P<pattern>\S+)?\s*(?P<optional>optional)?$"
)


@dataclass
class SqlParam:
    name: str
    type: str
    pattern: str | None
    optional: bool

    def validate(self, value: object) -> str | None:
        """Return an error message, or None if `value` is acceptable."""
        if value is None:
            return None if self.optional else f"param '{self.name}' is required"
        if self.pattern and isinstance(value, str) and not re.fullmatch(self.pattern, value):
            return f"param '{self.name}' value {value!r} does not match required pattern {self.pattern!r}"
        return None


@dataclass
class SqlTemplate:
    id: str
    description: str
    kind: str
    params: list[SqlParam]
    sql: str
    source_path: Path

    def validate_params(self, provided: dict[str, object]) -> list[str]:
        errors: list[str] = []
        known_names = {p.name for p in self.params}
        for name in provided:
            if name not in known_names:
                errors.append(f"unknown param '{name}' for template '{self.id}'")
        for param in self.params:
            errors_for_param = param.validate(provided.get(param.name))
            if errors_for_param:
                errors.append(errors_for_param)
        return errors

    @property
    def executable_sql(self) -> str:
        """SQL ready to hand to the real driver: `{{table:...}}` resolved to
        the literal qualified name (safe — it's reviewed template content,
        not user input), `:param_name` placeholders left intact for the
        driver's own server-side parameter binding (databricks-sql-connector's
        default NATIVE mode uses exactly this paramstyle — confirmed against
        its actual Cursor.execute docstring, 2026-10-31). Never used for
        display/audit; see render() for that.
        """
        return _TABLE_PLACEHOLDER.sub(lambda m: m.group(1), self.sql)

    def render(self, provided: dict[str, object]) -> str:
        """Human/audit-readable rendering with params inlined. NOT for execution."""
        errors = self.validate_params(provided)
        if errors:
            raise ValueError(f"Cannot render '{self.id}': {'; '.join(errors)}")
        rendered = self.sql
        for param in self.params:
            value = provided.get(param.name)
            literal = "NULL" if value is None else f"'{value}'"
            rendered = rendered.replace(f":{param.name}", literal)
        return rendered


def _parse_param_line(raw: str) -> SqlParam:
    match = _PARAM_LINE.match(raw.strip())
    if not match:
        raise ValueError(f"Could not parse param declaration: {raw!r}")
    groups = match.groupdict()
    pattern = groups["pattern"]
    if pattern == "optional":
        # "name type optional" with no pattern — the regex above is greedy on
        # pattern, so re-check for this shape explicitly.
        pattern = None
        optional = True
    else:
        optional = groups["optional"] is not None
    return SqlParam(name=groups["name"], type=groups["type"], pattern=pattern, optional=optional)


def _parse_template_file(path: Path) -> SqlTemplate:
    lines = path.read_text(encoding="utf-8").splitlines()
    header: dict[str, str] = {}
    params: list[SqlParam] = []
    sql_lines: list[str] = []

    for line in lines:
        header_match = _HEADER_LINE.match(line)
        if header_match:
            key, value = header_match.groups()
            if key == "param":
                if value.strip() != "(none)":
                    params.append(_parse_param_line(value))
            else:
                header[key] = value.strip()
        elif line.strip().startswith("--"):
            continue  # a plain comment line, not metadata
        else:
            sql_lines.append(line)

    if "id" not in header:
        raise ValueError(f"{path}: missing '-- id: ...' header")

    return SqlTemplate(
        id=header["id"],
        description=header.get("description", ""),
        kind=header.get("kind", "list"),
        params=params,
        sql="\n".join(sql_lines).strip(),
        source_path=path,
    )


def load_templates(directory: Path | None = None) -> dict[str, SqlTemplate]:
    directory = directory or _TEMPLATES_DIR
    templates: dict[str, SqlTemplate] = {}
    for path in sorted(directory.glob("*.sql")):
        template = _parse_template_file(path)
        templates[template.id] = template
    return templates


TEMPLATES: dict[str, SqlTemplate] = load_templates()


def get_template(template_id: str) -> SqlTemplate:
    if template_id not in TEMPLATES:
        raise KeyError(f"Unknown SQL template '{template_id}'. Known: {sorted(TEMPLATES)}")
    return TEMPLATES[template_id]
