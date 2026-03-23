"""
assembler.py — Сборка финального MP4 из видео и аудио потоков.

Отвечает за:
  - Склеивание расшифрованных видео и аудио в один MP4 через ffmpeg
  - Перенос метаданных (movflags +faststart для стриминга)
  - Валидацию результата
"""

import os
import subprocess


def merge_to_mp4(
    ffmpeg_path: str,
    video_path: str,
    audio_path: str,
    output_path: str,
) -> bool:
    """
    Склеивает видео и аудио в MP4 через ffmpeg.

    Использует -c copy (без перекодирования) и +faststart
    для быстрого начала воспроизведения.

    Args:
        ffmpeg_path: Путь к ffmpeg.
        video_path: Расшифрованный видео-файл.
        audio_path: Расшифрованный аудио-файл.
        output_path: Путь для результата.

    Returns:
        True если сборка успешна (файл > 10 КБ).
    """
    # Создаём директорию если не существует
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    result = subprocess.run(
        [
            ffmpeg_path, "-y",
            "-loglevel", "warning",
            "-i", video_path,
            "-i", audio_path,
            "-c", "copy",
            "-movflags", "+faststart",
            output_path,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return False

    return os.path.isfile(output_path) and os.path.getsize(output_path) > 10000
