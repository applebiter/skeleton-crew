"""STT provider with SSH-based remote execution."""

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import AsyncIterator, Optional

from skeleton_app.core.types import STTProvider, STTRequest, STTResult
from skeleton_app.remote import SSHExecutor

logger = logging.getLogger(__name__)


class RemoteWhisperProvider(STTProvider):
    """
    Whisper STT provider that executes on a remote node via SSH.
    
    This allows you to run Whisper on a powerful node (e.g., Windows with RTX 3060)
    while the voice capture happens on a lighter node (Linux with GTX 1050ti).
    """
    
    def __init__(
        self,
        remote_host: str,
        model: str = "medium",
        app_path: str = "/home/sysadmin/Programs/skeleton-app",
        user: str = "sysadmin"
    ):
        self.remote_host = remote_host
        self.model = model
        self.app_path = app_path
        self.executor = SSHExecutor(user=user)
    
    async def transcribe(self, request: STTRequest) -> STTResult:
        """
        Transcribe audio by executing Whisper on remote node.
        
        Process:
        1. Write audio to temp file locally
        2. SCP to remote node
        3. Execute Whisper via SSH
        4. Parse and return result
        5. Cleanup
        """
        # Create temp file for audio
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            local_path = f.name
            f.write(request.audio)
        
        try:
            # Remote temp path
            remote_path = f"/tmp/whisper_{Path(local_path).name}"
            
            # Copy audio to remote node
            logger.info(f"Copying audio to {self.remote_host}...")
            success = await self.executor.copy_file(
                self.remote_host,
                local_path,
                remote_path,
                direction="to"
            )
            
            if not success:
                raise Exception("Failed to copy audio file to remote node")
            
            # Execute Whisper remotely
            logger.info(f"Running Whisper on {self.remote_host}...")
            
            command = (
                f"cd {self.app_path} && "
                f"source .venv/bin/activate && "
                f"python -m whisper {remote_path} "
                f"--model {self.model} "
                f"--language {request.language} "
                f"--output_format json "
                f"--output_dir /tmp"
            )
            
            exit_code, stdout, stderr = await self.executor.execute(
                self.remote_host,
                command,
                timeout=300.0  # Whisper can take time
            )
            
            if exit_code != 0:
                logger.error(f"Whisper failed: {stderr}")
                raise Exception(f"Whisper execution failed: {stderr}")
            
            # Parse Whisper output
            # Whisper CLI outputs the transcript to stdout
            text = self._parse_whisper_output(stdout)
            
            # Cleanup remote file
            await self.executor.execute(
                self.remote_host,
                f"rm -f {remote_path} {remote_path}.json",
                timeout=5.0
            )
            
            return STTResult(
                text=text,
                confidence=1.0,  # Whisper doesn't provide confidence
                language=request.language,
                is_partial=False
            )
            
        finally:
            # Cleanup local temp file
            Path(local_path).unlink(missing_ok=True)
    
    async def transcribe_stream(self, request: STTRequest) -> AsyncIterator[STTResult]:
        """
        Whisper doesn't support streaming, so we just yield the final result.
        For true streaming, use Vosk locally or faster-whisper with streaming support.
        """
        result = await self.transcribe(request)
        yield result
    
    def _parse_whisper_output(self, output: str) -> str:
        """
        Parse Whisper CLI output to extract transcript.
        Whisper prints various info, we want the actual transcript.
        """
        lines = output.strip().split('\n')
        
        # Look for lines that look like transcript
        # Whisper typically outputs "[timestamp] transcript text"
        transcript_lines = []
        
        for line in lines:
            # Skip progress bars, model loading messages, etc.
            if '[' in line and ']' in line and '-->' not in line:
                continue
            if 'Detecting language' in line or 'model' in line.lower():
                continue
            
            # Extract actual transcript
            if line.strip() and not line.startswith('['):
                transcript_lines.append(line.strip())
        
        return ' '.join(transcript_lines).strip()


class RemoteVoskProvider(STTProvider):
    """
    Vosk STT provider that executes on a remote node via SSH.
    Less useful than RemoteWhisper since Vosk is light enough to run locally,
    but included for completeness.
    """
    
    def __init__(
        self,
        remote_host: str,
        model_path: str,
        app_path: str = "/home/sysadmin/Programs/skeleton-app",
        user: str = "sysadmin"
    ):
        self.remote_host = remote_host
        self.model_path = model_path
        self.app_path = app_path
        self.executor = SSHExecutor(user=user)
    
    async def transcribe(self, request: STTRequest) -> STTResult:
        """Transcribe using Vosk on remote node."""
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            local_path = f.name
            f.write(request.audio)
        
        try:
            remote_path = f"/tmp/vosk_{Path(local_path).name}"
            
            # Copy to remote
            await self.executor.copy_file(
                self.remote_host,
                local_path,
                remote_path,
                direction="to"
            )
            
            # Execute Vosk
            script = f"""
cd {self.app_path}
source .venv/bin/activate
python -c "
import json
from vosk import Model, KaldiRecognizer
import wave

model = Model('{self.model_path}')
wf = wave.open('{remote_path}', 'rb')
rec = KaldiRecognizer(model, wf.getframerate())

while True:
    data = wf.readframes(4000)
    if len(data) == 0:
        break
    rec.AcceptWaveform(data)

result = json.loads(rec.FinalResult())
print(result['text'])
"
"""
            
            exit_code, stdout, stderr = await self.executor.execute(
                self.remote_host,
                script,
                timeout=60.0
            )
            
            # Cleanup
            await self.executor.execute(
                self.remote_host,
                f"rm -f {remote_path}",
                timeout=5.0
            )
            
            if exit_code != 0:
                raise Exception(f"Vosk execution failed: {stderr}")
            
            return STTResult(
                text=stdout.strip(),
                confidence=1.0,
                language=request.language,
                is_partial=False
            )
            
        finally:
            Path(local_path).unlink(missing_ok=True)
    
    async def transcribe_stream(self, request: STTRequest) -> AsyncIterator[STTResult]:
        result = await self.transcribe(request)
        yield result


# Example: Hybrid approach - use SSH for specific tasks

class HybridSTTProvider(STTProvider):
    """
    Smart STT provider that routes to local or remote based on context.
    
    - Real-time commands: Use local Vosk
    - High-accuracy transcription: Use remote Whisper on Windows node
    - Batch processing: Queue jobs in database for remote processing
    """
    
    def __init__(
        self,
        local_provider: STTProvider,
        remote_provider: RemoteWhisperProvider
    ):
        self.local = local_provider
        self.remote = remote_provider
    
    async def transcribe(self, request: STTRequest) -> STTResult:
        """Route based on context."""
        
        if request.context == "command":
            # Use local for low latency
            logger.info("Using local STT for command")
            return await self.local.transcribe(request)
        
        elif request.context == "transcription":
            # Use remote for accuracy
            logger.info(f"Using remote STT on {self.remote.remote_host}")
            return await self.remote.transcribe(request)
        
        else:
            # Default to local
            return await self.local.transcribe(request)
    
    async def transcribe_stream(self, request: STTRequest) -> AsyncIterator[STTResult]:
        """Streaming only works with local provider."""
        async for result in self.local.transcribe_stream(request):
            yield result
