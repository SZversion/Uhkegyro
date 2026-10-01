"""Code-derived output schema and bounded, non-sensitive validation feedback."""
from pathlib import Path

from backend.schemas.models import InterpretationOutput


def response_format() -> dict:
    schema = InterpretationOutput.model_json_schema()

    def strict(node):
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object":
                node["required"] = list(node.get("properties", {}))
                node["additionalProperties"] = False
            for value in node.values():
                strict(value)
        elif isinstance(node, list):
            for value in node:
                strict(value)

    strict(schema)
    return {"type": "json_schema", "json_schema": {
        "name": "interpretation_output", "strict": True, "schema": schema,
    }}


def validation_feedback(error) -> list[dict]:
    schema = InterpretationOutput.model_json_schema()
    fields = set(schema["properties"]) | {
        field for definition in schema.get("$defs", {}).values()
        for field in definition.get("properties", {})
    }
    feedback = []
    for item in error.errors(include_input=False, include_url=False)[:8]:
        code = item["type"]
        if not item["loc"]:
            message = item["msg"]
            code = "role_duplicate" if "역할당 최대" in message else "role_order" if "역할 순서" in message else "state_rules"
        path = [part if isinstance(part, int) or part in fields else "unknown_field" for part in item["loc"]]
        feedback.append({"path": path, "code": code})
    return feedback


def load_skill(path: str) -> str:
    from backend.services.llm import _extract_fenced_block

    return _extract_fenced_block(Path(path).read_text(encoding="utf-8"), "## Runtime instructions")
