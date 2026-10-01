import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from ..runtime.admin_access import get_admin_id
from ..runtime.admin_actions_logging import create_admin_actions_logger
from ..runtime.bot_lifecycle import RestartController
from .states import AdminForm
from ..keyboards.admin import (
    ADMIN_EDIT_NAME,
    ADMIN_EDIT_PHONE,
    ADMIN_MENU,
    ADMIN_SEARCH,
    BOT_MANAGEMENT_MENU,
    BOT_RESTART,
    BOT_RESTART_CANCEL,
    BOT_RESTART_CONFIRM,
    BOT_CANCEL_SCHEDULED_RESTART,
    BOT_SCHEDULE_RESTART,
    BOT_STATUS,
    admin_action_keyboard,
    admin_menu_keyboard,
    bot_management_keyboard,
    bot_restart_confirmation_keyboard,
    bot_schedule_input_keyboard,
)
from ..keyboards.common import CANCEL, MAIN_MENU
from ..keyboards.user import main_menu_keyboard
from ..runtime.runtime_resources import get_process_resources


logger = logging.getLogger("bot.handlers.admin")
actions_logger = create_admin_actions_logger()
router = Router(name="admin_commands")


async def _admin_id(message: Message, repository: Any) -> Optional[int]:
    return await get_admin_id(message, repository)


async def _deny_non_admin(message: Message, repository: Any) -> bool:
    if await _admin_id(message, repository) is not None:
        return False
    await message.answer("Команда доступна только администратору студии.")
    logger.warning(
        "Rejected admin action telegram_id=%s",
        message.from_user.id if message.from_user else None,
    )
    actions_logger.warning(
        "action=denied actor_id=%s",
        message.from_user.id if message.from_user else None,
    )
    return True


def _parse_telegram_id(value: Optional[str]) -> Optional[int]:
    if value is None or not value.isdigit():
        return None
    telegram_id = int(value)
    return telegram_id if telegram_id > 0 else None


@router.message(Command("admin"))
async def admin_command(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    if await _deny_non_admin(message, repository):
        return

    await state.clear()
    await message.answer(
        "Админ-меню. Выберите действие:",
        reply_markup=admin_menu_keyboard(),
    )
    logger.info(
        "Opened admin menu telegram_id=%s",
        await _admin_id(message, repository),
    )


@router.message(F.text == ADMIN_MENU)
async def open_admin_menu(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    await admin_command(message, state, repository)


@router.message(F.text == BOT_MANAGEMENT_MENU)
async def open_bot_management_menu(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    if await _deny_non_admin(message, repository):
        return
    await state.clear()
    await message.answer(
        "Управление ботом. Выберите действие:",
        reply_markup=bot_management_keyboard(),
    )


@router.message(F.text == BOT_STATUS)
async def show_bot_status(
    message: Message,
    restart_controller: RestartController,
    repository: Any,
) -> None:
    if await _deny_non_admin(message, repository):
        return
    uptime_seconds = max(0, int(time.monotonic() - restart_controller.started_at))
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    statistics = await repository.get_user_statistics(
        datetime.now(timezone.utc) - timedelta(minutes=5)
    )
    memory_mb, cpu_seconds = get_process_resources()
    scheduled_restart = (
        restart_controller.scheduled_restart_at.strftime("%Y-%m-%d %H:%M")
        if restart_controller.scheduled_restart_at is not None
        else "нет"
    )
    await message.answer(
        "Бот работает.\nВремя работы: {} ч {} мин {} сек.\n"
        "CPU с запуска: {:.1f} сек.\nПиковая память: {:.1f} МБ.\n"
        "Пользователей всего: {}.\nАктивны за 5 минут: {}.\n"
        "Запланированный перезапуск (время сервера): {}.\n"
        "Причина перезапуска: {}.".format(
            hours,
            minutes,
            seconds,
            cpu_seconds,
            memory_mb,
            statistics.total_users,
            statistics.online_users,
            scheduled_restart,
            restart_controller.restart_reason or "нет",
        ),
        reply_markup=bot_management_keyboard(),
    )


@router.message(F.text == BOT_RESTART)
async def request_bot_restart(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    if await _deny_non_admin(message, repository):
        return
    await state.set_state(AdminForm.waiting_for_restart_confirmation)
    await message.answer(
        "Перезапустить бота сейчас? Текущий процесс будет остановлен.",
        reply_markup=bot_restart_confirmation_keyboard(),
    )


@router.message(F.text == BOT_RESTART_CONFIRM)
async def confirm_bot_restart(
    message: Message,
    state: FSMContext,
    restart_controller: RestartController,
    repository: Any,
) -> None:
    if await _deny_non_admin(message, repository):
        await state.clear()
        return
    if await state.get_state() != AdminForm.waiting_for_restart_confirmation.state:
        await message.answer(
            "Сначала выберите перезапуск в меню управления ботом.",
            reply_markup=bot_management_keyboard(),
        )
        return
    await state.clear()
    await message.answer(
        "Перезапуск бота выполняется.",
        reply_markup=main_menu_keyboard(is_admin=True),
    )
    actions_logger.warning(
        "action=restart_bot admin_id=%s",
        await _admin_id(message, repository),
    )
    await restart_controller.request_restart("admin_requested")


@router.message(F.text == BOT_RESTART_CANCEL)
async def cancel_bot_restart(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    if await _deny_non_admin(message, repository):
        await state.clear()
        return
    await state.clear()
    await message.answer(
        "Перезапуск отменён.",
        reply_markup=bot_management_keyboard(),
    )


@router.message(F.text == BOT_SCHEDULE_RESTART)
async def start_scheduling_restart(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    if await _deny_non_admin(message, repository):
        return
    await state.set_state(AdminForm.waiting_for_scheduled_restart)
    await message.answer(
        "Введите дату и время перезапуска по локальному времени сервера "
        "в формате ГГГГ-ММ-ДД ЧЧ:ММ.",
        reply_markup=bot_schedule_input_keyboard(),
    )


@router.message(F.text == BOT_CANCEL_SCHEDULED_RESTART)
async def cancel_scheduled_restart(
    message: Message,
    state: FSMContext,
    restart_controller: RestartController,
    repository: Any,
) -> None:
    if await _deny_non_admin(message, repository):
        return
    await state.clear()
    if not await restart_controller.cancel_scheduled_restart():
        await message.answer(
            "Запланированного перезапуска нет.",
            reply_markup=bot_management_keyboard(),
        )
        return
    await message.answer(
        "Запланированный перезапуск отменён.",
        reply_markup=bot_management_keyboard(),
    )


@router.message(AdminForm.waiting_for_scheduled_restart, F.text == CANCEL)
async def cancel_restart_schedule_input(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    if await _deny_non_admin(message, repository):
        await state.clear()
        return
    await state.clear()
    await message.answer(
        "Планирование отменено.",
        reply_markup=bot_management_keyboard(),
    )


@router.message(AdminForm.waiting_for_scheduled_restart, F.text == MAIN_MENU)
async def return_to_main_menu_from_schedule(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    if await _deny_non_admin(message, repository):
        await state.clear()
        return
    await state.clear()
    await message.answer(
        "Главное меню студии фламенко.",
        reply_markup=main_menu_keyboard(is_admin=True),
    )


@router.message(AdminForm.waiting_for_scheduled_restart)
async def save_restart_schedule(
    message: Message,
    state: FSMContext,
    restart_controller: RestartController,
    repository: Any,
) -> None:
    if await _deny_non_admin(message, repository):
        await state.clear()
        return
    try:
        scheduled_at = datetime.strptime(
            (message.text or "").strip(),
            "%Y-%m-%d %H:%M",
        ).astimezone()
        await restart_controller.schedule_restart(scheduled_at)
    except ValueError:
        await message.answer(
            "Укажите будущее время в формате ГГГГ-ММ-ДД ЧЧ:ММ."
        )
        return
    await state.clear()
    await message.answer(
        "Перезапуск запланирован на {} (локальное время сервера).".format(
            scheduled_at.strftime("%Y-%m-%d %H:%M")
        ),
        reply_markup=bot_management_keyboard(),
    )


@router.message(AdminForm.waiting_for_restart_confirmation, Command("cancel"))
async def command_cancel_bot_restart(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    if await _deny_non_admin(message, repository):
        await state.clear()
        return
    await state.clear()
    await message.answer(
        "Перезапуск отменён.",
        reply_markup=bot_management_keyboard(),
    )


@router.message(AdminForm.waiting_for_restart_confirmation, F.text == MAIN_MENU)
async def return_to_main_menu_from_restart(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    if await _deny_non_admin(message, repository):
        await state.clear()
        return
    await state.clear()
    await message.answer(
        "Главное меню студии фламенко.",
        reply_markup=main_menu_keyboard(is_admin=True),
    )


@router.message(AdminForm.waiting_for_restart_confirmation)
async def require_restart_confirmation(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    if await _deny_non_admin(message, repository):
        await state.clear()
        return
    await message.answer(
        "Для перезапуска нажмите «Подтвердить перезапуск» или отмените действие.",
        reply_markup=bot_restart_confirmation_keyboard(),
    )


@router.message(F.text == MAIN_MENU)
async def leave_admin_menu(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    await state.clear()
    await message.answer(
        "Главное меню студии фламенко.",
        reply_markup=main_menu_keyboard(
            is_admin=await _admin_id(message, repository) is not None
        ),
    )


@router.message(F.text == ADMIN_SEARCH)
async def start_participant_search(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    if await _deny_non_admin(message, repository):
        return
    await state.set_state(AdminForm.waiting_for_search)
    await message.answer(
        "Введите Telegram ID, имя или часть номера телефона для поиска.",
        reply_markup=admin_action_keyboard(),
    )


@router.message(AdminForm.waiting_for_search)
async def search_participants(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    if await _deny_non_admin(message, repository):
        await state.clear()
        return

    query = (message.text or "").strip()
    if not query or len(query) > 100:
        await message.answer("Введите поисковый запрос длиной от 1 до 100 символов.")
        return

    profiles = await repository.search_profiles(query, limit=20)
    await state.clear()
    if not profiles:
        await message.answer(
            "Участники не найдены.",
            reply_markup=admin_menu_keyboard(),
        )
        actions_logger.info(
            "action=search admin_id=%s query_length=%s results=0",
            await _admin_id(message, repository),
            len(query),
        )
        return

    lines = ["Найденные участники (максимум 20):"]
    for profile in profiles:
        lines.append(
            "ID: {} | {} | телефон: {}".format(
                profile.telegram_id,
                profile.user_name,
                profile.phone or "не указан",
            )
        )
    await message.answer("\n".join(lines), reply_markup=admin_menu_keyboard())
    actions_logger.info(
        "action=search admin_id=%s query_length=%s results=%s",
        await _admin_id(message, repository),
        len(query),
        len(profiles),
    )


@router.message(F.text == ADMIN_EDIT_NAME)
async def start_edit_participant_name(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    if await _deny_non_admin(message, repository):
        return
    await state.set_state(AdminForm.waiting_for_name_target)
    await message.answer(
        "Введите Telegram ID участника, имя которого нужно изменить.",
        reply_markup=admin_action_keyboard(),
    )


@router.message(AdminForm.waiting_for_name_target)
async def select_name_target(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    if await _deny_non_admin(message, repository):
        await state.clear()
        return
    telegram_id = _parse_telegram_id(message.text)
    if telegram_id is None:
        await message.answer("Telegram ID должен быть положительным целым числом.")
        return
    await state.update_data(target_telegram_id=telegram_id)
    await state.set_state(AdminForm.waiting_for_name_value)
    await message.answer(
        "Введите новое имя (от 1 до 64 символов).",
        reply_markup=admin_action_keyboard(),
    )


@router.message(AdminForm.waiting_for_name_value)
async def save_participant_name(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    if await _deny_non_admin(message, repository):
        await state.clear()
        return
    user_name = (message.text or "").strip()
    if not user_name or len(user_name) > 64:
        await message.answer("Имя должно содержать от 1 до 64 символов.")
        return

    form_data = await state.get_data()
    telegram_id = form_data.get("target_telegram_id")
    if not isinstance(telegram_id, int):
        await state.clear()
        await message.answer("Не удалось определить участника.")
        return
    if await repository.get_profile(telegram_id) is None:
        await state.clear()
        await message.answer(
            "Участник с таким Telegram ID не найден.",
            reply_markup=admin_menu_keyboard(),
        )
        actions_logger.warning(
            "action=edit_name admin_id=%s target_id=%s result=not_found",
            await _admin_id(message, repository),
            telegram_id,
        )
        return

    await repository.update_user_name(telegram_id, user_name)
    await state.clear()
    await message.answer("Имя участника обновлено.", reply_markup=admin_menu_keyboard())
    actions_logger.info(
        "action=edit_name admin_id=%s target_id=%s",
        await _admin_id(message, repository),
        telegram_id,
    )


@router.message(F.text == ADMIN_EDIT_PHONE)
async def start_edit_participant_phone(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    if await _deny_non_admin(message, repository):
        return
    await state.set_state(AdminForm.waiting_for_phone_target)
    await message.answer(
        "Введите Telegram ID участника, телефон которого нужно изменить.",
        reply_markup=admin_action_keyboard(),
    )


@router.message(AdminForm.waiting_for_phone_target)
async def select_phone_target(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    if await _deny_non_admin(message, repository):
        await state.clear()
        return
    telegram_id = _parse_telegram_id(message.text)
    if telegram_id is None:
        await message.answer("Telegram ID должен быть положительным целым числом.")
        return
    await state.update_data(target_telegram_id=telegram_id)
    await state.set_state(AdminForm.waiting_for_phone_value)
    await message.answer(
        "Введите новый номер телефона (до 32 символов).",
        reply_markup=admin_action_keyboard(),
    )


@router.message(AdminForm.waiting_for_phone_value)
async def save_participant_phone(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    if await _deny_non_admin(message, repository):
        await state.clear()
        return
    phone = (message.text or "").strip()
    if not re.fullmatch(r"\+?[0-9][0-9 ()-]{5,30}", phone):
        await message.answer(
            "Введите номер телефона: цифры, пробелы, скобки и дефисы "
            "(от 7 до 32 символов)."
        )
        return

    form_data = await state.get_data()
    telegram_id = form_data.get("target_telegram_id")
    if not isinstance(telegram_id, int):
        await state.clear()
        await message.answer("Не удалось определить участника.")
        return
    if await repository.get_profile(telegram_id) is None:
        await state.clear()
        await message.answer(
            "Участник с таким Telegram ID не найден.",
            reply_markup=admin_menu_keyboard(),
        )
        actions_logger.warning(
            "action=edit_phone admin_id=%s target_id=%s result=not_found",
            await _admin_id(message, repository),
            telegram_id,
        )
        return

    await repository.update_phone(telegram_id, phone)
    await state.clear()
    await message.answer(
        "Телефон участника обновлён.",
        reply_markup=admin_menu_keyboard(),
    )
    actions_logger.info(
        "action=edit_phone admin_id=%s target_id=%s",
        await _admin_id(message, repository),
        telegram_id,
    )

@router.message(Command("requests"))
async def list_requests(message: Message, repository: Any) -> None:
    admin_id = await _admin_id(message, repository)
    if admin_id is None:
        await message.answer("Команда доступна только администратору студии.")
        return

    requests = await repository.list_pending_requests()
    if not requests:
        await message.answer("Незакрытых заявок нет.")
        return

    lines = ["Незакрытые заявки:"]
    for request in requests:
        lines.append(
            "№{} | {} | Telegram ID {} | {}".format(
                request.id,
                "запись" if request.kind == "booking" else "покупка",
                request.telegram_id,
                request.details,
            )
        )
    await message.answer("\n".join(lines))
    logger.info("Listed %s pending requests admin_id=%s", len(requests), admin_id)


@router.message(Command("done"))
async def complete_request(message: Message, repository: Any) -> None:
    admin_id = await _admin_id(message, repository)
    if admin_id is None:
        await message.answer("Команда доступна только администратору студии.")
        return

    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Формат команды: /done ID")
        return

    completed = await repository.complete_request(int(parts[1]))
    await message.answer(
        "Заявка закрыта." if completed else "Незакрытая заявка с таким ID не найдена."
    )
    logger.info(
        "Admin completed request request_id=%s admin_id=%s success=%s",
        parts[1],
        admin_id,
        completed,
    )
    actions_logger.info(
        "action=complete_request admin_id=%s request_id=%s success=%s",
        admin_id,
        parts[1],
        completed,
    )
