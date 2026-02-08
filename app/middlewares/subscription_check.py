from aiogram import BaseMiddleware

class SubscriptionCheckMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user_id = event.from_user.id
        # Check subscription status here, for example, using a database or an API
        is_subscribed = await check_user_subscription(user_id)
        if not is_subscribed:
            await event.answer("Подпишитесь на наших спонсоров для продолжения.")
            return
        return await handler(event, data)
