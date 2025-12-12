"""Core types and abstractions."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional


class STTContext(str, Enum):
    """Speech-to-text usage context."""
    
    COMMAND = "command"
    CONVERSATION = "conversation"
    TRANSCRIPTION = "transcription"


class Priority(str, Enum):
    """Task priority level."""
    
    SPEED = "speed"
    BALANCED = "balanced"
    ACCURACY = "accuracy"


@dataclass
class STTRequest:
    """Speech-to-text request."""
    
    audio: bytes
    context: STTContext = STTContext.COMMAND
    priority: Priority = Priority.BALANCED
    language: str = "en"
    sample_rate: int = 16000


@dataclass
class STTResult:
    """Speech-to-text result."""
    
    text: str
    confidence: float = 1.0
    language: Optional[str] = None
    is_partial: bool = False
    metadata: Dict[str, Any] = None


@dataclass
class TTSRequest:
    """Text-to-speech request."""
    
    text: str
    voice: Optional[str] = None
    language: str = "en"
    speed: float = 1.0
    metadata: Dict[str, Any] = None


@dataclass
class TTSResult:
    """Text-to-speech result."""
    
    audio: bytes
    sample_rate: int
    format: str = "pcm"
    metadata: Dict[str, Any] = None


@dataclass
class LLMMessage:
    """LLM chat message."""
    
    role: str  # "user", "assistant", "system", "tool"
    content: str
    name: Optional[str] = None
    metadata: Dict[str, Any] = None


@dataclass
class LLMRequest:
    """LLM request."""
    
    messages: List[LLMMessage]
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    tools: Optional[List[Dict[str, Any]]] = None
    metadata: Dict[str, Any] = None


@dataclass
class LLMResponse:
    """LLM response."""
    
    content: str
    role: str = "assistant"
    tool_calls: Optional[List[Dict[str, Any]]] = None
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    metadata: Dict[str, Any] = None


class STTProvider(ABC):
    """Abstract speech-to-text provider."""
    
    @abstractmethod
    async def transcribe(self, request: STTRequest) -> STTResult:
        """Transcribe audio to text."""
        pass
    
    @abstractmethod
    async def transcribe_stream(self, request: STTRequest) -> AsyncIterator[STTResult]:
        """Transcribe audio stream to text with partial results."""
        pass


class TTSProvider(ABC):
    """Abstract text-to-speech provider."""
    
    @abstractmethod
    async def synthesize(self, request: TTSRequest) -> TTSResult:
        """Synthesize text to audio."""
        pass
    
    @abstractmethod
    async def synthesize_stream(self, request: TTSRequest) -> AsyncIterator[bytes]:
        """Synthesize text to audio stream."""
        pass


class LLMProvider(ABC):
    """Abstract LLM provider."""
    
    @abstractmethod
    async def chat(self, request: LLMRequest) -> LLMResponse:
        """Generate chat completion."""
        pass
    
    @abstractmethod
    async def chat_stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Generate streaming chat completion."""
        pass
    
    @abstractmethod
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for texts."""
        pass


@dataclass
class NodeCapability:
    """Node capability descriptor."""
    
    type: str  # "stt", "tts", "llm", etc.
    subtype: Optional[str] = None  # "realtime", "batch", "chat", "embedding"
    models: List[str] = None
    tags: Dict[str, Any] = None
    cost: float = 1.0  # Relative cost metric
    latency: float = 1.0  # Relative latency metric


@dataclass
class NodeInfo:
    """Node information."""
    
    id: str
    name: str
    host: str
    port: int
    roles: List[str]
    capabilities: List[NodeCapability]
    tags: Dict[str, Any]
    status: str = "online"  # "online", "offline", "degraded"
    last_seen: Optional[float] = None


@dataclass
class CapabilityRequest:
    """Request for a capability."""
    
    type: str
    subtype: Optional[str] = None
    model: Optional[str] = None
    prefer_local: bool = True
    required_tags: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = None


@dataclass
class CapabilityRoute:
    """Resolved capability route."""
    
    node_id: str
    is_local: bool
    endpoint: Optional[str] = None
    capability: NodeCapability = None
