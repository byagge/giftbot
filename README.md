# Gift Bot (aiogram + SQLite)

Telegram-бот с подписками на спонсоров, игрой 9×9, профилем/инвентарём, выводом подарков и админкой.

## Быстрый старт

1) Создайте виртуальное окружение и установите зависимости:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2) Создайте файл `.env` в корне проекта (можно скопировать `env.example` → `.env`):

```env
BOT_TOKEN=123456:ABCDEF
ADMIN_IDS=123456789,987654321
WITHDRAW_REVIEW_CHAT_ID=-1001234567890
```

3) Запуск:

```bash
python -m app
```

## Архитектура (вкратце)
- **Один “главный” UI-месседж**: бот всегда редактирует одно сообщение в меню/профиле/игре, не плодит новые.
- **SQLite**: таблицы `start_sponsors`, `sponsors`, `gifts`, `users`, `inventory`, `attempt_events`, `withdraw_requests`.
- **Проверка подписки**: для `start_sponsors` подписка обязательна для использования бота; для `sponsors` — как задание с бонусом и “списанием бонусов” при отписке в течение 24 часов.


