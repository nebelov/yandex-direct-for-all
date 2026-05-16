# Yandex Performance MCP Routing

Preferred route order for production agents:

1. Use specialized local scripts and collectors from the relevant skill when available.
2. Use MCP/API routes for structured Yandex Direct, Metrika, Wordstat, Roistat, or Search API operations.
3. Use raw API calls only when a specialized route does not exist or cannot cover the needed field.
4. For any paginated report, exhaust every page before drawing conclusions or building apply packs.

Do not convert a failed first path into a tool outage. Retry through canonical local routes and record any fallback debt separately from the core workflow.
