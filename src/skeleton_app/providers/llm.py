"""LLM provider implementations."""

import logging
from typing import AsyncIterator, List, Optional

import httpx

from skeleton_app.core.types import LLMMessage, LLMProvider, LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Ollama LLM provider."""
    
    def __init__(self, base_url: str = "http://localhost:11434", default_model: str = "granite4:3b"):
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.client = httpx.AsyncClient(timeout=300.0)
    
    async def chat(self, request: LLMRequest) -> LLMResponse:
        """Generate chat completion."""
        model = request.model or self.default_model
        
        # Convert messages to Ollama format
        messages = [
            {"role": msg.role, "content": msg.content}
            for msg in request.messages
        ]
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": request.temperature,
            }
        }
        
        if request.max_tokens:
            payload["options"]["num_predict"] = request.max_tokens
        
        # Add tools if provided (for granite3, minicpm-v, etc.)
        if request.tools:
            payload["tools"] = request.tools
        
        try:
            response = await self.client.post(
                f"{self.base_url}/api/chat",
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            
            message = data["message"]
            
            return LLMResponse(
                content=message.get("content", ""),
                role=message["role"],
                tool_calls=message.get("tool_calls"),  # Support for granite4/ministral-3
                finish_reason=data.get("done_reason"),
                usage={
                    "prompt_tokens": data.get("prompt_eval_count", 0),
                    "completion_tokens": data.get("eval_count", 0),
                    "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
                }
            )
        except Exception as e:
            logger.error(f"Ollama chat error: {e}")
            raise
    
    async def chat_stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Generate streaming chat completion."""
        model = request.model or self.default_model
        
        messages = [
            {"role": msg.role, "content": msg.content}
            for msg in request.messages
        ]
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": request.temperature,
            }
        }
        
        if request.max_tokens:
            payload["options"]["num_predict"] = request.max_tokens
        
        try:
            async with self.client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.strip():
                        import json
                        data = json.loads(line)
                        if "message" in data and "content" in data["message"]:
                            yield data["message"]["content"]
        except Exception as e:
            logger.error(f"Ollama streaming error: {e}")
            raise
    
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for texts."""
        embeddings = []
        
        # Ollama's embedding endpoint processes one text at a time
        for text in texts:
            try:
                response = await self.client.post(
                    f"{self.base_url}/api/embeddings",
                    json={
                        "model": "nomic-embed-text",  # Default embedding model
                        "prompt": text
                    }
                )
                response.raise_for_status()
                data = response.json()
                embeddings.append(data["embedding"])
            except Exception as e:
                logger.error(f"Ollama embedding error: {e}")
                raise
        
        return embeddings
    
    async def list_models(self) -> List[str]:
        """List available models."""
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
            return [model["name"] for model in data.get("models", [])]
        except Exception as e:
            logger.error(f"Error listing Ollama models: {e}")
            return []
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider."""
    
    def __init__(self, api_key: str, default_model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.default_model = default_model
        self.base_url = "https://api.openai.com/v1"
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=300.0
        )
    
    async def chat(self, request: LLMRequest) -> LLMResponse:
        """Generate chat completion."""
        model = request.model or self.default_model
        
        messages = [
            {"role": msg.role, "content": msg.content}
            for msg in request.messages
        ]
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
        }
        
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens
        
        if request.tools:
            payload["tools"] = request.tools
        
        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            
            choice = data["choices"][0]
            message = choice["message"]
            
            return LLMResponse(
                content=message.get("content", ""),
                role=message["role"],
                tool_calls=message.get("tool_calls"),
                finish_reason=choice.get("finish_reason"),
                usage=data.get("usage")
            )
        except Exception as e:
            logger.error(f"OpenAI chat error: {e}")
            raise
    
    async def chat_stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Generate streaming chat completion."""
        model = request.model or self.default_model
        
        messages = [
            {"role": msg.role, "content": msg.content}
            for msg in request.messages
        ]
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
            "stream": True,
        }
        
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens
        
        try:
            async with self.client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        
                        import json
                        try:
                            data = json.loads(data_str)
                            if "choices" in data and len(data["choices"]) > 0:
                                delta = data["choices"][0].get("delta", {})
                                if "content" in delta:
                                    yield delta["content"]
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error(f"OpenAI streaming error: {e}")
            raise
    
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for texts."""
        try:
            response = await self.client.post(
                f"{self.base_url}/embeddings",
                json={
                    "model": "text-embedding-3-small",
                    "input": texts
                }
            )
            response.raise_for_status()
            data = response.json()
            return [item["embedding"] for item in data["data"]]
        except Exception as e:
            logger.error(f"OpenAI embedding error: {e}")
            raise
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


class AnthropicProvider(LLMProvider):
    """Anthropic LLM provider."""
    
    def __init__(self, api_key: str, default_model: str = "claude-3-5-sonnet-20241022"):
        self.api_key = api_key
        self.default_model = default_model
        self.base_url = "https://api.anthropic.com/v1"
        self.client = httpx.AsyncClient(
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            },
            timeout=300.0
        )
    
    async def chat(self, request: LLMRequest) -> LLMResponse:
        """Generate chat completion."""
        model = request.model or self.default_model
        
        # Convert messages to Anthropic format
        # Anthropic requires system message separately
        system_message = None
        messages = []
        
        for msg in request.messages:
            if msg.role == "system":
                system_message = msg.content
            else:
                messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
        
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": request.max_tokens or 4096,
            "temperature": request.temperature,
        }
        
        if system_message:
            payload["system"] = system_message
        
        try:
            response = await self.client.post(
                f"{self.base_url}/messages",
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            
            content = data["content"][0]["text"] if data["content"] else ""
            
            return LLMResponse(
                content=content,
                role="assistant",
                finish_reason=data.get("stop_reason"),
                usage=data.get("usage")
            )
        except Exception as e:
            logger.error(f"Anthropic chat error: {e}")
            raise
    
    async def chat_stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Generate streaming chat completion."""
        model = request.model or self.default_model
        
        system_message = None
        messages = []
        
        for msg in request.messages:
            if msg.role == "system":
                system_message = msg.content
            else:
                messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
        
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": request.max_tokens or 4096,
            "temperature": request.temperature,
            "stream": True,
        }
        
        if system_message:
            payload["system"] = system_message
        
        try:
            async with self.client.stream(
                "POST",
                f"{self.base_url}/messages",
                json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        
                        import json
                        try:
                            data = json.loads(data_str)
                            if data.get("type") == "content_block_delta":
                                delta = data.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    yield delta.get("text", "")
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error(f"Anthropic streaming error: {e}")
            raise
    
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for texts."""
        # Anthropic doesn't provide embeddings, raise not implemented
        raise NotImplementedError("Anthropic does not provide embedding models")
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
