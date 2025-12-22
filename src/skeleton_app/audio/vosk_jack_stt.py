"""
JACK-aware Vosk STT engine for real-time voice command recognition.

This module provides a low-latency speech-to-text service that integrates
with the JACK audio server. It exposes a mono input port for microphone input
and provides continuous, real-time transcription with wake word support.
"""

import asyncio
import json
import logging
import queue
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

import jack
import numpy as np
from vosk import Model, KaldiRecognizer

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    """Result from speech recognition."""
    text: str
    partial: bool = False
    confidence: float = 0.0
    timestamp: float = 0.0
    metadata: Dict = field(default_factory=dict)


@dataclass
class VoiceCommand:
    """A parsed voice command."""
    target_node: Optional[str] = None  # Which node this command is for
    command: str = ""  # The actual command text
    raw_text: str = ""  # Full transcription
    confidence: float = 0.0
    timestamp: float = 0.0


class VoskJackSTT:
    """
    JACK-aware Vosk STT engine for real-time voice commands.
    
    Features:
    - Low-latency audio capture via JACK
    - Continuous speech recognition
    - Wake word detection (node-specific)
    - Partial and final transcription results
    - Callback-based event system
    """
    
    def __init__(
        self,
        model_path: str,
        client_name: str = "vosk_stt",
        sample_rate: int = 16000,
        buffer_duration: float = 0.1,  # 100ms buffer
        wake_words: Optional[Dict[str, str]] = None  # node_id -> wake_word
    ):
        """
        Initialize Vosk JACK STT engine.
        
        Args:
            model_path: Path to Vosk model directory
            client_name: JACK client name
            sample_rate: Sample rate (Vosk typically uses 16kHz)
            buffer_duration: Audio buffer duration in seconds
            wake_words: Dictionary mapping node IDs to their wake words
        """
        self.model_path = Path(model_path)
        self.client_name = client_name
        self.sample_rate = sample_rate
        self.buffer_duration = buffer_duration
        self.wake_words = wake_words or {}
        
        # JACK components
        self.jack_client: Optional[jack.Client] = None
        self.input_port: Optional[jack.Port] = None
        
        # Vosk components
        self.model: Optional[Model] = None
        self.recognizer: Optional[KaldiRecognizer] = None
        
        # Audio processing
        self.audio_queue = queue.Queue()
        self.processing_thread: Optional[threading.Thread] = None
        self.running = False
        
        # State management
        self.listening_for_command = False
        self.current_target_node: Optional[str] = None
        self.command_timeout = 5.0  # seconds
        self._command_timer: Optional[asyncio.Task] = None
        
        # Callbacks
        self._on_partial_result: Optional[Callable[[TranscriptionResult], None]] = None
        self._on_final_result: Optional[Callable[[TranscriptionResult], None]] = None
        self._on_wake_word: Optional[Callable[[str], None]] = None
        self._on_command: Optional[Callable[[VoiceCommand], None]] = None
        
        # Stats
        self.stats = {
            'frames_processed': 0,
            'transcriptions': 0,
            'commands_detected': 0,
            'wake_words_detected': 0
        }
    
    def load_model(self):
        """Load Vosk model from disk."""
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Vosk model not found at {self.model_path}. "
                "Download a model from https://alphacephei.com/vosk/models"
            )
        
        logger.info(f"Loading Vosk model from {self.model_path}")
        self.model = Model(str(self.model_path))
        self.recognizer = KaldiRecognizer(self.model, self.sample_rate)
        
        # Enable partial results for real-time feedback
        self.recognizer.SetWords(True)
        
        logger.info("Vosk model loaded successfully")
    
    def connect_jack(self):
        """Connect to JACK server and create audio input port."""
        try:
            self.jack_client = jack.Client(self.client_name)
            
            # Create mono input port for microphone
            self.input_port = self.jack_client.inports.register('voice_in')
            
            # Set process callback for audio capture
            self.jack_client.set_process_callback(self._process_audio)
            
            # Activate client
            self.jack_client.activate()
            
            logger.info(f"Connected to JACK as '{self.client_name}'")
            logger.info(f"JACK sample rate: {self.jack_client.samplerate} Hz")
            logger.info(f"JACK buffer size: {self.jack_client.blocksize} frames")
            
            # Warn if sample rates don't match
            if self.jack_client.samplerate != self.sample_rate:
                logger.warning(
                    f"JACK sample rate ({self.jack_client.samplerate}) "
                    f"differs from Vosk sample rate ({self.sample_rate}). "
                    "Audio will be resampled, which may add latency."
                )
        
        except jack.JackError as e:
            logger.error(f"Failed to connect to JACK: {e}")
            raise RuntimeError(f"JACK connection failed: {e}") from e
    
    def _process_audio(self, frames: int) -> None:
        """
        JACK process callback - called in real-time audio thread.
        
        Args:
            frames: Number of frames to process
        """
        if self.input_port is None:
            return
        
        try:
            # Get audio from input port
            audio_data = self.input_port.get_array()
            
            # Convert float32 to int16 for Vosk
            audio_int16 = (audio_data * 32767).astype(np.int16)
            
            # Put in queue for processing thread
            self.audio_queue.put(audio_int16.tobytes())
            self.stats['frames_processed'] += frames
            
        except Exception as e:
            logger.error(f"Error in JACK process callback: {e}")
    
    def _audio_processing_loop(self):
        """Background thread for processing audio with Vosk."""
        logger.info("Audio processing thread started")
        
        while self.running:
            try:
                # Get audio data from queue (block with timeout)
                audio_bytes = self.audio_queue.get(timeout=0.1)
                
                # Process with Vosk
                if self.recognizer.AcceptWaveform(audio_bytes):
                    # Final result
                    result = json.loads(self.recognizer.Result())
                    self._handle_final_result(result)
                else:
                    # Partial result
                    result = json.loads(self.recognizer.PartialResult())
                    self._handle_partial_result(result)
                    
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in audio processing loop: {e}")
        
        logger.info("Audio processing thread stopped")
    
    def _handle_partial_result(self, result: Dict):
        """Handle partial transcription result."""
        if 'partial' not in result or not result['partial']:
            return
        
        text = result['partial'].strip()
        if not text:
            return
        
        import time
        transcription = TranscriptionResult(
            text=text,
            partial=True,
            timestamp=time.time()
        )
        
        # Call callback if registered
        if self._on_partial_result:
            self._on_partial_result(transcription)
        
        # Check for wake words in partial results for faster response
        if not self.listening_for_command:
            self._check_for_wake_word(text)
    
    def _handle_final_result(self, result: Dict):
        """Handle final transcription result."""
        if 'text' not in result or not result['text']:
            return
        
        text = result['text'].strip()
        if not text:
            return
        
        self.stats['transcriptions'] += 1
        
        # Extract confidence if available
        confidence = 1.0
        if 'result' in result and result['result']:
            # Average confidence from word results
            confidences = [word.get('conf', 1.0) for word in result['result']]
            confidence = sum(confidences) / len(confidences) if confidences else 1.0
        
        import time
        transcription = TranscriptionResult(
            text=text,
            partial=False,
            confidence=confidence,
            timestamp=time.time()
        )
        
        # Call callback if registered
        if self._on_final_result:
            self._on_final_result(transcription)
        
        # Process for commands
        if self.listening_for_command:
            self._process_command(text, confidence)
        else:
            self._check_for_wake_word(text)
    
    def _check_for_wake_word(self, text: str):
        """Check if text contains a wake word."""
        text_lower = text.lower()
        
        for node_id, wake_word in self.wake_words.items():
            if wake_word.lower() in text_lower:
                logger.info(f"Wake word detected for node: {node_id}")
                self.stats['wake_words_detected'] += 1
                
                # Start listening for command
                self.listening_for_command = True
                self.current_target_node = node_id
                
                # Call callback
                if self._on_wake_word:
                    self._on_wake_word(node_id)
                
                # Start timeout timer
                asyncio.create_task(self._command_timeout_timer())
                break
    
    async def _command_timeout_timer(self):
        """Timer to reset command listening after timeout."""
        await asyncio.sleep(self.command_timeout)
        
        if self.listening_for_command:
            logger.info("Command timeout - resetting to wake word listening")
            self.listening_for_command = False
            self.current_target_node = None
    
    def _process_command(self, text: str, confidence: float):
        """Process text as a voice command."""
        if not self.current_target_node:
            return
        
        logger.info(f"Command received for {self.current_target_node}: {text}")
        self.stats['commands_detected'] += 1
        
        import time
        command = VoiceCommand(
            target_node=self.current_target_node,
            command=text,
            raw_text=text,
            confidence=confidence,
            timestamp=time.time()
        )
        
        # Call callback
        if self._on_command:
            self._on_command(command)
        
        # Reset to wake word listening
        self.listening_for_command = False
        self.current_target_node = None
    
    # Public API
    
    def start(self):
        """Start the STT engine."""
        if self.running:
            logger.warning("STT engine already running")
            return
        
        # Load model
        if self.model is None:
            self.load_model()
        
        # Connect to JACK
        if self.jack_client is None:
            self.connect_jack()
        
        # Start processing thread
        self.running = True
        self.processing_thread = threading.Thread(
            target=self._audio_processing_loop,
            daemon=True
        )
        self.processing_thread.start()
        
        logger.info("Vosk JACK STT engine started")
    
    def stop(self):
        """Stop the STT engine."""
        if not self.running:
            return
        
        logger.info("Stopping Vosk JACK STT engine")
        self.running = False
        
        # Wait for processing thread
        if self.processing_thread:
            self.processing_thread.join(timeout=2.0)
        
        # Disconnect from JACK
        if self.jack_client:
            try:
                self.jack_client.deactivate()
                self.jack_client.close()
            except Exception as e:
                logger.warning(f"Error closing JACK client: {e}")
            finally:
                self.jack_client = None
        
        logger.info("Vosk JACK STT engine stopped")
    
    def is_running(self) -> bool:
        """Check if engine is running."""
        return self.running
    
    def add_wake_word(self, node_id: str, wake_word: str):
        """Add a wake word for a node."""
        self.wake_words[node_id] = wake_word
        logger.info(f"Added wake word '{wake_word}' for node {node_id}")
    
    def remove_wake_word(self, node_id: str):
        """Remove a wake word for a node."""
        if node_id in self.wake_words:
            del self.wake_words[node_id]
            logger.info(f"Removed wake word for node {node_id}")
    
    # Callbacks
    
    def on_partial_result(self, callback: Callable[[TranscriptionResult], None]):
        """Register callback for partial transcription results."""
        self._on_partial_result = callback
    
    def on_final_result(self, callback: Callable[[TranscriptionResult], None]):
        """Register callback for final transcription results."""
        self._on_final_result = callback
    
    def on_wake_word(self, callback: Callable[[str], None]):
        """Register callback for wake word detection."""
        self._on_wake_word = callback
    
    def on_command(self, callback: Callable[[VoiceCommand], None]):
        """Register callback for voice commands."""
        self._on_command = callback
    
    def get_stats(self) -> Dict:
        """Get engine statistics."""
        return self.stats.copy()
    
    # Context manager support
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
