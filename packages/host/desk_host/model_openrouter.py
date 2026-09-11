"""OpenRouter chat-completions ModelClient (tool calling)."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from .model_client import ModelStepResult, ToolCall


def _parse_tool_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            loaded = json.loads(raw)
            return loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


class OpenRouterModelClient:
    """OpenAI-compatible chat completions via OpenRouter."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_sec: float = 120.0,
    ) -> None:
        self.api_key = (api_key or os.environ.get("OPENROUTER_API_KEY") or "").strip()
        self.base_url = (
            base_url or os.environ.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1"
        ).rstrip("/")
        self.timeout_sec = timeout_sec

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        model: str,
    ) -> ModelStepResult:
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY required for host_loop execute")
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.environ.get("OPENROUTER_HTTP_REFERER", "https://github.com/Donnieboi03/virgil-desk"),
            "X-Title": os.environ.get("OPENROUTER_APP_TITLE", "Virgil Desk"),
        }
        async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=body,
            )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"OpenRouter HTTP {resp.status_code}: {(resp.text or '')[:800]}"
            )
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            # Some providers return content parts
            text_parts = [
                str(p.get("text") or "")
                for p in content
                if isinstance(p, dict) and p.get("type") in (None, "text")
            ]
            content = "".join(text_parts) or None
        elif content is not None:
            content = str(content)

        tool_calls: list[ToolCall] = []
        for tc in message.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") or {}
            tool_calls.append(
                ToolCall(
                    id=str(tc.get("id") or f"call_{len(tool_calls)}"),
                    name=str(fn.get("name") or ""),
                    arguments=_parse_tool_arguments(fn.get("arguments")),
                )
            )

        usage = None
        raw_usage = data.get("usage")
        if isinstance(raw_usage, dict):
            usage = {}
            pt = raw_usage.get("prompt_tokens") or raw_usage.get("input_tokens")
            ct = raw_usage.get("completion_tokens") or raw_usage.get("output_tokens")
            tt = raw_usage.get("total_tokens")
            if pt is not None:
                usage["prompt_tokens"] = int(pt)
            if ct is not None:
                usage["completion_tokens"] = int(ct)
            if tt is not None:
                usage["total_tokens"] = int(tt)
            cost = raw_usage.get("cost")
            if cost is None and isinstance(raw_usage.get("cost_details"), dict):
                cost = raw_usage["cost_details"].get("upstream_inference_cost")
            if cost is not None:
                try:
                    usage["cost_usd"] = float(cost)
                except (TypeError, ValueError):
                    pass
            if not usage:
                usage = None

        return ModelStepResult(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            raw=data,
        )
