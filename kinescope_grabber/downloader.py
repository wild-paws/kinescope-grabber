"""
downloader.py — Многопоточная загрузка HLS-сегментов.

Отвечает за:
  - Параллельную загрузку сегментов через ThreadPoolExecutor
  - Byte-range запросы для каждого сегмента
  - Сборку сегментов в правильном порядке
  - Отображение прогресса (МБ/с, процент)

Архитектура:
  Каждый сегмент в Kinescope HLS — это byte-range часть одного MP4 файла
  на CDN, но с разными kcd= параметрами авторизации. Поэтому каждый
  сегмент скачивается отдельным HTTP-запросом со своим URL.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import C, ok, err
from .parser import MediaPlaylist, Segment, resolve_url


# ═══════════════════════════════════════════════════════════
#  Загрузка одного сегмента
# ═══════════════════════════════════════════════════════════

def _fetch_segment(session, url: str, headers: dict) -> bytes:
    """
    Скачивает один сегмент.

    Args:
        session: requests.Session с базовыми заголовками.
        url: Полный URL сегмента (с kcd= авторизацией).
        headers: Дополнительные заголовки (Range).

    Returns:
        Содержимое сегмента в байтах.

    Raises:
        requests.HTTPError: При HTTP-ошибке.
    """
    response = session.get(url, headers=headers, timeout=60)
    response.raise_for_status()
    return response.content


# ═══════════════════════════════════════════════════════════
#  Подготовка задач для скачивания
# ═══════════════════════════════════════════════════════════

def _build_range_header(segment: Segment) -> dict:
    """
    Формирует Range-заголовок для byte-range запроса.

    Args:
        segment: Сегмент с byte_size и byte_offset.

    Returns:
        Словарь с заголовком Range или пустой словарь.
    """
    if segment.byte_size is not None and segment.byte_offset is not None:
        end = segment.byte_offset + segment.byte_size - 1
        return {"Range": f"bytes={segment.byte_offset}-{end}"}
    return {}


def _prepare_tasks(playlist: MediaPlaylist, base_url: str) -> list[tuple[int, str, dict]]:
    """
    Подготавливает список задач (index, url, headers) для скачивания.

    Index = -1 для init-сегмента, 0..N для data-сегментов.
    Это гарантирует правильный порядок при сборке.

    Args:
        playlist: Распарсенный MediaPlaylist.
        base_url: Базовый URL для resolve.

    Returns:
        Список кортежей (index, url, headers).
    """
    tasks = []

    # Init-сегмент (заголовок fMP4-контейнера)
    if playlist.init_segment:
        url = resolve_url(playlist.init_segment.url, base_url)
        headers = _build_range_header(playlist.init_segment)
        tasks.append((-1, url, headers))

    # Data-сегменты
    for i, seg in enumerate(playlist.segments):
        url = resolve_url(seg.url, base_url)
        headers = _build_range_header(seg)
        tasks.append((i, url, headers))

    return tasks


# ═══════════════════════════════════════════════════════════
#  Основная функция скачивания
# ═══════════════════════════════════════════════════════════

def download_segments(
    playlist: MediaPlaylist,
    base_url: str,
    dest_path: str,
    label: str = "",
    workers: int = 8,
) -> bool:
    """
    Скачивает все сегменты MediaPlaylist в один файл.

    Сегменты загружаются параллельно в `workers` потоков, затем
    собираются в правильном порядке (init → seg0 → seg1 → ...).

    Args:
        playlist: Распарсенный MediaPlaylist с сегментами.
        base_url: Базовый URL для resolve относительных ссылок.
        dest_path: Путь для сохранения результата.
        label: Метка для прогресса ("Видео" / "Аудио").
        workers: Количество параллельных потоков (по умолч. 8).

    Returns:
        True если файл скачан успешно (размер > 1000 байт).
    """
    import requests
    import os

    if not playlist.segments:
        return False

    total_segs = len(playlist.segments)
    tasks = _prepare_tasks(playlist, base_url)

    # HTTP-сессия (переиспользует TCP-соединения)
    session = requests.Session()
    session.headers.update({"Referer": "https://kinescope.io/"})

    # Параллельная загрузка
    results = {}        # index → bytes
    done_count = 0
    total_bytes = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        # Запускаем все задачи
        futures = {}
        for idx, url, headers in tasks:
            future = pool.submit(_fetch_segment, session, url, headers)
            futures[future] = idx

        # Собираем результаты по мере готовности
        for future in as_completed(futures):
            idx = futures[future]
            try:
                data = future.result()
                results[idx] = data
                done_count += 1
                total_bytes += len(data)

                # Прогресс
                elapsed = time.time() - t0
                speed = total_bytes / 1048576 / elapsed if elapsed > 0 else 0
                pct = done_count * 100 // len(tasks)
                print(
                    f"\r  {C.DIM}{label}: {done_count}/{total_segs} ({pct}%) "
                    f"— {total_bytes/1048576:.1f} МБ — {speed:.1f} МБ/с{C.RESET}    ",
                    end="", flush=True,
                )
            except Exception as e:
                err(f"\n  Сегмент {idx}: {e}")
                results[idx] = b""

    print()  # Новая строка после прогресса

    # Сборка в правильном порядке
    with open(dest_path, "wb") as out:
        # Init-сегмент
        if playlist.init_segment and -1 in results:
            out.write(results[-1])
        # Data-сегменты по порядку
        for i in range(total_segs):
            if i in results:
                out.write(results[i])

    # Итог
    file_size = os.path.getsize(dest_path)
    elapsed = time.time() - t0
    speed = file_size / 1048576 / elapsed if elapsed > 0 else 0
    ok(f"{label}: {file_size/1048576:.1f} МБ ({total_segs} сег, {elapsed:.0f}с, {speed:.1f} МБ/с)")

    return file_size > 1000
