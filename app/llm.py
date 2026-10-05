import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from . import config


class LLMError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str, model: str, num_ctx: int, timeout: float):
        self.base_url = base_url
        self.model = model
        self.num_ctx = num_ctx
        self.timeout = timeout

    def _payload(self, messages, model, stream, temperature, schema=None) -> dict:
        payload = {
            "model": model or self.model,
            "messages": messages,
            "stream": stream,
            "options": {"temperature": temperature, "num_ctx": self.num_ctx},
        }
        if schema is not None:
            payload["format"] = schema
        return payload

    @asynccontextmanager
    async def _post(self, payload: dict):
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                    if response.status_code == 404:
                        raise LLMError(
                            f"Model '{payload['model']}' is not installed. "
                            f"Run `ollama pull {payload['model']}`."
                        )
                    if response.status_code >= 400:
                        body = (await response.aread()).decode(errors="replace")
                        raise LLMError(f"Ollama returned {response.status_code}: {body[:300]}")
                    yield response
        except httpx.TimeoutException as exc:
            raise LLMError(
                "The model took too long to answer. Turn on Fast mode or raise OLLAMA_TIMEOUT."
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMError(
                f"Could not reach Ollama at {self.base_url}. Is `ollama serve` running?"
            ) from exc

    async def chat(
        self,
        messages: list[dict],
        schema: dict | None = None,
        temperature: float = 0.4,
        model: str | None = None,
    ) -> str:
        payload = self._payload(messages, model, False, temperature, schema)
        async with self._post(payload) as response:
            data = json.loads(await response.aread())
        return data["message"]["content"]

    async def chat_json(
        self,
        messages: list[dict],
        schema: dict,
        temperature: float = 0.2,
        model: str | None = None,
    ) -> dict:
        for attempt in range(2):
            content = await self.chat(messages, schema=schema, temperature=temperature, model=model)
            try:
                return json.loads(content)
            except json.JSONDecodeError as exc:
                if attempt:
                    raise LLMError("The model returned malformed JSON. Please try again.") from exc

    async def stream_chat(
        self, messages: list[dict], temperature: float = 0.4, model: str | None = None
    ) -> AsyncIterator[str]:
        payload = self._payload(messages, model, True, temperature)
        async with self._post(payload) as response:
            async for line in response.aiter_lines():
                if not line:
                    continue
                data = json.loads(line)
                if "error" in data:
                    raise LLMError(data["error"])
                chunk = data.get("message", {}).get("content", "")
                if chunk:
                    yield chunk

    async def status(self, fast_model: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
        except httpx.HTTPError:
            return {"reachable": False, "model": self.model, "model_available": False,
                    "fast_model": fast_model, "fast_model_available": False}

        installed = {m["name"] for m in response.json().get("models", [])}

        def has(name: str) -> bool:
            return name in installed or f"{name}:latest" in installed

        return {"reachable": True, "model": self.model, "model_available": has(self.model),
                "fast_model": fast_model, "fast_model_available": has(fast_model)}


def get_llm() -> OllamaClient:
    return OllamaClient(
        config.OLLAMA_URL, config.OLLAMA_MODEL, config.OLLAMA_NUM_CTX, config.OLLAMA_TIMEOUT
    )
