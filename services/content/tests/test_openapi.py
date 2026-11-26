"""openapi.yaml must describe exactly the routes Flask serves: same paths, same methods.

The paths and methods are read with a small line parser (no YAML library is needed): under
`paths:`, a path is a line indented 2 spaces ending in ':', a method one indented 4 spaces.
CI also checks the whole document against the OpenAPI specification (openapi-spec-validator).
"""

import re
from pathlib import Path

OPENAPI = Path(__file__).parent.parent / "openapi.yaml"
PATH_LINE = re.compile(r"^  (/\S*):\s*$")
METHOD_LINE = re.compile(r"^    (get|post|put|patch|delete):\s*$")


def documented_routes(text: str) -> set[tuple[str, str]]:
    """{(METHOD, /path/{param})} from the `paths:` section of an OpenAPI document."""
    routes, in_paths, path = set(), False, None
    for line in text.splitlines():
        if re.match(r"^\S", line):              # a top-level key starts or ends the paths section
            in_paths = line.startswith("paths:")
        elif in_paths and (match := PATH_LINE.match(line)):
            path = match.group(1)
        elif in_paths and path and (match := METHOD_LINE.match(line)):
            routes.add((match.group(1).upper(), path))
    return routes


def served_routes(app) -> set[tuple[str, str]]:
    """{(METHOD, /path/{param})} from Flask's URL map; <int:id> is written {id} as in OpenAPI."""
    routes = set()
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        path = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", rule.rule)
        routes |= {(method, path) for method in rule.methods - {"HEAD", "OPTIONS"}}
    return routes


def test_the_parser_reads_paths_and_methods():
    text = ("openapi: 3.0.3\npaths:\n  /a/{id}:\n    get:\n      summary: x\n    put:\n"
            "  /b:\n    post:\ncomponents:\n  x:\n")
    assert documented_routes(text) == {("GET", "/a/{id}"), ("PUT", "/a/{id}"), ("POST", "/b")}


def test_openapi_documents_every_route_and_nothing_else(app):
    assert documented_routes(OPENAPI.read_text(encoding="utf-8")) == served_routes(app)
