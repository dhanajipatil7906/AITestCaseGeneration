"""Module-wise functional test case generation backed by the Claude LLM."""
import json
import os
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path

from anthropic import Anthropic, AuthenticationError

from app.config import settings


LLM_KEY_INVALID_WARNING = "Anthropic API key is invalid or expired; test cases were generated locally."

_anthropic_client: Anthropic | None = None
_ERROR_LOG_PATH = Path(__file__).resolve().parents[2] / "anthropic_error.txt"


def _log_anthropic_error(context: str, exc: Exception) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    with open(_ERROR_LOG_PATH, "a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {context}: {exc}\n")
        log_file.write(traceback.format_exc())
        log_file.write("\n")


def _get_anthropic_client() -> Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = Anthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client


def check_llm_status() -> str | None:
    """Return a warning message if the Anthropic key is configured but invalid/expired."""
    if not settings.anthropic_api_key:
        return None

    try:
        _get_anthropic_client().messages.create(
            model=settings.llm_model,
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
    except AuthenticationError as exc:
        _log_anthropic_error("check_llm_status", exc)
        return LLM_KEY_INVALID_WARNING
    except Exception as exc:
        _log_anthropic_error("check_llm_status", exc)

    return None


def module_key_for_path(path: str) -> str:
    """Group a file under its parent folder so related files (e.g. a .NET
    controller/service/model, or an Angular/React component's files) are
    analyzed together as one module."""
    normalized = (path or "").replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    if len(parts) <= 1:
        return "root"
    return "/".join(parts[:-1])


def generate_module_test_cases(
    module_name: str,
    files: list[dict],
    warnings: list[str] | None = None,
) -> list[dict]:
    """Return a list of {"file", "test_case"} entries for a module."""
    if settings.anthropic_api_key:
        try:
            return _generate_with_claude(module_name, files)
        except AuthenticationError as exc:
            _log_anthropic_error(f"generate_module_test_cases[{module_name}]", exc)
            if warnings is not None and LLM_KEY_INVALID_WARNING not in warnings:
                warnings.append(LLM_KEY_INVALID_WARNING)
        except Exception as exc:
            _log_anthropic_error(f"generate_module_test_cases[{module_name}]", exc)

    return _generate_heuristic(files)


def _build_module_prompt(module_name: str, files: list[dict]) -> str:
    file_sections = []
    for file_info in files:
        content = (file_info.get("content") or "")[:4000]
        file_sections.append(
            f"FILE: {file_info['path']} ({file_info.get('language', 'Unknown')})\n{content}"
        )
    joined = "\n\n".join(file_sections)

    return (
        "You are a senior QA engineer generating functional test cases for a software module.\n"
        f"Module: {module_name}\n"
        "The codebase may be a .NET Core API, an Angular app, a React app, or another stack.\n"
        "Analyze the source files below as a cohesive unit (for example a controller with its "
        "service/model, or a UI component with its template/styles) and produce functional test "
        "cases that reflect the module's real behavior.\n"
        "Return ONLY a JSON array, no commentary. Each element must have:\n"
        '  "file": the most relevant file path for the scenario,\n'
        '  "description": one concise functional test case sentence,\n'
        '  "sample_input": optional example input/data,\n'
        '  "negative_case": optional description of an invalid/negative scenario\n'
        "Cover positive, negative, and boundary scenarios across the module. Generate at most 8 "
        "test cases.\n\n"
        f"{joined}"
    )


def _generate_with_claude(module_name: str, files: list[dict]) -> list[dict]:
    prompt = _build_module_prompt(module_name, files)
    client = _get_anthropic_client()

    response = client.messages.create(
        model=settings.llm_model,
        max_tokens=1500,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )

    text = "".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    )

    parsed_results = _parse_test_cases_json(text, files)
    return parsed_results if parsed_results else _generate_heuristic(files)


def _parse_test_cases_json(text: str, files: list[dict]) -> list[dict]:
    valid_paths = {file_info["path"] for file_info in files}
    default_path = files[0]["path"] if files else "module"

    match = re.search(r"\[.*\]", text, re.DOTALL)
    raw_json = match.group(0) if match else text

    try:
        parsed = json.loads(raw_json)
    except Exception:
        return []

    if not isinstance(parsed, list):
        return []

    results = []
    for entry in parsed[:8]:
        if not isinstance(entry, dict) or not entry.get("description"):
            continue

        file_path = entry.get("file") or default_path
        if file_path not in valid_paths:
            file_path = default_path

        description = str(entry["description"]).strip()
        if entry.get("sample_input"):
            description += f" Sample: {entry['sample_input']}"
        if entry.get("negative_case"):
            description += f" Negative: {entry['negative_case']}"

        results.append({"file": file_path, "test_case": description})

    return results


def _generate_heuristic(files: list[dict]) -> list[dict]:
    """Deterministic fallback used when Claude is not configured or fails."""
    results = []
    for file_info in files:
        for test_case in _heuristic_file_test_cases(file_info):
            results.append({"file": file_info["path"], "test_case": test_case})
    return results


def _heuristic_file_test_cases(file_info: dict) -> list[str]:
    path = file_info.get("path") or ""
    language = file_info.get("language") or "Unknown"
    content = file_info.get("content") or ""
    name = os.path.basename(path)

    method_names = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", content)
    base_name = name.replace(".cs", "").replace(".py", "").replace(".js", "")

    sample_positive = f"a valid request payload for {base_name}"
    sample_negative = f"an invalid request with missing or malformed fields for {base_name}"

    if "controller" in path.lower() or (language.lower() == "c#" and "controller" in name.lower()):
        primary_method = method_names[0] if method_names else base_name
        return [
            f"Verify {primary_method} in {base_name} returns a successful response for valid input such as {sample_positive}.",
            f"Confirm {primary_method} in {base_name} handles invalid or malformed input such as {sample_negative} and returns an appropriate error.",
            f"Validate that {primary_method} in {base_name} processes edge-case inputs without breaking business logic.",
            f"Create a regression test for {primary_method} in {base_name} to ensure future updates do not break current behavior.",
            f"Confirm {primary_method} in {base_name} handles maximum valid input size correctly and returns the expected result.",
        ]

    if method_names:
        method = method_names[0]
        return [
            f"Verify {method} behaves correctly for normal input and returns the expected result using {sample_positive}.",
            f"Confirm {method} handles invalid data safely and returns an appropriate error response for {sample_negative}.",
            f"Validate that {method} remains stable with edge-case or boundary inputs.",
            f"Create a regression test for {method} to ensure the behavior stays stable over time.",
            f"Confirm {method} handles maximum valid input values correctly without failure.",
        ]

    return [
        f"Create a functional test for {base_name} using representative positive input such as {sample_positive}.",
        f"Add a negative test for {base_name} using invalid data like {sample_negative} to verify error handling.",
        f"Validate boundary or edge-case inputs for {base_name} to ensure stability.",
        f"Create a regression test for {base_name} to ensure future changes do not break behavior.",
        f"Confirm {base_name} handles maximum valid input sizes and returns expected results.",
    ]
