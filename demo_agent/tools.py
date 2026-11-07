"""Toy order-lookup tools. The `bug` argument switches on the one failure a tool carries."""

from __future__ import annotations

import json
from typing import Any

PENDING_HINT = "order is still processing; do not retry, report it as pending"
SILENT_ERROR_BODY = {"error": "customer not found"}

ORDERS: dict[str, dict[str, Any]] = {
    "A-1001": {"order_id": "A-1001", "status": "shipped", "total_usd": 42.0},
    "A-1002": {"order_id": "A-1002", "status": "delivered", "total_usd": 13.5},
    "A-1003": {"order_id": "A-1003", "status": "pending", "total_usd": 9.99},
}
ORDER_PAGES: tuple[tuple[str, ...], ...] = (("A-1001", "A-1002"), ("A-1003",))
CUSTOMERS: dict[str, dict[str, Any]] = {
    "ada lovelace": {"customer_id": "C-1", "name": "Ada Lovelace"},
}

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "get_order",
        "description": "Look up one order by id.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "list_orders_page",
        "description": "List one page of orders, starting at page 0.",
        "input_schema": {
            "type": "object",
            "properties": {"page": {"type": "integer", "minimum": 0}},
            "required": ["page"],
        },
    },
    {
        "name": "search_customer",
        "description": "Find a customer by full name.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
]


def execute_tool(name: str, tool_input: dict[str, Any], bug: str) -> tuple[dict[str, Any], str]:
    """Run one tool. Returns `(output, observation level)`."""
    if name == "get_order":
        return _get_order(str(tool_input.get("order_id", "")), bug)
    if name == "list_orders_page":
        return _list_orders_page(tool_input.get("page", 0)), "DEFAULT"
    if name == "search_customer":
        return _search_customer(str(tool_input.get("name", "")), bug)
    return {"error": f"unknown tool {name}"}, "ERROR"


def _get_order(order_id: str, bug: str) -> tuple[dict[str, Any], str]:
    if bug == "loop":
        # Deterministic loop bug: the hint makes a model repeat the identical call.
        return {"status": "pending", "hint": PENDING_HINT}, "DEFAULT"
    order = ORDERS.get(order_id)
    if order is None:
        return {"error": "order not found"}, "ERROR"
    return dict(order), "DEFAULT"


def _list_orders_page(page: Any) -> dict[str, Any]:
    index = page if isinstance(page, int) and 0 <= page < len(ORDER_PAGES) else None
    if index is None:
        return {"orders": []}
    return {"page": index, "orders": [dict(ORDERS[oid]) for oid in ORDER_PAGES[index]]}


def _search_customer(name: str, bug: str) -> tuple[dict[str, Any], str]:
    if bug == "silent_error":
        # Silent error bug: a failed lookup comes back as a 200-style body at DEFAULT level.
        return dict(SILENT_ERROR_BODY), "DEFAULT"
    customer = CUSTOMERS.get(name.strip().lower())
    if customer is None:
        return dict(SILENT_ERROR_BODY), "ERROR"
    return dict(customer), "DEFAULT"


def tool_result_text(output: dict[str, Any]) -> str:
    return json.dumps(output, ensure_ascii=False)
