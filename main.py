import json
import re
import warnings
from copy import deepcopy
from json import JSONDecodeError
from typing import Any, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from json_repair import repair_json
from jsonschema import Draft202012Validator, ValidationError
from pydantic import BaseModel, Field, field_validator


SERVICE_NAME = "JSONFix API"
MAX_TEXT_LENGTH = 200_000
MAX_BATCH_SIZE = 100

warnings.filterwarnings(
    "ignore",
    message='Field name "schema" in "RepairWithSchemaRequest" shadows an attribute in parent "BaseModel"',
    category=UserWarning,
)


app = FastAPI(
    title="JSON Repair & LLM Output Fixer API",
    description="Repair broken JSON and messy LLM outputs into valid JSON without external AI calls.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RepairRequest(BaseModel):
    text: str = Field(
        ...,
        min_length=1,
        max_length=MAX_TEXT_LENGTH,
        examples=["```json\n{name:'John', age:30,}\n```"],
    )
    return_string: bool = Field(True, examples=[True])


class ExtractRequest(BaseModel):
    text: str = Field(
        ...,
        min_length=1,
        max_length=MAX_TEXT_LENGTH,
        examples=["Sure, here is your data: ```json\n{name:'Sarah', role:'Founder'}\n``` Thanks!"],
    )


class ValidateRequest(BaseModel):
    json_string: str = Field(
        ...,
        min_length=1,
        max_length=MAX_TEXT_LENGTH,
        examples=['{"name":"John","age":30}'],
    )


class RepairWithSchemaRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH, examples=["{name:'John', age:'30'}"])
    schema: dict[str, Any] = Field(
        ...,
        examples=[
            {
                "type": "object",
                "required": ["name", "age"],
                "properties": {
                    "name": {"type": "string"},
                    "age": {"type": "number"},
                }
            }
        ],
    )


class BatchRepairRequest(BaseModel):
    items: list[str] = Field(
        ...,
        min_length=1,
        max_length=MAX_BATCH_SIZE,
        examples=[["{name:'John'}", "{name:'Sarah', age:25,}"]],
    )

    @field_validator("items")
    @classmethod
    def validate_item_lengths(cls, items: list[str]) -> list[str]:
        for index, item in enumerate(items):
            if not item:
                raise ValueError(f"items[{index}] must not be empty")
            if len(item) > MAX_TEXT_LENGTH:
                raise ValueError(f"items[{index}] exceeds {MAX_TEXT_LENGTH} characters")
        return items


def strip_markdown_fences(text: str) -> tuple[str, list[str]]:
    """Remove Markdown code fences and return the cleaned text plus fix labels."""
    stripped = text.strip()
    fixes: list[str] = []

    full_fence_match = re.fullmatch(
        r"```(?:json|javascript|js|JSON)?[ \t]*\r?\n?(.*?)\r?\n?```",
        stripped,
        flags=re.DOTALL,
    )
    if full_fence_match:
        return full_fence_match.group(1).strip(), ["removed_markdown_fence"]

    cleaned = re.sub(r"```(?:json|javascript|js|JSON)?[ \t]*\r?\n?", "", stripped)
    cleaned = cleaned.replace("```", "")
    if cleaned != stripped:
        fixes.append("removed_markdown_fence")

    return cleaned.strip(), fixes


def compact_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _repair_to_string(text: str) -> str:
    try:
        repaired = repair_json(text, return_objects=False)
    except TypeError:
        repaired = repair_json(text)

    if isinstance(repaired, str):
        return repaired
    return compact_json(repaired)


def parse_or_repair(text: str) -> tuple[bool, Any, Optional[str], list[str], Optional[str]]:
    cleaned, fixes = strip_markdown_fences(text)

    try:
        data = json.loads(cleaned)
        return True, data, compact_json(data), fixes, None
    except JSONDecodeError as strict_error:
        try:
            repaired_string = _repair_to_string(cleaned)
            data = json.loads(repaired_string)
            fixes.append("repaired_json")
            return True, data, compact_json(data), fixes, None
        except Exception as repair_error:
            return (
                False,
                None,
                None,
                fixes,
                f"Unable to parse or repair JSON. Strict parse error: {strict_error.msg}. Repair error: {repair_error}",
            )


def _balanced_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    opening = {"{": "}", "[": "]"}
    closing = {"}": "{", "]": "["}

    for start, char in enumerate(text):
        if char not in opening:
            continue

        stack = [char]
        in_string = False
        quote_char = ""
        escape = False

        for position in range(start + 1, len(text)):
            current = text[position]

            if in_string:
                if escape:
                    escape = False
                elif current == "\\":
                    escape = True
                elif current == quote_char:
                    in_string = False
                continue

            if current in ("'", '"'):
                in_string = True
                quote_char = current
                continue

            if current in opening:
                stack.append(current)
            elif current in closing:
                if not stack or stack[-1] != closing[current]:
                    break
                stack.pop()
                if not stack:
                    candidates.append(text[start : position + 1].strip())
                    break

    return sorted(candidates, key=len, reverse=True)


def extract_json_candidate(text: str) -> Optional[str]:
    stripped = text.strip()
    fenced_blocks = re.findall(
        r"```(?:json|javascript|js|JSON)?[ \t]*\r?\n?(.*?)\r?\n?```",
        stripped,
        flags=re.DOTALL,
    )

    candidates: list[str] = []
    for block in fenced_blocks:
        block = block.strip()
        if block:
            candidates.append(block)
            candidates.extend(_balanced_candidates(block))

    candidates.extend(_balanced_candidates(stripped))

    for candidate in candidates:
        success, _, _, _, _ = parse_or_repair(candidate)
        if success:
            return candidate

    return None


def _schema_type(schema: dict[str, Any]) -> set[str]:
    schema_type = schema.get("type")
    if isinstance(schema_type, str):
        return {schema_type}
    if isinstance(schema_type, list):
        return {item for item in schema_type if isinstance(item, str)}
    return set()


def _coerce_scalar(value: Any, schema: dict[str, Any]) -> Any:
    schema_types = _schema_type(schema)

    if isinstance(value, str):
        stripped = value.strip()

        if "boolean" in schema_types and stripped.lower() in {"true", "false"}:
            return stripped.lower() == "true"

        if "integer" in schema_types and re.fullmatch(r"[+-]?\d+", stripped):
            return int(stripped)

        if "number" in schema_types:
            try:
                if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", stripped):
                    return float(stripped) if any(marker in stripped for marker in ".eE") else int(stripped)
            except ValueError:
                return value

    return value


def coerce_types_for_schema(data: Any, schema: dict[str, Any]) -> Any:
    schema_types = _schema_type(schema)

    if isinstance(data, dict) and ("object" in schema_types or "properties" in schema):
        coerced = deepcopy(data)
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, property_schema in properties.items():
                if key in coerced and isinstance(property_schema, dict):
                    coerced[key] = coerce_types_for_schema(coerced[key], property_schema)
        return coerced

    if isinstance(data, list) and ("array" in schema_types or "items" in schema):
        item_schema = schema.get("items", {})
        if isinstance(item_schema, dict):
            return [coerce_types_for_schema(item, item_schema) for item in data]
        return data

    return _coerce_scalar(data, schema)


def validate_against_schema(data: Any, schema: dict[str, Any]) -> tuple[bool, list[str]]:
    try:
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(data), key=lambda error: list(error.path))
    except Exception as schema_error:
        return False, [f"Invalid JSON Schema: {schema_error}"]

    if not errors:
        return True, []

    return False, [_format_schema_error(error) for error in errors]


def _format_schema_error(error: ValidationError) -> str:
    path = ".".join(str(part) for part in error.absolute_path)
    location = path or "$"
    return f"{location}: {error.message}"


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "name": SERVICE_NAME,
        "title": "JSON Repair & LLM Output Fixer API",
        "description": "Repair broken JSON and messy LLM outputs into valid JSON.",
        "docs": "/docs",
        "health": "/health",
        "api_info": "/api-info",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/api-info")
def api_info() -> dict[str, Any]:
    return {
        "name": SERVICE_NAME,
        "description": "Repair broken JSON and messy LLM outputs into valid JSON.",
        "main_endpoints": ["/repair", "/extract", "/validate", "/repair-with-schema", "/batch-repair"],
        "use_cases": [
            "AI apps",
            "LLM output parsing",
            "automation workflows",
            "webhooks",
            "scrapers",
            "data cleaning",
        ],
        "disclaimer": "JSONFix attempts to repair malformed JSON but cannot guarantee semantic correctness.",
    }


@app.post("/repair")
def repair(request: RepairRequest) -> dict[str, Any]:
    success, data, json_string, fixes, error = parse_or_repair(request.text)
    return {
        "success": success,
        "data": data,
        "json_string": json_string if request.return_string and success else None,
        "fixes_applied": fixes,
        "error": error,
    }


@app.post("/extract")
def extract(request: ExtractRequest) -> dict[str, Any]:
    candidate = extract_json_candidate(request.text)
    if candidate is None:
        return {
            "success": False,
            "json_found": False,
            "data": None,
            "json_string": None,
            "error": "No JSON object or array candidate found in the provided text.",
        }

    success, data, json_string, _, error = parse_or_repair(candidate)
    return {
        "success": success,
        "json_found": True,
        "data": data,
        "json_string": json_string,
        "error": error,
    }


@app.post("/validate")
def validate(request: ValidateRequest) -> dict[str, Any]:
    try:
        data = json.loads(request.json_string)
        return {"valid": True, "data": data, "error": None}
    except JSONDecodeError as error:
        return {
            "valid": False,
            "data": None,
            "error": f"Invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}",
        }


@app.post("/repair-with-schema")
def repair_with_schema(request: RepairWithSchemaRequest) -> dict[str, Any]:
    success, data, _, _, error = parse_or_repair(request.text)
    if not success:
        return {
            "success": False,
            "data": None,
            "schema_valid": False,
            "schema_errors": [],
            "json_string": None,
            "error": error,
        }

    coerced_data = coerce_types_for_schema(data, request.schema)
    schema_valid, schema_errors = validate_against_schema(coerced_data, request.schema)

    return {
        "success": True,
        "data": coerced_data,
        "schema_valid": schema_valid,
        "schema_errors": schema_errors,
        "json_string": compact_json(coerced_data),
        "error": None,
    }


@app.post("/batch-repair")
def batch_repair(request: BatchRepairRequest) -> dict[str, Any]:
    results = []

    for index, item in enumerate(request.items):
        success, data, json_string, _, error = parse_or_repair(item)
        results.append(
            {
                "index": index,
                "success": success,
                "data": data,
                "json_string": json_string,
                "error": error,
            }
        )

    successful = sum(1 for result in results if result["success"])

    return {
        "total": len(request.items),
        "successful": successful,
        "failed": len(request.items) - successful,
        "results": results,
    }
