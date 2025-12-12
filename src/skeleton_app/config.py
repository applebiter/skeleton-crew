"""Configuration management for skeleton-app."""

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class NodeConfig(BaseModel):
    """Node identity and capabilities configuration."""
    
    id: str
    name: str = "Skeleton Node"
    host: str = "0.0.0.0"
    port: int = 8000
    roles: List[str] = Field(default_factory=list)
    tags: Dict[str, Any] = Field(default_factory=dict)


class STTProviderConfig(BaseModel):
    """STT provider configuration."""
    
    backend: str
    model: str
    model_path: Optional[str] = None
    device: str = "cpu"
    compute_type: str = "float32"


class STTConfig(BaseModel):
    """Speech-to-text configuration."""
    
    providers: Dict[str, STTProviderConfig] = Field(default_factory=dict)
    vosk: Dict[str, Any] = Field(default_factory=dict)
    whisper: Dict[str, Any] = Field(default_factory=dict)


class PiperConfig(BaseModel):
    """Piper TTS configuration."""
    
    model: str = "en_US-lessac-medium"
    model_path: Optional[str] = None
    sample_rate: int = 22050


class TTSConfig(BaseModel):
    """Text-to-speech configuration."""
    
    backend: str = "piper"
    piper: PiperConfig = Field(default_factory=PiperConfig)


class LLMProviderConfig(BaseModel):
    """LLM provider configuration."""
    
    name: str
    type: str
    base_url: Optional[str] = None
    models: Dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    requires_key: bool = False


class LLMConfig(BaseModel):
    """LLM configuration."""
    
    providers: List[LLMProviderConfig] = Field(default_factory=list)
    defaults: Dict[str, str] = Field(default_factory=dict)
    max_context_length: int = 4096
    max_history_messages: int = 20


class JACKConfig(BaseModel):
    """JACK audio configuration."""
    
    client_name: str = "skeleton_app"
    auto_connect: bool = True
    ports: Dict[str, str] = Field(default_factory=dict)


class VADConfig(BaseModel):
    """Voice activity detection configuration."""
    
    threshold: float = 0.5
    min_silence_duration: float = 0.5
    min_speech_duration: float = 0.3


class AudioConfig(BaseModel):
    """Audio configuration."""
    
    jack: JACKConfig = Field(default_factory=JACKConfig)
    vad: VADConfig = Field(default_factory=VADConfig)


class WakewordConfig(BaseModel):
    """Wake-word detection configuration."""
    
    enabled: bool = True
    phrase: str = "computer"
    sensitivity: float = 0.5
    timeout: float = 5.0


class CommandDefinition(BaseModel):
    """Command definition."""
    
    name: str
    aliases: List[str] = Field(default_factory=list)
    handler: str


class CommandsConfig(BaseModel):
    """Commands configuration."""
    
    builtin: List[CommandDefinition] = Field(default_factory=list)


class DatabaseConfig(BaseModel):
    """Database configuration."""
    
    url: str
    pool_size: int = 5
    max_overflow: int = 10


class RemoteNodeConfig(BaseModel):
    """Remote node definition."""
    
    id: str
    host: str
    port: int = 8000
    roles: List[str] = Field(default_factory=list)
    tags: Dict[str, Any] = Field(default_factory=dict)


class RegistryConfig(BaseModel):
    """Node registry configuration."""
    
    backend: str = "postgres"
    nodes: List[RemoteNodeConfig] = Field(default_factory=list)


class RoutingConfig(BaseModel):
    """Capability routing configuration."""
    
    prefer_local: bool = True
    fallback_to_remote: bool = True
    overrides: Dict[str, Dict[str, str]] = Field(default_factory=dict)


class NetworkConfig(BaseModel):
    """Network/API configuration."""
    
    registry: RegistryConfig = Field(default_factory=RegistryConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)


class LoggingConfig(BaseModel):
    """Logging configuration."""
    
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file: Optional[str] = None


class Config(BaseModel):
    """Main application configuration."""
    
    node: NodeConfig
    stt: STTConfig = Field(default_factory=STTConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    wakeword: WakewordConfig = Field(default_factory=WakewordConfig)
    commands: CommandsConfig = Field(default_factory=CommandsConfig)
    database: DatabaseConfig
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    
    @classmethod
    def from_yaml(cls, path: Path) -> "Config":
        """Load configuration from YAML file."""
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        
        # Replace environment variables
        data = cls._replace_env_vars(data)
        
        return cls(**data)
    
    @staticmethod
    def _replace_env_vars(data: Any) -> Any:
        """Recursively replace ${VAR} patterns with environment variables."""
        import os
        import re
        
        if isinstance(data, dict):
            return {k: Config._replace_env_vars(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [Config._replace_env_vars(item) for item in data]
        elif isinstance(data, str):
            pattern = re.compile(r'\$\{([^}]+)\}')
            matches = pattern.findall(data)
            for var in matches:
                value = os.getenv(var, "")
                data = data.replace(f"${{{var}}}", value)
            return data
        else:
            return data


class EnvSettings(BaseSettings):
    """Environment-based settings."""
    
    # API Keys
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    hf_token: Optional[str] = None
    
    # Database
    database_url: str = "postgresql://skeleton:password@localhost:5432/skeleton_app"
    
    # Node
    node_id: Optional[str] = None
    node_host: str = "0.0.0.0"
    node_port: int = 8000
    
    # Ollama
    ollama_host: str = "http://localhost:11434"
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Allow extra fields in .env
