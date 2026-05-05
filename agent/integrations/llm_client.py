"""
LLM client for OpenRouter API with Langfuse observability.

Provides a unified interface for LLM calls with automatic cost tracking,
error handling, and fallback logic.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from dotenv import load_dotenv

from agent.integrations.langfuse_client import log_llm_call

load_dotenv()


def _get_openrouter_key() -> str:
    """Get OpenRouter API key from environment."""
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        raise ValueError("OPENROUTER_API_KEY not set in environment")
    return key


def _get_llm_model() -> str:
    """Get LLM model from environment, default to Qwen3."""
    return os.getenv("LLM_MODEL", "openai/gpt-4o-mini")


async def generate_text(
    prompt: str,
    model: str | None = None,
    max_tokens: int = 1000,
    temperature: float = 0.7,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """
    Generate text using OpenRouter API.
    
    Args:
        prompt: The prompt to send to the LLM
        model: Model identifier (defaults to LLM_MODEL env var)
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature (0.0-1.0)
        timeout: Request timeout in seconds
    
    Returns:
        {
            "text": str,  # Generated text
            "model": str,  # Model used
            "cost_usd": float,  # Estimated cost
            "tokens": int,  # Total tokens used
            "success": bool,  # Whether call succeeded
            "error": str | None,  # Error message if failed
        }
    """
    model = model or _get_llm_model()
    
    try:
        api_key = _get_openrouter_key()
    except ValueError as e:
        return {
            "text": "",
            "model": model,
            "cost_usd": 0.0,
            "tokens": 0,
            "success": False,
            "error": str(e),
        }
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://tenacious-training.dev",
        "X-Title": "Tenacious Agent",
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract response text
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # Extract usage stats
            usage = data.get("usage", {})
            total_tokens = usage.get("total_tokens", 0)
            
            # Estimate cost (rough approximation)
            # OpenRouter pricing varies by model, this is a conservative estimate
            cost_per_1k_tokens = 0.002  # $0.002 per 1K tokens (average)
            cost_usd = (total_tokens / 1000.0) * cost_per_1k_tokens
            
            # Log to Langfuse
            log_llm_call(
                prompt=prompt,
                response=text,
                model=model,
                cost_usd=cost_usd,
            )
            
            return {
                "text": text.strip(),
                "model": model,
                "cost_usd": cost_usd,
                "tokens": total_tokens,
                "success": True,
                "error": None,
            }
            
    except httpx.HTTPStatusError as exc:
        error_msg = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
        print(f"[LLM ERROR] {error_msg}")
        return {
            "text": "",
            "model": model,
            "cost_usd": 0.0,
            "tokens": 0,
            "success": False,
            "error": error_msg,
        }
    
    except httpx.TimeoutException:
        error_msg = f"Timeout after {timeout}s"
        print(f"[LLM ERROR] {error_msg}")
        return {
            "text": "",
            "model": model,
            "cost_usd": 0.0,
            "tokens": 0,
            "success": False,
            "error": error_msg,
        }
    
    except Exception as exc:
        error_msg = f"Unexpected error: {str(exc)}"
        print(f"[LLM ERROR] {error_msg}")
        return {
            "text": "",
            "model": model,
            "cost_usd": 0.0,
            "tokens": 0,
            "success": False,
            "error": error_msg,
        }


async def generate_json(
    prompt: str,
    model: str | None = None,
    max_tokens: int = 1500,
    temperature: float = 0.5,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """
    Generate JSON using OpenRouter API.
    
    Same as generate_text but attempts to parse response as JSON.
    
    Returns:
        {
            "data": dict | list | None,  # Parsed JSON data
            "text": str,  # Raw text response
            "model": str,
            "cost_usd": float,
            "tokens": int,
            "success": bool,
            "error": str | None,
        }
    """
    result = await generate_text(
        prompt=prompt,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
    )
    
    if not result["success"]:
        return {
            **result,
            "data": None,
        }
    
    # Try to parse JSON
    text = result["text"]
    try:
        # Handle markdown code blocks
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        
        data = json.loads(text)
        return {
            **result,
            "data": data,
        }
    except json.JSONDecodeError as e:
        return {
            **result,
            "data": None,
            "success": False,
            "error": f"JSON parse error: {str(e)}",
        }
