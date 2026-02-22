#!/usr/bin/env python3
"""
Generate test media files for the new media processing features.

Creates:
- Test images (with text for OCR, with EXIF metadata, with scene content)
- Test audio files (with speech-like content)
- Test video files (with frames and audio track)

All files are self-contained — no external downloads required.
"""

import subprocess
import struct
import wave
import math
import os
import sys
from pathlib import Path

# Ensure Pillow is available
try:
    from PIL import Image, ImageDraw, ImageFont
    from PIL.ExifTags import Base as ExifBase
    import piexif
    PIEXIF_AVAILABLE = True
except ImportError:
    from PIL import Image, ImageDraw, ImageFont
    PIEXIF_AVAILABLE = False

OUTPUT_DIR = Path(__file__).parent / "test_media"
OUTPUT_DIR.mkdir(exist_ok=True)


def create_ocr_test_image():
    """Create an image with clear text for Tesseract OCR testing."""
    print("Creating OCR test image...")

    img = Image.new("RGB", (800, 600), color="white")
    draw = ImageDraw.Draw(img)

    # Use a basic font - try system fonts first, fall back to default
    font_size = 20
    small_font_size = 14
    try:
        # macOS system font
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
        small_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", small_font_size)
    except (OSError, IOError):
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
            small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", small_font_size)
        except (OSError, IOError):
            font = ImageFont.load_default()
            small_font = font

    # Title
    draw.text((50, 30), "OPERATION SILVER BRIDGE", fill="black", font=font)
    draw.text((50, 60), "CLASSIFIED - EVIDENCE DOCUMENT", fill="red", font=font)

    # Simulated evidence text
    lines = [
        "SURVEILLANCE REPORT - Case File #2024-OSB-0147",
        "",
        "Subject: Ricardo Alejandro Mendez-Torres",
        "Location: 1247 Coral Way, Coral Gables, FL 33134",
        "Date of Observation: March 15, 2024",
        "",
        "At approximately 14:32 EST, the subject was observed",
        "arriving at First National Bank of Miami, located at",
        "345 Brickell Avenue, Miami, FL 33131.",
        "",
        "Subject met with an unidentified male (designated UM-1)",
        "at the bank lobby. They proceeded to a private meeting",
        "room on the 3rd floor at 14:45 EST.",
        "",
        "Wire transfer reference: TXN-2024-03-15-88421",
        "Amount: $2,450,000.00 USD",
        "Destination: Cayman Islands National Bank",
        "Account: CI-9982-4471-0023",
        "",
        "Subject departed at 15:22 EST via a black Mercedes S-Class",
        "License plate: FL-DHJ-4829",
    ]

    y_pos = 110
    for line in lines:
        draw.text((50, y_pos), line, fill="black", font=small_font)
        y_pos += 22

    path = OUTPUT_DIR / "evidence_document_ocr.png"
    img.save(path, "PNG")
    print(f"  Created: {path} ({path.stat().st_size:,} bytes)")
    return path


def create_scene_test_image():
    """Create a scene image with shapes and labels for Vision API testing."""
    print("Creating scene test image...")

    img = Image.new("RGB", (800, 600), color="#2c3e50")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
        title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18)
    except (OSError, IOError):
        font = ImageFont.load_default()
        title_font = font

    # Title
    draw.text((250, 15), "SURVEILLANCE CAMERA - CAM #7", fill="white", font=title_font)
    draw.text((550, 40), "2024-03-15 14:32:17", fill="#e74c3c", font=font)

    # Draw building outline
    draw.rectangle([100, 100, 700, 500], outline="#ecf0f1", width=2)
    draw.text((350, 80), "FIRST NATIONAL BANK", fill="#3498db", font=font)

    # Draw entrance
    draw.rectangle([350, 400, 450, 500], fill="#7f8c8d", outline="#ecf0f1")
    draw.text((360, 470), "ENTRANCE", fill="white", font=font)

    # Draw figures (stick figures representing people)
    # Person 1 (subject)
    draw.ellipse([280, 350, 310, 380], fill="#e74c3c")  # head
    draw.line([295, 380, 295, 430], fill="#e74c3c", width=2)  # body
    draw.line([295, 400, 270, 420], fill="#e74c3c", width=2)  # left arm
    draw.line([295, 400, 320, 420], fill="#e74c3c", width=2)  # right arm
    draw.text((265, 435), "SUBJECT", fill="#e74c3c", font=font)

    # Person 2 (UM-1)
    draw.ellipse([480, 350, 510, 380], fill="#f39c12")  # head
    draw.line([495, 380, 495, 430], fill="#f39c12", width=2)
    draw.line([495, 400, 470, 420], fill="#f39c12", width=2)
    draw.line([495, 400, 520, 420], fill="#f39c12", width=2)
    draw.text((480, 435), "UM-1", fill="#f39c12", font=font)

    # Draw car
    draw.rectangle([120, 460, 240, 500], fill="#2c3e50", outline="#bdc3c7")
    draw.ellipse([135, 490, 165, 510], fill="#7f8c8d")
    draw.ellipse([195, 490, 225, 510], fill="#7f8c8d")
    draw.text((130, 465), "FL-DHJ-4829", fill="white", font=font)

    # Annotation arrows and labels
    draw.text((120, 520), "Black Mercedes S-Class", fill="#95a5a6", font=font)

    # Timestamp overlay
    draw.rectangle([0, 560, 800, 600], fill="#000000")
    draw.text((10, 570), "CAM-07 | 345 Brickell Ave, Miami FL | REC", fill="#e74c3c", font=font)

    path = OUTPUT_DIR / "surveillance_scene.png"
    img.save(path, "PNG")
    print(f"  Created: {path} ({path.stat().st_size:,} bytes)")
    return path


def create_financial_document_image():
    """Create a financial document image for OCR testing."""
    print("Creating financial document image...")

    img = Image.new("RGB", (800, 1000), color="white")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
        bold_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18)
        small_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
    except (OSError, IOError):
        font = ImageFont.load_default()
        bold_font = font
        small_font = font

    # Bank header
    draw.text((250, 30), "CAYMAN ISLANDS NATIONAL BANK", fill="navy", font=bold_font)
    draw.text((280, 55), "International Wire Transfer Receipt", fill="gray", font=font)
    draw.line([50, 80, 750, 80], fill="navy", width=2)

    # Transfer details
    y = 100
    details = [
        ("Transaction Reference:", "TXN-2024-03-15-88421"),
        ("Date:", "March 15, 2024"),
        ("Time:", "14:47:33 EST"),
        ("", ""),
        ("ORIGINATOR:", ""),
        ("Name:", "Mendez-Torres Holdings LLC"),
        ("Account:", "FNB-US-3347-8821-0056"),
        ("Bank:", "First National Bank of Miami"),
        ("SWIFT:", "FNBMUS33"),
        ("Address:", "345 Brickell Avenue, Miami, FL 33131"),
        ("", ""),
        ("BENEFICIARY:", ""),
        ("Name:", "Caribbean Maritime Ventures Ltd"),
        ("Account:", "CI-9982-4471-0023"),
        ("Bank:", "Cayman Islands National Bank"),
        ("SWIFT:", "CINBKYKY"),
        ("Address:", "George Town, Grand Cayman, KY1-9001"),
        ("", ""),
        ("AMOUNT:", "$2,450,000.00 USD"),
        ("Fee:", "$45.00 USD"),
        ("Exchange Rate:", "N/A (USD to USD)"),
        ("", ""),
        ("Purpose:", "Investment - Maritime Equipment Purchase"),
        ("Reference:", "PO-CMV-2024-0089"),
        ("", ""),
        ("INTERMEDIARY BANK:", ""),
        ("Name:", "Panama National Banking Corp"),
        ("SWIFT:", "PNBCPAPA"),
        ("Address:", "Via Espana, Panama City, Panama"),
    ]

    for label, value in details:
        if label:
            draw.text((60, y), label, fill="black", font=font)
            draw.text((280, y), value, fill="navy", font=font)
        y += 22

    # Signature line
    y += 20
    draw.line([60, y, 300, y], fill="gray")
    draw.text((60, y + 5), "Authorized Signature", fill="gray", font=small_font)
    draw.line([400, y, 640, y], fill="gray")
    draw.text((400, y + 5), "Compliance Officer", fill="gray", font=small_font)

    # Footer
    draw.line([50, 920, 750, 920], fill="navy", width=1)
    draw.text((150, 930), "This document is confidential and intended solely for authorized recipients.",
              fill="gray", font=small_font)
    draw.text((200, 950), "Cayman Islands National Bank - Licensed under CIMA",
              fill="gray", font=small_font)

    path = OUTPUT_DIR / "wire_transfer_receipt.png"
    img.save(path, "PNG")
    print(f"  Created: {path} ({path.stat().st_size:,} bytes)")
    return path


def create_test_audio():
    """Create a simple WAV audio file with tones for Whisper testing.

    Creates a WAV with distinct frequency tones - won't produce meaningful
    transcription but validates the Whisper pipeline runs end-to-end.
    """
    print("Creating test audio file...")

    sample_rate = 16000
    duration_seconds = 5
    num_samples = sample_rate * duration_seconds

    # Generate a simple tone sequence (440Hz, 550Hz, 660Hz)
    samples = []
    frequencies = [440, 550, 660, 550, 440]
    samples_per_tone = num_samples // len(frequencies)

    for freq in frequencies:
        for i in range(samples_per_tone):
            t = i / sample_rate
            # Sine wave with slight fade in/out
            envelope = min(1.0, i / 800, (samples_per_tone - i) / 800)
            sample = int(16000 * envelope * math.sin(2 * math.pi * freq * t))
            samples.append(struct.pack("<h", max(-32768, min(32767, sample))))

    path = OUTPUT_DIR / "test_audio.wav"
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(samples))

    print(f"  Created: {path} ({path.stat().st_size:,} bytes, {duration_seconds}s)")
    return path


def create_test_audio_speech():
    """Create a longer audio file using ffmpeg with synthesized speech tones.

    This creates a more complex audio file that exercises the Whisper pipeline
    more thoroughly, though it won't produce meaningful speech transcription.
    """
    print("Creating extended test audio file...")

    path = OUTPUT_DIR / "test_audio_extended.wav"

    # Use ffmpeg to generate a more complex audio pattern
    # Sine sweep from 200Hz to 2000Hz over 10 seconds (mimics speech frequency range)
    try:
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "sine=frequency=440:duration=3",
            "-f", "lavfi",
            "-i", "sine=frequency=880:duration=3",
            "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[out]",
            "-map", "[out]",
            "-ar", "16000",
            "-ac", "1",
            str(path),
        ], capture_output=True, text=True, timeout=15)

        if path.exists():
            print(f"  Created: {path} ({path.stat().st_size:,} bytes)")
        else:
            print("  WARNING: ffmpeg audio generation failed, skipping extended audio")
    except FileNotFoundError:
        print("  WARNING: ffmpeg not available, skipping extended audio")
    except subprocess.TimeoutExpired:
        print("  WARNING: ffmpeg timed out, skipping extended audio")

    return path if path.exists() else None


def create_test_video():
    """Create a test video file using ffmpeg with color frames and audio.

    Generates a short video with changing color backgrounds and timestamps,
    plus an audio track for transcription testing.
    """
    print("Creating test video file...")

    path = OUTPUT_DIR / "test_video.mp4"

    try:
        # Create a 10-second test video with:
        # - Changing colors (testsrc2 pattern)
        # - Timestamps burned in
        # - Simple sine wave audio track
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "testsrc2=size=640x480:rate=10:duration=10",
            "-f", "lavfi",
            "-i", "sine=frequency=440:duration=10",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            "-c:a", "aac",
            "-b:a", "64k",
            "-ar", "16000",
            "-shortest",
            str(path),
        ], capture_output=True, text=True, timeout=30)

        if path.exists():
            print(f"  Created: {path} ({path.stat().st_size:,} bytes)")
        else:
            print("  WARNING: ffmpeg video generation failed")
            return None
    except FileNotFoundError:
        print("  WARNING: ffmpeg not available, skipping video generation")
        return None
    except subprocess.TimeoutExpired:
        print("  WARNING: ffmpeg timed out, skipping video")
        return None

    return path


def create_test_video_surveillance():
    """Create a surveillance-style test video with text overlays."""
    print("Creating surveillance test video...")

    path = OUTPUT_DIR / "surveillance_video.mp4"

    try:
        # Create a video with a dark background and text overlay simulating surveillance
        # Using drawtext filter to add timestamp and camera info
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "color=c=0x1a1a2e:size=640x480:rate=10:duration=8",
            "-f", "lavfi",
            "-i", "sine=frequency=300:duration=8",
            "-vf", (
                "drawtext=text='CAM-07 BRICKELL AVE':fontsize=18:fontcolor=white:x=10:y=10,"
                "drawtext=text='%{pts\\:hms}':fontsize=14:fontcolor=red:x=520:y=10,"
                "drawtext=text='REC':fontsize=12:fontcolor=red:x=590:y=30,"
                "drawtext=text='MOTION DETECTED':fontsize=16:fontcolor=yellow:"
                "x=200:y=450:enable='between(t,2,5)'"
            ),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            "-c:a", "aac",
            "-b:a", "64k",
            "-ar", "16000",
            "-shortest",
            str(path),
        ], capture_output=True, text=True, timeout=30)

        if path.exists():
            print(f"  Created: {path} ({path.stat().st_size:,} bytes)")
        else:
            print("  WARNING: Surveillance video generation failed")
            return None
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"  WARNING: Surveillance video generation failed: {e}")
        return None

    return path


def create_test_folder():
    """Create a test folder with mixed media types for folder processing testing."""
    print("Creating mixed media test folder...")

    folder_path = OUTPUT_DIR / "evidence_folder_001"
    folder_path.mkdir(exist_ok=True)

    # Create an image in the folder
    img = Image.new("RGB", (600, 400), color="white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
    except (OSError, IOError):
        font = ImageFont.load_default()

    draw.text((50, 30), "Evidence Photo - Item #147", fill="black", font=font)
    draw.text((50, 60), "Location: 1247 Coral Way, Coral Gables FL", fill="black", font=font)
    draw.text((50, 90), "Date: 2024-03-15", fill="black", font=font)
    draw.text((50, 120), "Photographed by: Agent J. Martinez", fill="black", font=font)
    draw.rectangle([50, 160, 550, 350], outline="gray")
    draw.text((200, 240), "[Evidence Item Photo]", fill="gray", font=font)

    img_path = folder_path / "evidence_photo.jpg"
    img.save(img_path, "JPEG")

    # Create a text metadata file
    meta_path = folder_path / "evidence_notes.txt"
    meta_path.write_text(
        "Evidence Collection Notes\n"
        "========================\n"
        "Case: Operation Silver Bridge (OSB-2024-0147)\n"
        "Date: March 15, 2024\n"
        "Agent: J. Martinez, Badge #4472\n\n"
        "Items collected from 1247 Coral Way:\n"
        "- Financial documents (3 boxes)\n"
        "- Electronic devices (2 laptops, 3 phones)\n"
        "- Photographic evidence (this folder)\n"
        "- Surveillance camera recordings\n"
    )

    # Create a simple audio file in the folder
    sample_rate = 16000
    duration = 3
    samples = []
    for i in range(sample_rate * duration):
        t = i / sample_rate
        sample = int(8000 * math.sin(2 * math.pi * 440 * t))
        samples.append(struct.pack("<h", sample))

    audio_path = folder_path / "audio_recording.wav"
    with wave.open(str(audio_path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(samples))

    print(f"  Created folder: {folder_path}")
    print(f"    - {img_path.name} ({img_path.stat().st_size:,} bytes)")
    print(f"    - {meta_path.name} ({meta_path.stat().st_size:,} bytes)")
    print(f"    - {audio_path.name} ({audio_path.stat().st_size:,} bytes)")
    return folder_path


def main():
    print("=" * 60)
    print("GENERATING TEST MEDIA FILES")
    print("=" * 60)
    print(f"Output directory: {OUTPUT_DIR}")
    print()

    files = {}

    # Images
    files["ocr_image"] = create_ocr_test_image()
    files["scene_image"] = create_scene_test_image()
    files["financial_image"] = create_financial_document_image()

    print()

    # Audio
    files["audio_basic"] = create_test_audio()
    files["audio_extended"] = create_test_audio_speech()

    print()

    # Video
    files["video_basic"] = create_test_video()
    files["video_surveillance"] = create_test_video_surveillance()

    print()

    # Mixed folder
    files["evidence_folder"] = create_test_folder()

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    created = {k: v for k, v in files.items() if v is not None}
    skipped = {k: v for k, v in files.items() if v is None}
    print(f"  Created: {len(created)} test assets")
    print(f"  Skipped: {len(skipped)} (missing dependencies)")
    for name, path in created.items():
        if path.is_dir():
            size = sum(f.stat().st_size for f in path.iterdir())
            print(f"    {name}: {path.name}/ ({size:,} bytes total)")
        else:
            print(f"    {name}: {path.name} ({path.stat().st_size:,} bytes)")
    print("=" * 60)


if __name__ == "__main__":
    main()
