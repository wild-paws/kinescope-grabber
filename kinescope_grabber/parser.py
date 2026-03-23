"""
parser.py — Парсинг Kinescope journal.json и HLS media.m3u8.

Отвечает за:
  - Извлечение метаданных из journal.json (title, video_id, m3u8 URL, DRM и т.д.)
  - Парсинг master.m3u8 для получения URL видео/аудио потоков
  - Парсинг media.m3u8 для извлечения сегментов (byte-range), URL ключа
  - Валидация и нормализация данных
"""

import json
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse


# ═══════════════════════════════════════════════════════════
#  Датаклассы для структурированных данных
# ═══════════════════════════════════════════════════════════

@dataclass
class VideoInfo:
    """Метаданные видео, извлечённые из journal.json."""
    title: str
    video_id: str
    m3u8_url: str
    referrer: str
    base_url: str
    qualities: list[int] = field(default_factory=list)
    frame_rates: dict = field(default_factory=dict)
    duration: float = 0.0

    @property
    def duration_str(self) -> str:
        """Форматированная длительность (M:SS)."""
        if not self.duration:
            return ""
        m, s = divmod(int(self.duration), 60)
        return f"{m}:{s:02d}"

    @property
    def sign_params(self) -> str:
        """Извлекает sign и expires из m3u8 URL для авторизации запросов."""
        params = parse_qs(urlparse(self.m3u8_url).query)
        return "&".join(
            f"{k}={params[k][0]}"
            for k in ("sign", "expires")
            if k in params
        )

    def media_url(self, quality: int, stream_type: str = "video") -> str:
        """
        Формирует URL media.m3u8 для конкретного качества и типа потока.

        Args:
            quality: Качество (360, 480, 720, 1080)
            stream_type: "video" или "audio"
        """
        sp = self.sign_params
        if stream_type == "audio":
            return f"{self.base_url}media.m3u8?quality={quality}&type=audio&lang=und&{sp}&token="
        return f"{self.base_url}media.m3u8?quality={quality}&type=video&{sp}&token="


@dataclass
class Segment:
    """Один HLS-сегмент (byte-range кусок видео/аудио файла)."""
    url: str
    byte_size: int | None = None   # Размер в байтах
    byte_offset: int | None = None  # Смещение от начала файла


@dataclass
class MediaPlaylist:
    """Результат парсинга media.m3u8."""
    init_segment: Segment | None = None  # Инициализирующий сегмент (заголовок контейнера)
    segments: list[Segment] = field(default_factory=list)  # Все data-сегменты
    key_url: str | None = None  # URL для получения ключа дешифрования


# ═══════════════════════════════════════════════════════════
#  Парсинг journal.json
# ═══════════════════════════════════════════════════════════

def parse_journal(path: str) -> VideoInfo | None:
    """
    Парсит Kinescope journal.json и возвращает VideoInfo.

    Args:
        path: Путь к JSON файлу.

    Returns:
        VideoInfo с метаданными видео, или None если файл не валидный.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    # Находим playlist — может быть в rawOptions или options
    playlist = _extract_playlist(data)
    if not playlist:
        return None

    # m3u8 URL — ищем в sources (shakahls или hls)
    m3u8 = _extract_m3u8(playlist)
    if not m3u8:
        return None

    # Название видео (убираем расширение если есть)
    title = playlist.get("title", "kinescope_video")
    for ext in (".mp4", ".mkv", ".avi", ".mov", ".webm"):
        if title.lower().endswith(ext):
            title = title[:-len(ext)]
            break

    # Video ID
    video_id = playlist.get("id") or data.get("state", {}).get("videoId", "unknown")

    # Качества
    qualities = _extract_qualities(playlist)

    # Frame rates
    frame_rates = playlist.get("frameRate", {})

    # Длительность
    meta = playlist.get("meta", {})
    duration = float(meta.get("duration", 0)) or data.get("state", {}).get("duration", 0)

    # Base URL для запросов
    parsed = urlparse(m3u8)
    base_url = f"{parsed.scheme}://{parsed.netloc}/{video_id}/"

    # Referrer (сайт, на котором встроен плеер)
    referrer = data.get("referrer", "https://kinescope.io/")

    return VideoInfo(
        title=title,
        video_id=video_id,
        m3u8_url=m3u8,
        referrer=referrer,
        base_url=base_url,
        qualities=qualities,
        frame_rates=frame_rates,
        duration=duration,
    )


# ═══════════════════════════════════════════════════════════
#  Парсинг media.m3u8
# ═══════════════════════════════════════════════════════════

def parse_media_m3u8(text: str) -> MediaPlaylist:
    """
    Парсит содержимое media.m3u8 и извлекает сегменты.

    HLS fmp4 формат Kinescope:
      - #EXT-X-MAP:URI=... — init-сегмент (заголовок MP4-контейнера)
      - #EXT-X-KEY:...URI=... — URL ключа шифрования
      - #EXT-X-BYTERANGE:SIZE@OFFSET — byte-range следующего сегмента
      - URL — CDN-адрес сегмента (с kcd= параметром авторизации)

    Args:
        text: Содержимое m3u8 файла.

    Returns:
        MediaPlaylist с init-сегментом, data-сегментами и URL ключа.
    """
    result = MediaPlaylist()
    pending_byterange = None

    for line in text.split("\n"):
        line = line.strip()

        # Ключ шифрования: #EXT-X-KEY:METHOD=SAMPLE-AES,...,URI="..."
        if line.startswith("#EXT-X-KEY:") and "URI=" in line:
            match = re.search(r'URI="([^"]+)"', line)
            if match:
                result.key_url = match.group(1)

        # Init сегмент: #EXT-X-MAP:URI="...",BYTERANGE="SIZE@OFFSET"
        if line.startswith("#EXT-X-MAP:"):
            uri_match = re.search(r'URI="([^"]+)"', line)
            br_match = re.search(r'BYTERANGE="(\d+)@(\d+)"', line)
            if uri_match:
                result.init_segment = Segment(
                    url=uri_match.group(1),
                    byte_size=int(br_match.group(1)) if br_match else None,
                    byte_offset=int(br_match.group(2)) if br_match else None,
                )

        # Byte range для следующего сегмента: #EXT-X-BYTERANGE:SIZE@OFFSET
        if line.startswith("#EXT-X-BYTERANGE:"):
            parts = line.split(":")[1]
            if "@" in parts:
                sz, off = parts.split("@")
                pending_byterange = (int(sz), int(off))
            else:
                pending_byterange = (int(parts), None)

        # URL сегмента (не начинается с #, длина > 5)
        if line and not line.startswith("#") and len(line) > 5:
            seg = Segment(url=line)
            if pending_byterange:
                seg.byte_size, seg.byte_offset = pending_byterange
                pending_byterange = None
            result.segments.append(seg)

    return result


def resolve_url(url: str, base_url: str) -> str:
    """Преобразует относительный URL в абсолютный."""
    return url if url.startswith("http") else base_url + url


# ═══════════════════════════════════════════════════════════
#  Приватные хелперы
# ═══════════════════════════════════════════════════════════

def _extract_playlist(data: dict) -> dict | None:
    """Извлекает первый playlist из rawOptions или options."""
    for key in ("rawOptions", "options"):
        if key in data and "playlist" in data[key]:
            pl = data[key]["playlist"]
            if isinstance(pl, list) and pl:
                return pl[0]
    return None


def _extract_m3u8(playlist: dict) -> str | None:
    """Извлекает m3u8 URL из sources (shakahls предпочтительнее hls)."""
    for source_key in ("shakahls", "hls"):
        src = playlist.get("sources", {}).get(source_key)
        if isinstance(src, dict) and "src" in src:
            return src["src"]
        elif isinstance(src, str):
            return src
    return None


def _extract_qualities(playlist: dict) -> list[int]:
    """Извлекает и сортирует доступные качества (от лучшего к худшему)."""
    ql = playlist.get("qualityLabels", {})
    if "list" in ql:
        return sorted(ql["list"], reverse=True)
    return sorted([int(k) for k in ql if k.isdigit()], reverse=True)
