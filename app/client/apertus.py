"""Apertus sovereign LLM client with CSCS primary inference, Hugging Face fallback, and real-time streaming."""

import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple
import httpx

from app.config import Settings, get_settings

logger = logging.getLogger("apertus.client")


class ApertusClient:
    """Async client connecting to sovereign CSCS Inference API with automated Hugging Face fallback and SSE streaming."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        force_fallback: bool = False,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Dispatch non-streaming chat completion to CSCS inference primary, falling back to Hugging Face."""
        start_time = time.perf_counter()
        req_model = model or self.settings.default_model

        if not force_fallback and req_model not in ("hf-fallback", "hf-apertus-8b"):
            try:
                cscs_response, cscs_meta = await self._call_cscs(
                    messages=messages,
                    model=req_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                total_latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
                cscs_meta["total_client_latency_ms"] = total_latency_ms
                return cscs_response, cscs_meta
            except Exception as exc:
                logger.warning(
                    "CSCS Inference API failed (%s). Initiating Sovereign Failover to Hugging Face.",
                    str(exc),
                )
                failover_reason = str(exc)
        else:
            failover_reason = "Manual/test trigger or explicit HF selector"

        # Secondary / Failover: Hugging Face Inference API
        hf_response, hf_meta = await self._call_huggingface(
            messages=messages,
            model=req_model,
            temperature=temperature,
            max_tokens=max_tokens,
            failover_reason=failover_reason,
        )
        total_latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        hf_meta["total_client_latency_ms"] = total_latency_ms
        return hf_response, hf_meta

    async def chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        force_fallback: bool = False,
    ) -> AsyncGenerator[Tuple[str, Optional[Dict[str, Any]]], None]:
        """Asynchronously stream token chunks from CSCS with automatic failover to Hugging Face.

        Yields tuples of:
            - delta_content: The text fragment emitted by the LLM
            - metadata: Optional dict with backend info (emitted with the first or final chunk)
        """
        req_model = model or self.settings.default_model
        direct_hf = force_fallback or (req_model in ("hf-fallback", "hf-apertus-8b"))

        if not direct_hf:
            success = False
            cscs_model = self.settings.resolve_cscs_model(req_model)
            url = f"{self.settings.cscs_base_url.rstrip('/')}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.settings.cscs_api_key}",
                "Content-Type": "application/json",
                "User-Agent": "ApertusSovereignGate/1.0.0",
            }
            payload = {
                "model": cscs_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            }

            try:
                async with httpx.AsyncClient(timeout=self.settings.timeout_seconds) as client:
                    async with client.stream("POST", url, headers=headers, json=payload) as resp:
                        if resp.status_code == 200:
                            success = True
                            first = True
                            async for line in resp.aiter_lines():
                                line = line.strip()
                                if not line or not line.startswith("data:"):
                                    continue
                                data_str = line[5:].strip()
                                if data_str == "[DONE]":
                                    yield "", {"status": "DONE", "backend": "cscs-sovereign-primary"}
                                    break
                                try:
                                    chunk_json = json.loads(data_str)
                                    choices = chunk_json.get("choices", [])
                                    if choices:
                                        delta = choices[0].get("delta", {}).get("content", "")
                                        meta = None
                                        if first:
                                            meta = {
                                                "backend": "cscs-sovereign-primary",
                                                "model": cscs_model,
                                                "failover_active": False,
                                            }
                                            first = False
                                        if delta or meta:
                                            yield delta, meta
                                except Exception:
                                    continue
                        else:
                            logger.warning("CSCS Streaming returned %d: %s", resp.status_code, (await resp.aread())[:200])
            except Exception as exc:
                logger.warning("CSCS streaming failed with exception: %s. Switching to HF fallback.", str(exc))

            if success:
                return

        # Secondary / Failover: Hugging Face Streaming
        hf_model = self.settings.resolve_hf_model(req_model)
        url_hf = f"{self.settings.hf_base_url.rstrip('/')}/chat/completions"
        headers_hf = {
            "Authorization": f"Bearer {self.settings.hf_api_key}",
            "Content-Type": "application/json",
            "User-Agent": "ApertusSovereignGate/1.0.0",
        }
        payload_hf = {
            "model": hf_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=self.settings.timeout_seconds) as client:
            async with client.stream("POST", url_hf, headers=headers_hf, json=payload_hf) as resp_hf:
                if resp_hf.status_code != 200:
                    # Retry with default 8B on HF if specific model unsupported
                    payload_hf["model"] = "swiss-ai/Apertus-8B-Instruct-2509"
                    async with client.stream("POST", url_hf, headers=headers_hf, json=payload_hf) as retry_resp:
                        first = True
                        async for line in retry_resp.aiter_lines():
                            line = line.strip()
                            if not line or not line.startswith("data:"):
                                continue
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                yield "", {"status": "DONE", "backend": "huggingface-sovereign-fallback"}
                                break
                            try:
                                chunk_json = json.loads(data_str)
                                choices = chunk_json.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {}).get("content", "")
                                    meta = None
                                    if first:
                                        meta = {
                                            "backend": "huggingface-sovereign-fallback",
                                            "model": "swiss-ai/Apertus-8B-Instruct-2509",
                                            "failover_active": True,
                                        }
                                        first = False
                                    if delta or meta:
                                        yield delta, meta
                            except Exception:
                                continue
                        return

                first = True
                async for line in resp_hf.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        yield "", {"status": "DONE", "backend": "huggingface-sovereign-fallback"}
                        break
                    try:
                        chunk_json = json.loads(data_str)
                        choices = chunk_json.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {}).get("content", "")
                            meta = None
                            if first:
                                meta = {
                                    "backend": "huggingface-sovereign-fallback",
                                    "model": hf_model,
                                    "failover_active": True,
                                }
                                first = False
                            if delta or meta:
                                yield delta, meta
                    except Exception:
                        continue

    async def _call_cscs(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Call CSCS Inference API (OpenAI compatible)."""
        cscs_model = self.settings.resolve_cscs_model(model)
        url = f"{self.settings.cscs_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.cscs_api_key}",
            "Content-Type": "application/json",
            "User-Agent": "ApertusSovereignGate/1.0.0",
        }
        payload = {
            "model": cscs_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.settings.timeout_seconds) as client:
            resp = await client.post(url, headers=headers, json=payload)

        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        if resp.status_code == 200:
            data = resp.json()
            meta = {
                "backend": "cscs-sovereign-primary",
                "backend_url": url,
                "model_requested": model,
                "model_resolved": cscs_model,
                "status_code": resp.status_code,
                "backend_latency_ms": latency_ms,
                "failover_active": False,
            }
            return data, meta

        err_msg = f"CSCS HTTP {resp.status_code}: {resp.text[:300]}"
        raise RuntimeError(err_msg)

    async def _call_huggingface(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        failover_reason: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Call Hugging Face Inference API fallback."""
        hf_model = self.settings.resolve_hf_model(model)
        url = f"{self.settings.hf_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.hf_api_key}",
            "Content-Type": "application/json",
            "User-Agent": "ApertusSovereignGate/1.0.0",
        }
        payload = {
            "model": hf_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.settings.timeout_seconds) as client:
            resp = await client.post(url, headers=headers, json=payload)

        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        if resp.status_code == 200:
            data = resp.json()
            meta = {
                "backend": "huggingface-sovereign-fallback",
                "backend_url": url,
                "model_requested": model,
                "model_resolved": hf_model,
                "status_code": resp.status_code,
                "backend_latency_ms": latency_ms,
                "failover_active": True,
                "failover_reason": failover_reason,
            }
            return data, meta

        if resp.status_code in (400, 404) and hf_model != "swiss-ai/Apertus-8B-Instruct-2509":
            payload["model"] = "swiss-ai/Apertus-8B-Instruct-2509"
            async with httpx.AsyncClient(timeout=self.settings.timeout_seconds) as client:
                retry_resp = await client.post(url, headers=headers, json=payload)
            if retry_resp.status_code == 200:
                data = retry_resp.json()
                meta = {
                    "backend": "huggingface-sovereign-fallback",
                    "backend_url": url,
                    "model_requested": model,
                    "model_resolved": "swiss-ai/Apertus-8B-Instruct-2509",
                    "status_code": retry_resp.status_code,
                    "backend_latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                    "failover_active": True,
                    "failover_reason": failover_reason,
                }
                return data, meta

        err_msg = f"Hugging Face HTTP {resp.status_code}: {resp.text[:300]}"
        raise RuntimeError(f"Both CSCS and HF fallback failed. HF error: {err_msg}")
