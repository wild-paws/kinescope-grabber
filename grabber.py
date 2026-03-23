#!/usr/bin/env python3
"""
grabber.py — Быстрый запуск Kinescope Grabber.

Использование:
  python3 grabber.py video.json --best
  python3 grabber.py ./jsons/ --best -w 16
  python3 grabber.py --help

Эквивалентно:
  python3 -m kinescope_grabber video.json --best
"""

from kinescope_grabber.cli import main

if __name__ == "__main__":
    main()
