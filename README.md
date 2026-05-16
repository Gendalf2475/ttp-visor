# TTP VISOR

Telegram-бот для внутренней аналитики модерации TimeToPlay.

## Что умеет

- синхронизирует действующих модераторов из Google Sheets;
- собирает новые закрытые тикеты ТП из настроенного чата/топика;
- собирает новые проверенные тикеты КТ;
- собирает выданные и снятые наказания;
- хранит исторические события в PostgreSQL и не удаляет статистику прошлых периодов;
- строит отчёты за неделю, текущий месяц, прошлый месяц, позапрошлый месяц и произвольный период;
- автоматически отправляет отчёты в Telegram по cron-расписанию;
- принимает команды управления от `super_admin_ids`; служебная `/debug` также работает в чатах и топиках.

Важно: Telegram Bot API не отдаёт историю сообщений до добавления бота. Для сбора тикетов бот должен быть добавлен в нужные чаты/топики, а privacy mode у бота нужно отключить через BotFather, если требуется читать все сообщения в группе.

## Быстрый запуск на VPS

1. Скопировать примеры конфигов:

```bash
cp .env.example .env
cp config.yml.example config.yml
```

2. Заполнить `.env`:

- `BOT_TOKEN`;
- `DATABASE_URL`;
- `GOOGLE_CREDENTIALS_FILE` или `GOOGLE_CREDENTIALS_JSON`.

3. Заполнить `config.yml`:

- `bot.super_admin_ids`;
- `telegram_sources.*.chat_id`, `topic_id`, `topic_ids` или `all_topics`;
- `report_target`;
- `google_sheets.spreadsheet_id` и диапазон;
- расписание в `scheduler`.

4. Положить service account JSON рядом с проектом как `google_credentials.json`.

5. Запустить:

```bash
docker compose up -d --build
```

Контейнер `bot` перед стартом сам выполнит `alembic upgrade head`.

## Команды супер-админа

- `/sync_staff` - синхронизация состава из Google Sheets.
- `/stats` - отчёт за текущую неделю.
- `/stats current_month` - текущий месяц.
- `/stats previous_month` - прошлый месяц.
- `/stats two_months_ago` - позапрошлый месяц.
- `/stats 2026-05-01 2026-05-16` - произвольный период.
- `/report [period]` - отправить отчёт в настроенный чат.
- `/debug` - показать `chat_id`, `topic_id` и данные текущего сообщения.
- `/staff_find <текст>` - поиск модератора.
- `/bind <staff_id> <alias> [telegram_user_id]` - ручная привязка алиаса из сообщений к модератору.
- `/unbind <alias>` - удалить привязку.
- `/bindings [текст]` - список привязок.

## Формат таблицы Google Sheets

Источник состава:

- Spreadsheet ID: `1Ss0Eq_zqrbQh2JQ4cr4d1AVG8-7-OPeHorSdh5-umII`
- лист: `Администрация | Штат`
- диапазон: `'Администрация | Штат'!A4:E`

Ожидаемые колонки:

| Колонка | Поле |
| --- | --- |
| A | rank |
| B | nickname |
| C | mentor |
| D | real_name |
| E | telegram_raw |

Отдельной колонки `active` нет. Активным считается любой человек, у которого есть строка в диапазоне и заполнен ник в колонке B. Если ник исчез из диапазона, модератор помечается inactive, а открытый active period закрывается.

Значение Telegram из колонки E нормализуется в `telegram_username`. Поддерживаются форматы:

- `https://t.me/username`
- `http://t.me/username`
- `t.me/username`
- `@username`
- `username`

Исходное значение сохраняется как `telegram_raw`. Если Telegram username есть в таблице, синхронизация автоматически создаёт или обновляет привязки nickname/telegram_username к модератору. Если `telegram_user_id` неизвестен, хранится только username; позже его можно добавить командой `/bind <staff_id> <alias> <telegram_user_id>`.

## Google Service Account

Бот не полагается на публичный доступ к таблице “по ссылке”. Для закрытой Google Sheets используется Google Service Account.

1. Открыть Google Cloud Console и создать проект или выбрать существующий.
2. Включить Google Sheets API.
3. Создать Service Account в разделе IAM & Admin.
4. Создать JSON-ключ для этого Service Account.
5. Сохранить JSON на VPS, например как `google_credentials.json`.
6. В `.env` указать путь:

```bash
GOOGLE_CREDENTIALS_FILE=/opt/ttp-visor/google_credentials.json
```

7. Скопировать email сервисного аккаунта из JSON или Google Cloud Console.
8. Добавить этот email в доступы Google Sheets с ролью Viewer/Читатель.

Публичный доступ “Anyone with the link” не требуется и не должен использоваться как основной механизм доступа.

## Как узнать chat_id и topic_id

1. Добавьте бота в нужный чат.
2. Дайте ему права читать сообщения.
3. В нужном чате или топике отправьте `/debug`.
4. Бот ответит `chat_id` и `topic_id`.
5. Для обычного чата `topic_id` будет `none`.
6. Для форум-топика `topic_id` будет равен `message_thread_id`.

Команда `/debug` доступна только пользователям из `bot.super_admin_ids`. Она работает в личке, группах, супергруппах и форум-топиках.

## Как настроить чат поддержки с множеством топиков

Если каждый тикет или диалог в поддержке создаётся отдельным топиком, нужно использовать `all_topics: true`. Тогда бот будет читать все топики внутри указанного `chat_id` и фильтровать события только по regex-шаблонам закрытия тикета.

```yaml
telegram_sources:
  support:
    enabled: true
    chat_id: -1001234567890
    topic_id: null
    topic_ids: []
    all_topics: true
```

Для источников с фиксированными топиками можно оставить старый формат с одним `topic_id`, либо использовать `topic_ids`:

```yaml
telegram_sources:
  kt:
    enabled: true
    chat_id: -1001234567891
    topic_id: 111
    topic_ids: []
    all_topics: false
```

## Сообщения от других ботов

Чат наказаний может получать события от другого Telegram-бота. TTP VISOR не игнорирует сообщения с `from_user.is_bot = true`: если Telegram Bot API отдаёт такой update, сообщение будет передано в парсер наказаний, а `sender_user_id`, `sender_username` и `sender_is_bot` сохранятся в таблице событий.

Ограничения Telegram:

- TTP VISOR должен быть добавлен в чат наказаний;
- privacy mode у TTP VISOR желательно отключить через BotFather;
- бот должен иметь права читать сообщения в группе/топике;
- нужно использовать актуальные версии Bot API и aiogram;
- Telegram может не отдавать часть сообщений от других ботов в группах.

Если Telegram не отдаёт сообщения исходного лог-бота, нужен fallback: настроить лог-бот так, чтобы он дополнительно отправлял события напрямую в TTP VISOR, либо дублировал наказания сообщениями от обычного пользователя, канала или другой интеграции.

## Архитектура

- `app/bot` - aiogram dispatcher, middleware, handlers.
- `app/config` - `.env` settings и YAML loader.
- `app/db` - SQLAlchemy models, repositories, Alembic migrations.
- `app/services` - Google Sheets, sync, parsers, stats, reports, scheduler.
- `app/utils` - даты, regex, текст, logging.

Парсеры вынесены отдельно и читают regex/markers из `config.yml`, поэтому формат служебных сообщений можно адаптировать без переписывания handler-ов.
