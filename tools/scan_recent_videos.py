#!/usr/bin/env python3
"""
Scan for recently modified videos and check compatibility.
Only checks - does not transcode without explicit permission.
"""

import subprocess
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, List


def probe_video(file_path: Path) -> Optional[Dict]:
    """Probe video file to get codec information."""
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=codec_name,codec_long_name,pix_fmt,width,height',
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
        return None


def test_playback(file_path: Path) -> bool:
    """Test if video can be decoded properly."""
    try:
        cmd = [
            'ffmpeg',
            '-v', 'error',
            '-i', str(file_path),
            '-t', '1',
            '-f', 'null',
            '-'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.stderr and 'error' in result.stderr.lower():
            return False
        
        return result.returncode == 0
    
    except Exception:
        return False


def find_recent_videos(base_dir: Path, days: int = 180) -> List[Path]:
    """Find mp4 files modified in the last N days."""
    cutoff = datetime.now() - timedelta(days=days)
    recent = []
    
    print(f"Searching for .mp4 files modified since {cutoff.strftime('%Y-%m-%d')}...")
    
    for mp4 in base_dir.rglob("*.mp4"):
        try:
            mtime = datetime.fromtimestamp(mp4.stat().st_mtime)
            if mtime > cutoff:
                recent.append((mp4, mtime))
        except Exception:
            continue
    
    # Sort by modification time, newest first
    recent.sort(key=lambda x: x[1], reverse=True)
    
    return [path for path, _ in recent]


def main():
    base_dir = Path("/home/sysadmin/Backups/Videos/Feature Films")
    
    print("=" * 70)
    print("Video Compatibility Scanner - Recent Files Only")
    print("=" * 70)
    
    # Find recent videos (last 6 months)
    recent_videos = find_recent_videos(base_dir, days=180)
    
    if not recent_videos:
        print("\nNo recently modified .mp4 files found.")
        return
    
    print(f"\nFound {len(recent_videos)} recent video(s):")
    for i, video in enumerate(recent_videos[:10], 1):  # Show first 10
        size_mb = video.stat().st_size / (1024 * 1024)
        mtime = datetime.fromtimestamp(video.stat().st_mtime)
        print(f"  {i}. {video.name} ({size_mb:.1f} MB) - {mtime.strftime('%Y-%m-%d')}")
    
    if len(recent_videos) > 10:
        print(f"  ... and {len(recent_videos) - 10} more")
    
    print("\n" + "=" * 70)
    print("Checking compatibility...")
    print("=" * 70 + "\n")
    
    problematic = []
    
    for video in recent_videos:
        rel_path = video.relative_to(base_dir)
        print(f"Checking: {rel_path}")
        
        codec_info = probe_video(video)
        if not codec_info:
            print("  ⚠ Could not probe\n")
            continue
        
        print(f"  Codec: {codec_info.get('codec_name', 'unknown')}")
        print(f"  Format: {codec_info.get('codec_long_name', 'unknown')}")
        
        if not test_playback(video):
            print("  ✗ PLAYBACK ISSUES DETECTED")
            problematic.append(video)
        else:
            print("  ✓ OK")
        
        print()
    
    print("=" * 70)
    
    if problematic:
        print(f"\n⚠ {len(problematic)} video(s) need transcoding:\n")
        for video in problematic:
            size_mb = video.stat().st_size / (1024 * 1024)
            print(f"  - {video.name} ({size_mb:.1f} MB)")
        
        print("\nTo transcode a specific file, run:")
        print("  python tools/check_video_compatibility.py <video_path>")
    else:
        print("\n✓ All recent videos are compatible!")


if __name__ == '__main__':
    main()
