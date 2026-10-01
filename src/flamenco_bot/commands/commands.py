from aiogram.types import BotCommand


def get_bot_commands() -> list[BotCommand]:
    return [
        BotCommand(command="start", description="Регистрация и главное меню"),
        BotCommand(command="account", description="Учетная запись"),
        BotCommand(command="lessons", description="Занятия и запись"),
        BotCommand(command="schedule", description="Запросить расписание"),
        BotCommand(command="buy", description="Купить занятия"),
        BotCommand(command="help", description="Справка"),
        BotCommand(command="cancel", description="Отменить текущий ввод"),
        BotCommand(command="admin", description="Панель администратора"),
        BotCommand(command="requests", description="Заявки для администратора"),
        BotCommand(command="done", description="Закрыть заявку"),
        BotCommand(command="slots", description="Управление слотами занятий"),
        BotCommand(command="slot_add", description="Создать слот занятия"),
        BotCommand(command="slot_capacity", description="Изменить вместимость слота"),
        BotCommand(command="slot_close", description="Закрыть слот занятия"),
        BotCommand(command="support_tickets", description="Обращения поддержки"),
        BotCommand(command="support_reply", description="Ответить на обращение"),
        BotCommand(command="support_close", description="Закрыть обращение"),
    ]
