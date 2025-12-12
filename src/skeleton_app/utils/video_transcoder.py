"""
Video transcoding utility for frame-accurate playback.

Transcodes videos to MJPEG with separate audio files for optimal
frame-precise scrubbing with xjadeo and Qt video players.
"""

import logging
import subprocess
import json
from pathlib import Path
from typing import Optional, Dict, Tuple, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class AudioFormat(Enum):
    """Preferred audio formats."""
    FLAC = "flac"
    OGG = "ogg"  # Vorbis
    OPUS = "opus"
    WAV = "wav"
    MP3 = "mp3"
    AAC = "aac"  # Keep if already AAC


@dataclass
class TranscodeJob:
    """Transcode job configuration."""
    source_path: Path
    output_dir: Path
    video_codec: str = "h264_nvenc"  # Use NVIDIA hardware encoder
    video_quality: int = 23  # CRF for h264_nvenc (lower = better)
    use_hw_accel: bool = True  # Use GPU acceleration
    audio_format: Optional[AudioFormat] = None  # None = keep original
    audio_bitrate: str = "320k"  # For lossy formats
    
    @property
    def output_video_path(self) -> Path:
        """Get output video file path."""
        ext = "mp4" if "nvenc" in self.video_codec else "avi"
        return self.output_dir / f"{self.source_path.stem}_video.{ext}"
    
    @property
    def output_audio_path(self) -> Path:
        """Get output audio file path."""
        ext = self.audio_format.value if self.audio_format else "audio"
        return self.output_dir / f"{self.source_path.stem}_audio.{ext}"


@dataclass
class MediaInfo:
    """Information about media file."""
    duration: float  # seconds
    video_codec: str
    video_bitrate: int
    audio_codec: str
    audio_bitrate: int
    audio_sample_rate: int
    audio_channels: int
    width: int
    height: int
    fps: float


class VideoTranscoder:
    """
    Transcode videos to frame-accurate format with separate audio.
    
    Uses NVIDIA NVENC hardware acceleration for fast encoding.
    
    Features:
    - H.264 all-intraframe (every frame is keyframe - perfect for scrubbing)
    - NVIDIA GTX 1050 Ti hardware encoding (much faster than CPU)
    - Hardware-accelerated decoding (NVDEC/CUVID)
    - Separate audio file (flac/ogg/opus/wav/mp3)
    - Preserve aspect ratio and framerate
    - Progress callbacks
    """
    
    def __init__(self, use_hw_accel: bool = True):
        self.current_job: Optional[TranscodeJob] = None
        self.is_running = False
        self.use_hw_accel = use_hw_accel
        self._check_nvenc_support()
    
    def _check_nvenc_support(self) -> bool:
        """Check if NVENC is available."""
        if not self.use_hw_accel:
            return False
        
        try:
            result = subprocess.run(
                ['ffmpeg', '-hide_banner', '-encoders'],
                capture_output=True,
                text=True,
                check=True
            )
            
            has_nvenc = 'h264_nvenc' in result.stdout
            if has_nvenc:
                logger.info("NVIDIA NVENC hardware encoder detected")
            else:
                logger.warning("NVENC not available, falling back to CPU encoding")
                self.use_hw_accel = False
            
            return has_nvenc
        
        except Exception as e:
            logger.warning(f"Failed to check NVENC support: {e}")
            self.use_hw_accel = False
            return False
    
    def probe_media(self, file_path: Path) -> MediaInfo:
        """Get media file information using ffprobe."""
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                str(file_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            
            # Extract video stream info
            video_stream = next(
                (s for s in data['streams'] if s['codec_type'] == 'video'),
                None
            )
            
            # Extract audio stream info
            audio_stream = next(
                (s for s in data['streams'] if s['codec_type'] == 'audio'),
                None
            )
            
            if not video_stream:
                raise ValueError("No video stream found")
            
            duration = float(data['format'].get('duration', 0))
            
            return MediaInfo(
                duration=duration,
                video_codec=video_stream.get('codec_name', 'unknown'),
                video_bitrate=int(video_stream.get('bit_rate', 0)),
                audio_codec=audio_stream.get('codec_name', 'unknown') if audio_stream else 'none',
                audio_bitrate=int(audio_stream.get('bit_rate', 0)) if audio_stream else 0,
                audio_sample_rate=int(audio_stream.get('sample_rate', 48000)) if audio_stream else 0,
                audio_channels=audio_stream.get('channels', 2) if audio_stream else 0,
                width=video_stream.get('width', 0),
                height=video_stream.get('height', 0),
                fps=eval(video_stream.get('r_frame_rate', '30/1'))  # "30000/1001" -> 29.97
            )
        
        except subprocess.CalledProcessError as e:
            logger.error(f"ffprobe failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to probe media: {e}")
            raise
    
    def get_preferred_audio_format(self, current_codec: str) -> Optional[AudioFormat]:
        """
        Determine preferred audio format based on current codec.
        
        Keep lossless as lossless, keep preferred formats as-is,
        convert others to ogg vorbis.
        """
        # Map codec names to our formats
        codec_map = {
            'flac': AudioFormat.FLAC,
            'vorbis': AudioFormat.OGG,
            'opus': AudioFormat.OPUS,
            'pcm_s16le': AudioFormat.WAV,
            'pcm_s24le': AudioFormat.WAV,
            'mp3': AudioFormat.MP3,
            'aac': AudioFormat.AAC,
        }
        
        # If already preferred format, keep it
        if current_codec in codec_map:
            return None  # Keep original
        
        # Convert to ogg vorbis as default
        return AudioFormat.OGG
    
    def transcode_video(
        self,
        source_path: Path,
        output_dir: Path,
        video_quality: int = 23,
        audio_format: Optional[AudioFormat] = None,
        progress_callback=None
    ) -> Tuple[Path, Path]:
        """
        Transcode video to frame-accurate H.264 + separate audio.
        
        Uses NVIDIA NVENC for hardware-accelerated encoding.
        
        Args:
            source_path: Source video file
            output_dir: Output directory
            video_quality: CRF quality 0-51 (lower = better, 23 = high quality)
            audio_format: Target audio format (None = keep original)
            progress_callback: Callable(percent: float, message: str)
        
        Returns:
            Tuple of (video_path, audio_path)
        """
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")
        
        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Probe source file
        logger.info(f"Probing {source_path}")
        media_info = self.probe_media(source_path)
        logger.info(f"Source: {media_info.video_codec} {media_info.width}x{media_info.height} @ {media_info.fps}fps, "
                   f"audio: {media_info.audio_codec}")
        
        # Determine audio format
        if audio_format is None:
            audio_format = self.get_preferred_audio_format(media_info.audio_codec)
        
        # Create job
        codec = "h264_nvenc" if self.use_hw_accel else "libx264"
        job = TranscodeJob(
            source_path=source_path,
            output_dir=output_dir,
            video_codec=codec,
            video_quality=video_quality,
            use_hw_accel=self.use_hw_accel,
            audio_format=audio_format
        )
        
        self.current_job = job
        self.is_running = True
        
        try:
            # Transcode video with NVENC
            codec_name = "NVENC (GPU)" if job.use_hw_accel else "x264 (CPU)"
            logger.info(f"Transcoding video with {codec_name} (quality {video_quality})")
            if progress_callback:
                progress_callback(0, f"Transcoding video with {codec_name}...")
            
            self._transcode_video_stream(job, media_info, progress_callback)
            
            # Extract/transcode audio
            logger.info(f"Extracting audio")
            if progress_callback:
                progress_callback(50, "Extracting audio...")
            
            self._transcode_audio_stream(job, media_info, progress_callback)
            
            if progress_callback:
                progress_callback(100, "Complete!")
            
            logger.info(f"Transcode complete:")
            logger.info(f"  Video: {job.output_video_path}")
            logger.info(f"  Audio: {job.output_audio_path}")
            
            return job.output_video_path, job.output_audio_path
        
        finally:
            self.is_running = False
            self.current_job = None
    
    def _transcode_video_stream(
        self,
        job: TranscodeJob,
        media_info: MediaInfo,
        progress_callback=None
    ):
        """Transcode video stream with NVIDIA NVENC hardware acceleration."""
        cmd = ['ffmpeg']
        
        # Hardware-accelerated decoding
        if job.use_hw_accel:
            cmd.extend([
                '-hwaccel', 'cuda',
                '-hwaccel_output_format', 'cuda',
            ])
        
        cmd.extend(['-i', str(job.source_path)])
        
        # Video encoding
        if job.use_hw_accel:
            # NVIDIA NVENC encoding
            cmd.extend([
                '-c:v', 'h264_nvenc',
                '-preset', 'p7',  # p7 = highest quality preset
                '-tune', 'hq',  # High quality tuning
                '-rc', 'vbr',  # Variable bitrate
                '-cq', str(job.video_quality),  # Quality level (0-51)
                '-b:v', '0',  # Let CQ control bitrate
                '-g', '1',  # GOP size 1 = all intraframe (every frame is keyframe)
                '-bf', '0',  # No B-frames
            ])
        else:
            # CPU fallback (libx264)
            cmd.extend([
                '-c:v', 'libx264',
                '-preset', 'slow',
                '-crf', str(job.video_quality),
                '-g', '1',  # All intraframe
                '-bf', '0',
            ])
        
        cmd.extend([
            '-an',  # No audio
            '-y',  # Overwrite
            str(job.output_video_path)
        ])
        
        logger.debug(f"Running: {' '.join(cmd)}")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        # Parse progress from stderr
        for line in process.stderr:
            if progress_callback and 'time=' in line:
                # Extract time from ffmpeg output
                # Example: "frame= 1234 fps=56 q=8.0 size=  123456kB time=00:01:23.45 bitrate=1234.5kbits/s"
                try:
                    time_str = line.split('time=')[1].split()[0]
                    h, m, s = time_str.split(':')
                    current_time = int(h) * 3600 + int(m) * 60 + float(s)
                    percent = min(45, (current_time / media_info.duration) * 45)
                    progress_callback(percent, f"Transcoding video: {percent:.0f}%")
                except:
                    pass
        
        returncode = process.wait()
        if returncode != 0:
            raise RuntimeError(f"ffmpeg failed with code {returncode}")
    
    def _transcode_audio_stream(
        self,
        job: TranscodeJob,
        media_info: MediaInfo,
        progress_callback=None
    ):
        """Extract/transcode audio stream."""
        if media_info.audio_codec == 'none':
            logger.warning("No audio stream found")
            return
        
        # Build ffmpeg command based on target format
        cmd = ['ffmpeg', '-i', str(job.source_path)]
        
        if job.audio_format is None:
            # Keep original - just copy
            cmd.extend(['-vn', '-c:a', 'copy'])
        else:
            # Transcode to target format
            cmd.extend(['-vn'])  # No video
            
            if job.audio_format == AudioFormat.FLAC:
                cmd.extend(['-c:a', 'flac'])
            elif job.audio_format == AudioFormat.OGG:
                cmd.extend(['-c:a', 'libvorbis', '-q:a', '6'])  # Quality 6 (high)
            elif job.audio_format == AudioFormat.OPUS:
                cmd.extend(['-c:a', 'libopus', '-b:a', '192k'])
            elif job.audio_format == AudioFormat.WAV:
                cmd.extend(['-c:a', 'pcm_s16le'])
            elif job.audio_format == AudioFormat.MP3:
                cmd.extend(['-c:a', 'libmp3lame', '-b:a', job.audio_bitrate])
            elif job.audio_format == AudioFormat.AAC:
                cmd.extend(['-c:a', 'aac', '-b:a', job.audio_bitrate])
        
        cmd.extend(['-y', str(job.output_audio_path)])
        
        logger.debug(f"Running: {' '.join(cmd)}")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        # Parse progress
        for line in process.stderr:
            if progress_callback and 'time=' in line:
                try:
                    time_str = line.split('time=')[1].split()[0]
                    h, m, s = time_str.split(':')
                    current_time = int(h) * 3600 + int(m) * 60 + float(s)
                    percent = 50 + min(50, (current_time / media_info.duration) * 50)
                    progress_callback(percent, f"Extracting audio: {percent-50:.0f}%")
                except:
                    pass
        
        returncode = process.wait()
        if returncode != 0:
            raise RuntimeError(f"ffmpeg audio extraction failed with code {returncode}")
    
    def batch_transcode(
        self,
        source_files: List[Path],
        output_base_dir: Path,
        video_quality: int = 8,
        progress_callback=None
    ) -> List[Tuple[Path, Path]]:
        """
        Batch transcode multiple files.
        
        Each file gets its own subdirectory in output_base_dir.
        """
        results = []
        total = len(source_files)
        
        for i, source_file in enumerate(source_files):
            logger.info(f"Processing {i+1}/{total}: {source_file.name}")
            
            # Create subdirectory for this file
            subdir = output_base_dir / source_file.stem
            
            try:
                video_path, audio_path = self.transcode_video(
                    source_path=source_file,
                    output_dir=subdir,
                    video_quality=video_quality,
                    progress_callback=lambda p, m: progress_callback(
                        ((i + p/100) / total) * 100,
                        f"[{i+1}/{total}] {source_file.name}: {m}"
                    ) if progress_callback else None
                )
                results.append((video_path, audio_path))
            
            except Exception as e:
                logger.error(f"Failed to transcode {source_file}: {e}")
                if progress_callback:
                    progress_callback(
                        ((i + 1) / total) * 100,
                        f"[{i+1}/{total}] Failed: {source_file.name}"
                    )
        
        return results


def cli_transcode(source_path: str, output_dir: str):
    """CLI interface for transcoding."""
    transcoder = VideoTranscoder()
    
    def progress(percent, message):
        print(f"\r[{percent:5.1f}%] {message}", end='', flush=True)
    
    try:
        video_path, audio_path = transcoder.transcode_video(
            Path(source_path),
            Path(output_dir),
            progress_callback=progress
        )
        print(f"\n\nSuccess!")
        print(f"Video: {video_path}")
        print(f"Audio: {audio_path}")
    
    except Exception as e:
        print(f"\n\nError: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: video_transcoder.py <source_file> <output_dir>")
        sys.exit(1)
    
    sys.exit(cli_transcode(sys.argv[1], sys.argv[2]))
