"""MCP-сервер платного Yandex Cloud Search API с явными воротами."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from mcp.server.fastmcp import FastMCP

from detail import call_ai_search_with_yazeka, call_web_search, validate_input_data


mcp = FastMCP(name="Yandex Search API v2 with paid-call guard")


def error_result(message: str) -> str:
    return json.dumps({"status": "rejected", "error": message}, ensure_ascii=False, indent=2)


@mcp.tool()
def ai_search_with_yazeka(body: dict) -> str:
    """Платный порождающий поиск. Не вызывай его без явно выбранного платного режима."""
    if message := validate_input_data(body, {"query", "search_region"}):
        return error_result(message)
    try:
        value = json.loads(call_ai_search_with_yazeka(body))
        message = value.get("message") if isinstance(value, dict) else None
        sources = value.get("sources", []) if isinstance(value, dict) else []
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not isinstance(sources, list):
            return error_result("Порождающий поиск вернул ответ неверной схемы")
        used = [source.get("url") for source in sources if isinstance(source, dict) and source.get("used") is True and isinstance(source.get("url"), str)]
        return json.dumps({"status": "complete", "response": content, "sources": used}, ensure_ascii=False, indent=2)
    except Exception as exc:
        return error_result(str(exc))


def documents_from_xml(xml_content: str) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as exc:
        raise ValueError("Веб-поиск вернул неверный XML") from exc
    documents: list[dict[str, str]] = []
    for document in root.iter("doc"):
        url = (document.findtext("url") or "").strip()
        if not url:
            continue
        content = ""
        for field in ("headline", "title", "passage", "extended-text"):
            values = ["".join(node.itertext()).strip() for node in document.findall(field)]
            values = [value for value in values if value]
            if values:
                content = " ".join(values)
                break
        if content:
            documents.append({"data": content, "source": url})
    return documents


@mcp.tool()
def web_search(body: dict) -> str:
    """Платный веб-поиск. Не вызывай его без явно выбранного платного режима."""
    if message := validate_input_data(body, {"query", "search_region"}):
        return error_result(message)
    try:
        return json.dumps({"status": "complete", "responses": documents_from_xml(call_web_search(body))}, ensure_ascii=False, indent=2)
    except Exception as exc:
        return error_result(str(exc))


def main() -> None:
    """Запустить сервер через стандартный ввод-вывод."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
