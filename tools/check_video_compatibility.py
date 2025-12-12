#!/usr/bin/env python3
"""
Check video compatibility and transcode problematic files using NVENC.
"""

import subprocess
import json
import sys
from pathlib import Path
from typing import Dict, Optional
import time


def probe_video(file_path: Path) -> Optional[Dict]:
    """
    Probe video file to get codec information.
    
    Returns:
        Dictionary with codec info, or None if probe fails
    """
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=codec_name,codec_long_name,pix_fmt,width,height,bit_rate',
            '-of', 'json',
            str(file_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            return None
        
        data = json.loads(result.stdout)
        if 'streams' in data and len(data['streams']) > 0:
            return data['streams'][0]
        
        return None
    
    except Exception as e:
        print(f"Error probing {file_path.name}: {e}")
        return None


def is_problematic(codec_info: Dict) -> bool:
    """
    Determine if video needs transcoding.
    
    OBS Studio hybrid mp4 issues often involve:
    - Fragmented mp4 (frag_keyframe)
    - Certain pixel formats
    - Non-standard codec flags
    """
    codec_name = codec_info.get('codec_name', '')
    codec_long = codec_info.get('codec_long_name', '')
    
    # Check for known problematic indicators
    problematic_indicators = [
        'frag' in codec_long.lower(),
        'hybrid' in codec_long.lower(),
    ]
    
    return any(problematic_indicators)


def test_playback(file_path: Path) -> bool:
    """
    Test if video can be decoded by trying to read first few frames.
    
    Returns:
        True if playback works, False if errors
    """
    try:
        cmd = [
            'ffmpeg',
            '-v', 'error',
            '-i', str(file_path),
            '-t', '1',  # Just 1 second
            '-f', 'null',
            '-'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        # If there's error output, it's problematic
        if result.stderr and 'error' in result.stderr.lower():
            return False
        
        return result.returncode == 0
    
    except Exception as e:
        print(f"Error testing playback: {e}")
        return False


def test_xjadeo_compatibility(file_path: Path) -> tuple[bool, str]:
    """
    Test if xjadeo can open the video file.
    
    Returns:
        (compatible, error_message)
    """
    try:
        # Try to get video info via xjadeo
        cmd = [
            'xjadeo',
            '--info',
            str(file_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            return True, ""
        else:
            # Extract error message
            error = result.stderr.strip() if result.stderr else "Unknown error"
            return False, error
    
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except FileNotFoundError:
        return None, "xjadeo not found"
    except Exception as e:
        return False, str(e)


def transcode_video(input_path: Path, output_path: Path, quality: int = 18) -> bool:
    """
    Transcode video using NVENC hardware acceleration.
    
    Args:
        input_path: Source video
        output_path: Destination video
        quality: CQ value (15-19 for visually lossless)
    
    Returns:
        True if successful, False otherwise
    """
    print(f"\nTranscoding: {input_path.name}")
    print(f"Output: {output_path}")
    
    cmd = [
        'ffmpeg',
        '-hwaccel', 'cuda',
        '-i', str(input_path),
        '-c:v', 'h264_nvenc',
        '-preset', 'p7',  # Highest quality
        '-tune', 'hq',
        '-rc', 'vbr',
        '-cq', str(quality),
        '-b:v', '0',
        '-c:a', 'copy',  # Copy audio without re-encoding
        '-movflags', '+faststart',  # Web optimization
        '-y',  # Overwrite output
        str(output_path)
    ]
    
    start_time = time.time()
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        elapsed = time.time() - start_time
        
        if result.returncode == 0:
            print(f"✓ Success! Time: {elapsed:.1f}s")
            
            # Show file sizes
            input_size = input_path.stat().st_size / (1024 * 1024)
            output_size = output_path.stat().st_size / (1024 * 1024)
            ratio = (output_size / input_size) * 100
            
            print(f"  Input:  {input_size:.1f} MB")
            print(f"  Output: {output_size:.1f} MB ({ratio:.1f}% of original)")
            
            return True
        else:
            print(f"✗ Failed: {result.stderr}")
            return False
    
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 check_video_compatibility.py <video_file_or_directory>")
        print("\nChecks video compatibility and transcodes problematic files.")
        sys.exit(1)
    
    path = Path(sys.argv[1]).expanduser()
    
    if not path.exists():
        print(f"Error: {path} does not exist")
        sys.exit(1)
    
    # Single file mode
    if path.is_file():
        print(f"Checking: {path.name}")
        print("=" * 60)
        
        # Probe video
        codec_info = probe_video(path)
        if not codec_info:
            print("✗ Could not probe video")
            sys.exit(1)
        
        print(f"Codec: {codec_info.get('codec_name', 'unknown')}")
        print(f"Format: {codec_info.get('codec_long_name', 'unknown')}")
        print(f"Pixel Format: {codec_info.get('pix_fmt', 'unknown')}")
        print(f"Resolution: {codec_info.get('width', '?')}x{codec_info.get('height', '?')}")
        
        # Test xjadeo compatibility
        print("\nTesting xjadeo compatibility...")
        xjadeo_ok, xjadeo_error = test_xjadeo_compatibility(path)
        
        if xjadeo_ok is None:
            print("⚠ xjadeo not found - install it to test compatibility")
            needs_transcode = False
        elif xjadeo_ok:
            print("✓ xjadeo can open this video")
            needs_transcode = False
        else:
            print(f"✗ xjadeo ERROR: {xjadeo_error}")
            print("  → Transcoding recommended for xjadeo compatibility")
            needs_transcode = True
        
        if needs_transcode:
            response = input("\nTranscode this video? [y/N]: ")
            if response.lower() == 'y':
                output_path = path.parent / f"{path.stem}_converted{path.suffix}"
                success = transcode_video(path, output_path)
                
                if success:
                    print(f"\n✓ Transcoded video saved to: {output_path}")
                    
                    # Ask if user wants to replace original
                    response = input("\nReplace original? [y/N]: ")
                    if response.lower() == 'y':
                        import shutil
                        backup = path.parent / f"{path.stem}_original{path.suffix}"
                        shutil.move(str(path), str(backup))
                        shutil.move(str(output_path), str(path))
                        print(f"✓ Original backed up to: {backup}")
                        print(f"✓ Converted video moved to: {path}")
    
    # Directory mode
    elif path.is_dir():
        print(f"Scanning directory: {path}")
        print("=" * 60)
        
        mp4_files = list(path.glob("*.mp4"))
        
        if not mp4_files:
            print("No .mp4 files found")
            sys.exit(0)
        
        print(f"Found {len(mp4_files)} video files\n")
        
        problematic = []
        
        for video in mp4_files:
            print(f"Checking: {video.name}... ", end='', flush=True)
            
            codec_info = probe_video(video)
            if not codec_info:
                print("⚠ Could not probe")
                continue
            
            # Test xjadeo compatibility
            xjadeo_ok, _ = test_xjadeo_compatibility(video)
            
            if xjadeo_ok is None:
                print("⚠ xjadeo not found")
            elif not xjadeo_ok:
                print("✗ xjadeo incompatible")
                problematic.append(video)
            else:
                print("✓ OK")
        
        if problematic:
            print(f"\n{len(problematic)} videos need transcoding:")
            for v in problematic:
                print(f"  - {v.name}")
            
            print("\nUse single-file mode to transcode each one.")
        else:
            print("\n✓ All videos are compatible!")


if __name__ == '__main__':
    main()
