from __future__ import annotations

from pathlib import Path
from typing import Any


class SimpleYamlError(ValueError):
    """Raised when the small project YAML subset cannot be parsed."""


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load the YAML subset used by the IES design configuration files.

    The project intentionally avoids a hard dependency on PyYAML for this first
    interface pass. This parser supports the subset used by our config drafts:
    indentation-based dictionaries, scalar values, inline lists, and simple
    block lists of scalar values.
    """
    path = Path(path)
    lines = _preprocess(path.read_text(encoding="utf-8-sig"))
    if not lines:
        return {}
    result, index = _parse_mapping(lines, 0, lines[0][0])
    if index != len(lines):
        raise SimpleYamlError(f"Unexpected trailing YAML content in {path}: line {index + 1}")
    return result


def _preprocess(text: str) -> list[tuple[int, str]]:
    parsed: list[tuple[int, str]] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        line = _strip_comment(raw.rstrip())
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        parsed.append((indent, line.strip()))
    return parsed


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    for idx, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            if idx == 0 or line[idx - 1].isspace():
                return line[:idx].rstrip()
    return line


def _parse_mapping(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[dict[str, Any], int]:
    data: dict[str, Any] = {}
    while index < len(lines):
        current_indent, content = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            raise SimpleYamlError(f"Unexpected indentation before: {content}")
        if content.startswith("- "):
            raise SimpleYamlError("Top-level block lists are not supported in this config subset")
        key, value = _split_key_value(content)
        if value == "":
            if index + 1 >= len(lines) or lines[index + 1][0] <= current_indent:
                data[key] = {}
                index += 1
                continue
            next_indent, next_content = lines[index + 1]
            if next_content.startswith("- "):
                parsed_list, index = _parse_list(lines, index + 1, next_indent)
                data[key] = parsed_list
            else:
                parsed_map, index = _parse_mapping(lines, index + 1, next_indent)
                data[key] = parsed_map
        else:
            data[key] = _parse_scalar(value)
            index += 1
    return data, index


def _parse_list(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[list[Any], int]:
    items: list[Any] = []
    while index < len(lines):
        current_indent, content = lines[index]
        if current_indent < indent:
            break
        if current_indent != indent or not content.startswith("- "):
            break
        item = content[2:].strip()
        if item == "":
            if index + 1 >= len(lines):
                items.append(None)
                index += 1
            else:
                parsed_map, index = _parse_mapping(lines, index + 1, lines[index + 1][0])
                items.append(parsed_map)
        elif ":" in item and not item.startswith(('"', "'")):
            key, value = _split_key_value(item)
            entry: dict[str, Any] = {key: _parse_scalar(value) if value else {}}
            index += 1
            items.append(entry)
        else:
            items.append(_parse_scalar(item))
            index += 1
    return items, index


def _split_key_value(content: str) -> tuple[str, str]:
    if ":" not in content:
        raise SimpleYamlError(f"Expected key: value entry, got: {content}")
    key, value = content.split(":", 1)
    key = key.strip().strip('"').strip("'")
    return key, value.strip()


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "":
        return ""
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part.strip()) for part in _split_inline_list(inner)]
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    lower = value.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower in {"null", "none", "~"}:
        return None
    try:
        if any(ch in value for ch in [".", "e", "E"]):
            return float(value)
        return int(value)
    except ValueError:
        return value


def _split_inline_list(inner: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    for ch in inner:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        if ch == "," and not in_single and not in_double:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return parts
