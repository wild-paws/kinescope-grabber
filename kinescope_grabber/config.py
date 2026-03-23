"""
config.py — Конфигурация среды выполнения.

Отвечает за:
  - Определение ОС (macOS / Windows / Linux)
  - Поддержку ANSI-цветов в терминале
  - Поиск внешних инструментов (ffmpeg, mp4decrypt)
  - Форматированный вывод в консоль (ok / warn / err / step)
"""

import os
import platform
import shutil
import sys

# ═══════════════════════════════════════════════════════════
#  Определение ОС
# ═══════════════════════════════════════════════════════════

OS_NAME = {
    "darwin": "macos",
    "windows": "windows",
}.get(platform.system().lower(), "linux")


# ═══════════════════════════════════════════════════════════
#  ANSI-цвета с автодетектом поддержки
# ═══════════════════════════════════════════════════════════

def _supports_ansi() -> bool:
    """Проверяет, поддерживает ли терминал ANSI escape-коды."""
    if os.environ.get("NO_COLOR"):
        return False
    if OS_NAME == "windows":
        # Windows Terminal и новые консоли поддерживают ANSI
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            return True
        except Exception:
            return bool(os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM"))
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_ANSI = _supports_ansi()


class Colors:
    """ANSI escape-коды для цветного вывода. Пустые строки если терминал не поддерживает."""
    BOLD   = "\033[1m"   if _ANSI else ""
    GREEN  = "\033[92m"  if _ANSI else ""
    YELLOW = "\033[93m"  if _ANSI else ""
    RED    = "\033[91m"  if _ANSI else ""
    CYAN   = "\033[96m"  if _ANSI else ""
    DIM    = "\033[90m"  if _ANSI else ""
    RESET  = "\033[0m"   if _ANSI else ""
    BLUE   = "\033[94m"  if _ANSI else ""
    MAGENTA= "\033[95m"  if _ANSI else ""
    WHITE  = "\033[97m"  if _ANSI else ""


# Короткие алиасы для удобства
C = Colors


# ═══════════════════════════════════════════════════════════
#  Функции вывода
# ═══════════════════════════════════════════════════════════

def log(message: str, color: str = C.RESET) -> None:
    """Выводит сообщение с опциональным цветом."""
    print(f"{color}{message}{C.RESET}")


def step(number: str, message: str) -> None:
    """Заголовок шага: [N] Описание."""
    print(f"\n{C.BOLD}{C.CYAN}[{number}]{C.RESET} {message}")


def ok(message: str) -> None:
    """Сообщение об успехе: ✓ текст."""
    print(f"  {C.GREEN}✓{C.RESET} {message}")


def warn(message: str) -> None:
    """Предупреждение: ⚠ текст."""
    print(f"  {C.YELLOW}⚠{C.RESET} {message}")


def err(message: str) -> None:
    """Ошибка: ✗ текст."""
    print(f"  {C.RED}✗{C.RESET} {message}")


def die(message: str) -> None:
    """Критическая ошибка → выход."""
    err(message)
    sys.exit(1)


# ═══════════════════════════════════════════════════════════
#  Поиск внешних инструментов
# ═══════════════════════════════════════════════════════════

# Стандартные пути для каждой ОС
_EXTRA_PATHS = {
    "macos": ["/opt/homebrew/bin", "/usr/local/bin"],
    "linux": ["/usr/bin", "/usr/local/bin", "/snap/bin"],
    "windows": [],
}


def find_tool(name: str) -> str | None:
    """
    Ищет исполняемый файл по имени:
      1. В системном PATH (shutil.which)
      2. Рядом со скриптом
      3. В стандартных путях для ОС

    Returns:
        Полный путь к найденному файлу или None.
    """
    # 1. PATH
    path = shutil.which(name)
    if path:
        return path

    # 2. Рядом со скриптом
    ext = ".exe" if OS_NAME == "windows" else ""
    script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    local = os.path.join(script_dir, name + ext)
    if os.path.isfile(local):
        return local

    # 3. Стандартные пути
    for directory in _EXTRA_PATHS.get(OS_NAME, []):
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate):
            return candidate

    return None


# ═══════════════════════════════════════════════════════════
#  Автоустановка pip-пакетов
# ═══════════════════════════════════════════════════════════

def ensure_package(package: str) -> bool:
    """
    Проверяет наличие pip-пакета и устанавливает его при необходимости.
    Перебирает несколько стратегий для совместимости с Homebrew Python и др.

    Returns:
        True если пакет доступен.
    """
    try:
        __import__(package)
        return True
    except ImportError:
        pass

    warn(f"Пакет '{package}' не найден — устанавливаю...")

    # Порядок стратегий: macOS Homebrew требует --break-system-packages
    strategies = [
        [sys.executable, "-m", "pip", "install", "--break-system-packages", "--user", package],
        [sys.executable, "-m", "pip", "install", "--break-system-packages", package],
        [sys.executable, "-m", "pip", "install", "--user", package],
        [sys.executable, "-m", "pip", "install", package],
    ]

    import subprocess
    for cmd in strategies:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                ok(f"Пакет '{package}' установлен")
                return True
        except Exception:
            continue

    err(f"Не удалось установить '{package}'. Вручную: pip install {package}")
    return False
