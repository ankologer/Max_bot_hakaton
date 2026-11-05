# MAX bot

Python 3.12, maxo, Tortoise ORM + SQLite, Loguru, python-dotenv.
События принимаются через long polling.

## Быстрый старт в PowerShell

Установите Python 3.12 с Python Launcher и откройте PowerShell
в корне проекта. Создайте окружение и установите зависимости:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Укажите `BOT_TOKEN` и сохраните `.env`. Активация `.venv` не нужна:
мы вызываем её Python напрямую, поэтому политика выполнения
PowerShell не мешает работе и менять ExecutionPolicy не требуется.

Также поддерживаются Python 3.13 и 3.14: замените `-3.12`
на установленную версию. Python 3.15 текущий maxo не поддерживает.

Справка работает без токена и запуска бота:

```powershell
.\.venv\Scripts\python.exe src/main.py --help
.\.venv\Scripts\python.exe src/main.py -h
.\.venv\Scripts\python.exe src/main.py help
```

Команды прямого запуска:

```powershell
.\.venv\Scripts\python.exe src/main.py
.\.venv\Scripts\python.exe src/main.py --LOG_LEVEL=DEBUG
.\.venv\Scripts\python.exe -m src.main
```

Windows поддерживается напрямую. Для остановки бота нажмите Ctrl+C:
программа отменит обработчики, закроет соединения и допишет логи.
В контейнере дополнительно поддерживается остановка через SIGTERM.

## Настройки

Приоритет: `--KEY=VALUE` → `.env` → окружение → значения по умолчанию.
Пути считаются от корня проекта. Для пробелов используйте кавычки.

| Переменная | По умолчанию |
| --- | --- |
| `BOT_TOKEN` | Обязателен |
| `DATABASE_PATH` | `data/bot.sqlite3` |
| `LOG_FILE` | `logs/bot.log` |
| `LOG_LEVEL` | `INFO` |

## Поведение и расширение

- `/start` — приветствие, `/help` — справка, `/me` — профиль.
- Остальной текст повторяется; вложения не копируются.
- Middleware передаёт профиль из БД параметром `profile: User`.
- События пользователя обрабатываются последовательно.
- Дубликаты отсеиваются в памяти на время `PROCESSED_UPDATE_TTL`.
  После перезапуска отметки теряются.
- Новые роутеры подключайте в `src/handlers/__init__.py` перед эхо.
- Таблицы создаются при запуске; изменение схемы требует миграций.
- Логи: stderr и файл, ротация 10 МБ, хранение архивов 7 дней.

## Запуск на Windows 10 через Docker Desktop

Установите и запустите [Docker Desktop][docker].
Требования к версии Windows указаны в инструкции установки.
Python и `.venv` на стороне Windows для этого способа не нужны.

Откройте PowerShell в корне проекта и подготовьте `.env`:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Заполните `BOT_TOKEN`. По умолчанию образ — `python:3.12-alpine`.
В PowerShell перенос строки обозначается обратным апострофом:

```powershell
docker build -t maxbot .
docker build -t maxbot:slim `
  --build-arg BASE_IMAGE=python:3.12-slim .
docker run --rm maxbot --help

docker run -d --name maxbot `
  --env-file .env `
  --mount type=volume,source=maxbot-data,target=/app/data `
  --mount type=volume,source=maxbot-logs,target=/app/logs `
  maxbot

docker logs -f maxbot
docker stop --timeout 30 maxbot
```

Volumes сохраняют БД и логи после удаления контейнера.
`.env` не включается в образ; значения передаются через `--env-file`.
Для переопределения добавьте `--KEY=VALUE` после имени образа.

Сборка: системные пакеты (`apk`/`apt-get`), venv с библиотеками,
пользователь и права. Компиляторы остаются в промежуточном образе.
UID/GID по умолчанию — `10001:10001`; аргументы сборки —
`APP_UID` и `APP_GID`. Запускайте один процесс для одного токена.

[docker]: https://docs.docker.com/desktop/install/windows-install/
