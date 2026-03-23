"""
cli.py — Интерфейс командной строки Kinescope Grabber.

Отвечает за:
  - Красивый ASCII-баннер при запуске
  - Парсинг аргументов командной строки
  - Оркестрация пайплайна: JSON → m3u8 → скачивание → дешифрация → сборка
  - Пакетный режим (обработка папки с JSON файлами)
  - Итоговый отчёт
"""

import argparse
import glob
import os
import platform
import sys
import tempfile
import shutil
import time
from urllib.parse import parse_qs, urlparse

from . import __version__
from .config import C, OS_NAME, log, step, ok, warn, err, die, find_tool, ensure_package
from .parser import parse_journal, parse_media_m3u8, resolve_url, VideoInfo
from .downloader import download_segments
from .crypto import fetch_decryption_key, decrypt_file, validate_with_ffmpeg
from .assembler import merge_to_mp4


# ═══════════════════════════════════════════════════════════
#  ASCII-баннер
# ═══════════════════════════════════════════════════════════

def _make_banner() -> str:
    """Генерирует ASCII-баннер с системной информацией."""
    return f"""
{C.CYAN}    ██╗  ██╗ ██████╗ ██████╗  █████╗ ██████╗
    ██║ ██╔╝██╔════╝ ██╔══██╗██╔══██╗██╔══██╗
    █████╔╝ ██║  ███╗██████╔╝███████║██████╔╝
    ██╔═██╗ ██║   ██║██╔══██╗██╔══██║██╔══██╗
    ██║  ██╗╚██████╔╝██║  ██║██║  ██║██████╔╝
    ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝{C.RESET}
{C.BOLD}{C.WHITE}    K I N E S C O P E   G R A B B E R{C.RESET}
    {C.DIM}─────────────────────────────────────
    v{__version__}  ·  {OS_NAME.upper()}  ·  Python {platform.python_version()}
    github.com/wild-paws/kinescope-grabber{C.RESET}
"""


# ═══════════════════════════════════════════════════════════
#  Поиск JSON файлов
# ═══════════════════════════════════════════════════════════

def find_json_files(path: str) -> list[str]:
    """
    Находит все Kinescope JSON файлы по указанному пути.

    Если путь — файл, возвращает его.
    Если путь — папка, ищет все .json файлы и фильтрует валидные.
    Дедупликация по video_id (берёт самый свежий по expires).

    Args:
        path: Путь к файлу или папке.

    Returns:
        Список путей к валидным JSON файлам (без дубликатов).
    """
    if os.path.isfile(path):
        return [path]

    if not os.path.isdir(path):
        return []

    # Собираем все JSON из папки
    all_json = set()
    for pattern in ("kinescope_player_log_*.json", "*.json"):
        all_json.update(glob.glob(os.path.join(path, pattern)))

    # Парсим и дедуплицируем по video_id
    seen = {}  # video_id → (filepath, expires)
    for filepath in sorted(all_json):
        info = parse_journal(filepath)
        if not info:
            continue

        vid = info.video_id
        # Извлекаем expires для сравнения свежести
        params = parse_qs(urlparse(info.m3u8_url).query)
        expires = int(params.get("expires", ["0"])[0])

        if vid not in seen or expires > seen[vid][1]:
            seen[vid] = (filepath, expires)

    return [filepath for filepath, _ in seen.values()]


# ═══════════════════════════════════════════════════════════
#  HTTP-запросы
# ═══════════════════════════════════════════════════════════

def _http_get(url: str, referrer: str) -> str:
    """GET-запрос с Referer/Origin заголовками."""
    import requests
    origin = urlparse(referrer).scheme + "://" + urlparse(referrer).netloc
    r = requests.get(url, headers={"Referer": referrer, "Origin": origin}, timeout=30)
    r.raise_for_status()
    return r.text


# ═══════════════════════════════════════════════════════════
#  Скачивание одного видео (пайплайн)
# ═══════════════════════════════════════════════════════════

def download_one(
    json_path: str,
    quality: int | None,
    output_dir: str | None,
    ffmpeg: str,
    mp4decrypt: str,
    workers: int = 8,
) -> tuple[bool, str, str]:
    """
    Полный пайплайн скачивания одного видео:
      JSON → m3u8 → сегменты → mp4decrypt → ffmpeg → MP4

    Args:
        json_path: Путь к journal.json.
        quality: Желаемое качество (None = лучшее).
        output_dir: Папка для сохранения (None = ~/Downloads).
        ffmpeg: Путь к ffmpeg.
        mp4decrypt: Путь к mp4decrypt.
        workers: Потоков скачивания.

    Returns:
        Кортеж (success, title, output_path).
    """
    import re

    # ── Парсинг JSON ──
    info = parse_journal(json_path)
    if not info:
        err(f"Невалидный JSON: {json_path}")
        return False, "?", ""

    title = info.title
    q = quality or (info.qualities[0] if info.qualities else 720)

    # Путь для сохранения
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', title).strip()[:200] or "kinescope_video"
    if output_dir:
        output = os.path.join(output_dir, f"{safe_name}_{q}p.mp4")
    else:
        downloads = (
            os.path.join(os.environ.get("USERPROFILE", "."), "Downloads")
            if OS_NAME == "windows"
            else os.path.expanduser("~/Downloads")
        )
        output = os.path.join(downloads, f"{safe_name}_{q}p.mp4")

    # Пропуск уже скачанных
    if os.path.isfile(output) and os.path.getsize(output) > 100_000:
        ok(f"Уже скачан: {os.path.basename(output)} ({os.path.getsize(output)/1048576:.1f} МБ)")
        return True, title, output

    # Заголовок
    dur = f" ({info.duration_str})" if info.duration_str else ""
    log(f"\n  {C.BOLD}{C.CYAN}▶ {title}{C.RESET} — {q}p{dur}")

    # ── m3u8 → сегменты ──
    try:
        video_m3u8_text = _http_get(info.media_url(q, "video"), info.referrer)
        audio_m3u8_text = _http_get(info.media_url(q, "audio"), info.referrer)
    except Exception as e:
        err(f"Ошибка m3u8: {e}")
        return False, title, ""

    v_playlist = parse_media_m3u8(video_m3u8_text)
    a_playlist = parse_media_m3u8(audio_m3u8_text)

    # ── Ключ дешифрования ──
    key_url = v_playlist.key_url or a_playlist.key_url
    key_hex = None
    if key_url:
        if not key_url.startswith("http"):
            key_url = resolve_url(key_url, info.base_url)
        key_hex = fetch_decryption_key(key_url)
        if key_hex:
            ok(f"Ключ: {key_hex[:8]}...{key_hex[-8:]}")
        else:
            warn("Ключ не получен")

    # ── Скачивание сегментов ──
    tmp = tempfile.mkdtemp(prefix="kgrab_")
    v_enc = os.path.join(tmp, "v_enc.mp4")
    a_enc = os.path.join(tmp, "a_enc.mp4")

    try:
        if not download_segments(v_playlist, info.base_url, v_enc, "Видео", workers):
            err("Видео не скачалось")
            shutil.rmtree(tmp, True)
            return False, title, ""
        if not download_segments(a_playlist, info.base_url, a_enc, "Аудио", workers):
            err("Аудио не скачалось")
            shutil.rmtree(tmp, True)
            return False, title, ""
    except Exception as e:
        err(f"Скачивание: {e}")
        shutil.rmtree(tmp, True)
        return False, title, ""

    # ── Дешифрация ──
    v_dec = os.path.join(tmp, "v_dec.mp4")
    a_dec = os.path.join(tmp, "a_dec.mp4")

    if key_hex:
        for src, dst, lbl in [(v_enc, v_dec, "Видео"), (a_enc, a_dec, "Аудио")]:
            if not decrypt_file(mp4decrypt, key_hex, src, dst):
                err(f"Дешифрация {lbl} не удалась")
                shutil.rmtree(tmp, True)
                return False, title, ""
        ok(f"Расшифровано: В={os.path.getsize(v_dec)/1048576:.1f} А={os.path.getsize(a_dec)/1048576:.1f} МБ")
    else:
        v_dec, a_dec = v_enc, a_enc

    # ── Сборка MP4 ──
    if not merge_to_mp4(ffmpeg, v_dec, a_dec, output):
        err("Сборка MP4 не удалась")
        shutil.rmtree(tmp, True)
        return False, title, ""

    shutil.rmtree(tmp, True)

    sz = os.path.getsize(output) / 1048576
    ok(f"Готово: {os.path.basename(output)} — {sz:.1f} МБ")
    return True, title, output


# ═══════════════════════════════════════════════════════════
#  Точка входа CLI
# ═══════════════════════════════════════════════════════════

def main():
    """Главная функция CLI — парсинг аргументов и запуск пайплайна."""

    py = "python" if OS_NAME == "windows" else "python3"

    parser = argparse.ArgumentParser(
        prog="kinescope-grabber",
        description=f"Kinescope Grabber v{__version__} — скачиватель видео с Kinescope",
        epilog=f"""
{C.BOLD}Примеры:{C.RESET}
  {C.DIM}# Одно видео (лучшее качество):{C.RESET}
  {py} -m kinescope_grabber video.json --best

  {C.DIM}# Все видео из папки:{C.RESET}
  {py} -m kinescope_grabber ./jsons/ --best

  {C.DIM}# Конкретное качество + выходная папка:{C.RESET}
  {py} -m kinescope_grabber ./jsons/ -q 720 -o ./videos/

  {C.DIM}# Больше потоков (быстрый интернет):{C.RESET}
  {py} -m kinescope_grabber video.json --best -w 16

{C.BOLD}Как получить journal.json:{C.RESET}
  1. Откройте страницу с видео, нажмите {C.BOLD}Play{C.RESET}
  2. {C.BOLD}Правый клик{C.RESET} по видео → «Сохранить журнал» / «Save journal»
  3. Передайте JSON файл (или папку с файлами) этому скрипту
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "input",
        help="JSON файл или папка с JSON файлами",
    )
    parser.add_argument(
        "-q", "--quality",
        type=int,
        metavar="N",
        help="Качество видео: 360, 480, 720, 1080 (по умолч. лучшее)",
    )
    parser.add_argument(
        "--best",
        action="store_true",
        help="Автоматически выбрать лучшее качество",
    )
    parser.add_argument(
        "-o", "--output",
        metavar="DIR",
        help="Папка для сохранения (по умолч. ~/Downloads)",
    )
    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=8,
        metavar="N",
        help="Количество потоков загрузки (по умолч. 8)",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="Показать информацию о видео без скачивания",
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"Kinescope Grabber v{__version__}",
    )

    args = parser.parse_args()

    # ── Баннер ──
    print(_make_banner())

    # ── Зависимости ──
    step("1", "Проверка зависимостей")
    ensure_package("requests")

    ffmpeg = find_tool("ffmpeg")
    mp4decrypt = find_tool("mp4decrypt")

    if ffmpeg:     ok(f"ffmpeg: {ffmpeg}")
    else:          warn("ffmpeg не найден")
    if mp4decrypt: ok(f"mp4decrypt: {mp4decrypt}")
    else:          warn("mp4decrypt не найден")
    ok(f"Потоков загрузки: {args.workers}")

    # ── Поиск видео ──
    step("2", "Поиск видео")
    files = find_json_files(args.input)

    if not files:
        die(f"Kinescope JSON файлы не найдены: {args.input}")

    # Парсим информацию о каждом видео
    video_infos = []
    for f in files:
        info = parse_journal(f)
        if info:
            video_infos.append((f, info))

    if not video_infos:
        die("Ни один JSON не содержит данных Kinescope")

    # Выводим список найденных видео
    for i, (f, info) in enumerate(video_infos):
        q = args.quality or (info.qualities[0] if info.qualities else 720)
        dur = f" ({info.duration_str})" if info.duration_str else ""
        ok(f"{i+1}. {C.BOLD}{info.title}{C.RESET} — {q}p{dur}")

    log(f"\n  {C.DIM}Найдено: {len(video_infos)} видео{C.RESET}")

    # Только информация
    if args.info:
        import json as json_mod
        for _, info in video_infos:
            print(json_mod.dumps({
                "title": info.title, "video_id": info.video_id,
                "qualities": info.qualities, "duration": info.duration_str,
                "referrer": info.referrer,
            }, indent=2, ensure_ascii=False))
        return

    # Проверка инструментов перед скачиванием
    if not ffmpeg:
        die("ffmpeg обязателен!\n"
            "    macOS:   brew install ffmpeg\n"
            "    Linux:   sudo apt install ffmpeg\n"
            "    Windows: winget install Gyan.FFmpeg")
    if not mp4decrypt:
        die("mp4decrypt обязателен!\n"
            "    macOS:   brew install bento4\n"
            "    Linux:   https://www.bento4.com/downloads/\n"
            "    Windows: https://www.bento4.com/downloads/")

    # ── Выбор качества (для одного видео — интерактивно) ──
    quality = None
    if args.best:
        quality = None  # Лучшее для каждого
    elif args.quality:
        quality = args.quality
    elif len(video_infos) == 1:
        info = video_infos[0][1]
        if info.qualities:
            print(f"\n  {C.BOLD}Качества:{C.RESET}")
            for i, q in enumerate(info.qualities):
                fps = info.frame_rates.get(str(q), "")
                fps_s = f" @ {fps} fps" if fps else ""
                mark = f" {C.GREEN}← лучшее{C.RESET}" if i == 0 else ""
                print(f"    {i+1}) {q}p{fps_s}{mark}")
            try:
                ch = input(f"\n  Выбор [1-{len(info.qualities)}] (Enter=лучшее): ").strip()
                quality = info.qualities[0] if not ch else info.qualities[int(ch) - 1]
            except (ValueError, IndexError):
                quality = info.qualities[0]

    # ── Output dir ──
    output_dir = None
    if args.output:
        output_dir = os.path.abspath(os.path.expanduser(args.output))
        os.makedirs(output_dir, exist_ok=True)

    # ── Скачивание ──
    step("3", f"Загрузка ({len(video_infos)} видео)")

    results = []
    t_start = time.time()

    for i, (f, info) in enumerate(video_infos):
        if len(video_infos) > 1:
            log(f"\n{'─' * 55}")
            log(f"  {C.BOLD}[{i+1}/{len(video_infos)}]{C.RESET}")

        success, title, path = download_one(
            f, quality, output_dir, ffmpeg, mp4decrypt, args.workers
        )
        results.append((success, title, path))

    # ── Итоговый отчёт ──
    elapsed = time.time() - t_start
    succeeded = sum(1 for s, _, _ in results if s)
    failed = len(results) - succeeded
    total_size = sum(
        os.path.getsize(p) / 1048576
        for s, _, p in results
        if s and p and os.path.isfile(p)
    )

    print(f"\n{'═' * 55}")
    print()
    log(f"  {C.BOLD}{C.GREEN}╔═══════════════════════════════════╗{C.RESET}")
    log(f"  {C.BOLD}{C.GREEN}║         ЗАГРУЗКА ЗАВЕРШЕНА        ║{C.RESET}")
    log(f"  {C.BOLD}{C.GREEN}╚═══════════════════════════════════╝{C.RESET}")
    print()

    fail_str = f"  {C.RED}(ошибок: {failed}){C.RESET}" if failed else ""
    log(f"  {C.BOLD}Скачано:{C.RESET}  {succeeded}/{len(results)}{fail_str}")
    log(f"  {C.BOLD}Объём:{C.RESET}    {total_size:.1f} МБ")
    log(f"  {C.BOLD}Время:{C.RESET}    {elapsed:.0f}с")
    print()

    for success, title, path in results:
        if success and path and os.path.isfile(path):
            sz = os.path.getsize(path) / 1048576
            log(f"  {C.GREEN}✓{C.RESET} {title} — {sz:.1f} МБ")
        else:
            log(f"  {C.RED}✗{C.RESET} {title}")

    print()
