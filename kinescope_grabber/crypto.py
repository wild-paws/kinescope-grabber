"""
crypto.py — Получение ключей и дешифрация SAMPLE-AES (CBCS).

Отвечает за:
  - Получение ключа дешифрования с license.kinescope.io
  - Обёртку над mp4decrypt (Bento4) для расшифровки видео/аудио
  - Валидацию расшифрованных файлов через ffmpeg

Kinescope использует SAMPLE-AES CBCS шифрование (не обычный AES-128!).
Ни ffmpeg, ни yt-dlp не умеют его расшифровывать. Нужен mp4decrypt.

Ключ получается с endpoint:
  https://license.kinescope.io/v1/vod/{video_id}/acquire/sample-aes/{key_id}?token=

Ответ — 16 сырых байт, которые являются ключом.
"""

import os
import subprocess


# ═══════════════════════════════════════════════════════════
#  Получение ключа дешифрования
# ═══════════════════════════════════════════════════════════

def fetch_decryption_key(key_url: str) -> str | None:
    """
    Получает ключ дешифрования с Kinescope license-сервера.

    Ответ сервера — ровно 16 байт (128 бит), которые являются ключом.
    НЕ base64, а сырые байты, представленные как текст.

    Args:
        key_url: Полный URL для получения ключа (sample-aes endpoint).

    Returns:
        Hex-строка ключа (32 символа) или None при ошибке.
    """
    import requests

    try:
        response = requests.get(
            key_url,
            headers={"Referer": "https://kinescope.io/"},
            timeout=15,
        )
        if response.status_code == 200 and len(response.content) == 16:
            # 16 байт → 32-символьная hex-строка
            return response.content.hex()
    except Exception:
        pass

    return None


# ═══════════════════════════════════════════════════════════
#  Дешифрация через mp4decrypt
# ═══════════════════════════════════════════════════════════

def decrypt_file(
    mp4decrypt_path: str,
    key_hex: str,
    input_path: str,
    output_path: str,
) -> bool:
    """
    Расшифровывает один файл через mp4decrypt (Bento4).

    Формат ключа для mp4decrypt: --key TRACK_ID:KEY_HEX
    Для Kinescope TRACK_ID = 1 (работает для видео и аудио).

    Args:
        mp4decrypt_path: Путь к mp4decrypt.
        key_hex: Hex-строка ключа (32 символа).
        input_path: Путь к зашифрованному файлу.
        output_path: Путь для расшифрованного файла.

    Returns:
        True если дешифрация успешна.
    """
    result = subprocess.run(
        [mp4decrypt_path, "--key", f"1:{key_hex}", input_path, output_path],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return False

    return os.path.isfile(output_path) and os.path.getsize(output_path) > 100


def validate_with_ffmpeg(ffmpeg_path: str, file_path: str) -> bool:
    """
    Проверяет, может ли ffmpeg прочитать файл (первую секунду).

    Args:
        ffmpeg_path: Путь к ffmpeg.
        file_path: Путь к файлу для проверки.

    Returns:
        True если файл валидный.
    """
    try:
        result = subprocess.run(
            [ffmpeg_path, "-v", "error", "-i", file_path, "-f", "null", "-t", "1", "-"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0
    except Exception:
        return False
