# 🎬 Kinescope Grabber

<p align="center">
  <a href="https://github.com/user-attachments/assets/e3e9330b-4d73-4bb7-8def-0ae835ff8a59">
    <img src="https://i.ibb.co/JFKL16Fj/pic.jpg" width="700"/>
  </a>
  <br/>
  <b>▶️ Watch Demo Video</b>
</p>

> Кроссплатформенный скачиватель видео с [Kinescope](https://kinescope.io) — с поддержкой **SAMPLE-AES CBCS** шифрования, **многопоточной загрузки** и **пакетного режима**.

```
╔═══════════════════════════════════════════════════════╗
║   ██╗  ██╗ ██████╗ ██████╗  █████╗ ██████╗            ║
║   ██║ ██╔╝██╔════╝ ██╔══██╗██╔══██╗██╔══██╗           ║
║   █████╔╝ ██║  ███╗██████╔╝███████║██████╔╝           ║
║   ██╔═██╗ ██║   ██║██╔══██╗██╔══██║██╔══██╗           ║
║   ██║  ██╗╚██████╔╝██║  ██║██║  ██║██████╔╝           ║
║   ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝            ║
║   K I N E S C O P E   G R A B B E R                   ║
╚═══════════════════════════════════════════════════════╝
```

---

## ✨ Возможности

- 🔐 **Дешифрация SAMPLE-AES CBCS** — обходит шифрование через mp4decrypt
- ⚡ **Многопоточная загрузка** — 8 потоков по умолчанию (~5x быстрее)
- 📁 **Пакетный режим** — скачивание всех видео из папки с JSON файлами
- 🖥️ **Кроссплатформенность** — macOS, Windows, Linux
- 🔄 **Дедупликация** — при нескольких JSON одного видео берёт свежайший
- ⏭️ **Пропуск скачанных** — не перезаписывает уже существующие файлы
- 📊 **Прогресс** — скорость в МБ/с, процент, время загрузки

---

## 📋 Требования

| Компонент | Назначение |
|-----------|------------|
| **Python 3.10+** | Основная среда |
| **ffmpeg** | Склейка видео и аудио в MP4 |
| **mp4decrypt** (Bento4) | Дешифрация SAMPLE-AES CBCS |
| **requests** (pip) | HTTP-запросы (ставится автоматически) |

---

## 🚀 Установка

### Быстрая установка через pip

```bash
pip install git+https://github.com/wild-paws/kinescope-grabber.git
```

После этого доступна команда `kgrab`:

```bash
kgrab video.json --best
kgrab ./jsons/ --best -w 16
```

> ⚠️ **Внешние зависимости** (ffmpeg и mp4decrypt) всё равно нужно установить отдельно — см. инструкции ниже для вашей ОС.

---

### macOS

```bash
# 1. Python (обычно предустановлен, или через Homebrew)
brew install python3

# 2. FFmpeg
brew install ffmpeg

# 3. mp4decrypt (часть Bento4)
brew install bento4

# 4. Скачиваем проект
git clone https://github.com/wild-paws/kinescope-grabber.git
cd kinescope-grabber

# 5. Устанавливаем зависимости Python
pip3 install -r requirements.txt
# На macOS с Homebrew Python может потребоваться:
pip3 install --break-system-packages -r requirements.txt
```

### Windows

```powershell
# 1. Python — скачать с https://python.org/downloads/
#    ☑ Обязательно отметьте "Add to PATH" при установке

# 2. FFmpeg
winget install Gyan.FFmpeg
# Или скачайте с https://www.gyan.dev/ffmpeg/builds/
# и добавьте папку bin\ в PATH

# 3. mp4decrypt (Bento4)
# Скачайте с https://www.bento4.com/downloads/
# Распакуйте и добавьте папку bin\ в PATH
# Или положите mp4decrypt.exe рядом с grabber.py

# 4. Скачиваем проект
git clone https://github.com/wild-paws/kinescope-grabber.git
cd kinescope-grabber

# 5. Зависимости
pip install -r requirements.txt
```

### Linux (Ubuntu/Debian)

```bash
# 1. Python
sudo apt install python3 python3-pip

# 2. FFmpeg
sudo apt install ffmpeg

# 3. mp4decrypt (Bento4)
# Скачайте с https://www.bento4.com/downloads/
wget https://www.bok.net/Bento4/binaries/Bento4-SDK-1-6-0-641.x86_64-unknown-linux.zip
unzip Bento4-SDK-1-6-0-641.x86_64-unknown-linux.zip
sudo cp Bento4-SDK-*/bin/mp4decrypt /usr/local/bin/

# 4. Проект
git clone https://github.com/wild-paws/kinescope-grabber.git
cd kinescope-grabber
pip3 install -r requirements.txt
```

---

## 📖 Использование

### Шаг 1: Получение journal.json

1. Откройте страницу с видео Kinescope в браузере
2. Нажмите **Play** (видео должно начать воспроизведение)
3. **Правый клик** по видео → **«Сохранить журнал»** (или **«Save journal»**)
4. Файл `kinescope_player_log_XXXXX.json` сохранится на диск

> ⚠️ **Важно:** JSON содержит временный токен (expires). Используйте файл в течение нескольких часов после сохранения.

### Шаг 2: Скачивание

```bash
# Если установлен через pip:
kgrab video.json --best
kgrab ./json_folder/ --best
kgrab video.json -q 720 -o ./videos/
kgrab video.json --best -w 16
kgrab video.json --info

# Если скачан через git clone:
python3 grabber.py video.json --best

# Как Python-модуль:
python3 -m kinescope_grabber video.json --best
```

### Аргументы

| Аргумент | Описание |
|----------|----------|
| `input` | JSON файл или папка с JSON файлами |
| `-q`, `--quality` | Качество: 360, 480, 720, 1080 |
| `--best` | Автоматически лучшее качество |
| `-o`, `--output` | Папка для сохранения |
| `-w`, `--workers` | Потоков загрузки (по умолч. 8) |
| `--info` | Показать информацию без скачивания |
| `-v`, `--version` | Версия программы |
| `-h`, `--help` | Справка |

---

## 📁 Структура проекта

```
kinescope-grabber/
├── grabber.py                  # Точка входа: python3 grabber.py
├── requirements.txt            # Python-зависимости
├── LICENSE                     # MIT License
├── README.md                   # Документация
│
└── kinescope_grabber/          # Основной пакет
    ├── __init__.py             # Версия и описание пакета
    ├── __main__.py             # python -m kinescope_grabber
    ├── cli.py                  # CLI: баннер, аргументы, пайплайн
    ├── config.py               # ОС, цвета, поиск инструментов
    ├── parser.py               # Парсинг journal.json и m3u8
    ├── downloader.py           # Многопоточная загрузка сегментов
    ├── crypto.py               # Получение ключей, mp4decrypt
    └── assembler.py            # ffmpeg сборка MP4
```

---

## 🔧 Как это работает

```
journal.json
    │
    ▼
┌──────────────────┐     ┌────────────────────────┐
│  parser.py        │────▶│  media.m3u8 (video)     │
│  Извлекает:       │     │  media.m3u8 (audio)     │
│  - m3u8 URL       │     │  key URL (sample-aes)   │
│  - referrer       │     └────────────────────────┘
│  - qualities      │                │
└──────────────────┘                ▼
                          ┌────────────────────────┐
                          │  downloader.py          │
                          │  8 потоков × N сегм.    │
                          │  byte-range запросы     │
                          │  → video_enc.mp4        │
                          │  → audio_enc.mp4        │
                          └────────────────────────┘
                                     │
                                     ▼
                          ┌────────────────────────┐
                          │  crypto.py              │
                          │  mp4decrypt --key 1:HEX │
                          │  → video_dec.mp4        │
                          │  → audio_dec.mp4        │
                          └────────────────────────┘
                                     │
                                     ▼
                          ┌────────────────────────┐
                          │  assembler.py           │
                          │  ffmpeg -c copy         │
                          │  → output.mp4 ✅        │
                          └────────────────────────┘
```

---

## 🐛 Решение проблем

### «Видео обрезается / застывает»
Скорее всего токен в JSON истёк. Сохраните **свежий** journal.json и скачайте сразу.

### «Access Denied» / «403»
Kinescope привязывает доступ к домену-referrer. Убедитесь что JSON сохранён со страницы, где плеер работает.

### «mp4decrypt: invalid hex format for key»
Ключ получен некорректно. Попробуйте сохранить JSON заново.

### macOS: «pip install ... externally-managed-environment»
```bash
pip3 install --break-system-packages -r requirements.txt
```

### Windows: «'python3' is not recognized»
Используйте `python` вместо `python3`, или `py`:
```powershell
py grabber.py video.json --best
```

---

## 📄 Лицензия

MIT License. Подробности в файле [LICENSE](LICENSE).

---

## ⚠️ Дисклеймер

Этот инструмент предназначен для личного использования — скачивания видео, к которым у вас есть легальный доступ (например, оплаченных курсов для офлайн-просмотра). Авторы не несут ответственности за нарушение авторских прав.
