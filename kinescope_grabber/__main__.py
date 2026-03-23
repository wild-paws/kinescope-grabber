"""
__main__.py — Точка входа для запуска как модуль.

Позволяет запускать:
  python -m kinescope_grabber video.json --best
"""

from .cli import main

if __name__ == "__main__":
    main()
