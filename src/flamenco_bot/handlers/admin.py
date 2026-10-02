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
from ..payments import YooKassaClient
from ..services import PaymentService, RefundStatus
from ..class_catalog import CLASS_LABELS
from ..database.repository import CLASS_KEYS
from ..keyboards.admin import CLASS_SLOTS, SUPPORT_TICKETS


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


async def _show_class_slots(message: Message, repository: Any) -> None:
    slots = await repository.list_class_slots(limit=30)
    if not slots:
        await message.answer(
            "Будущих слотов пока нет.\n"
            "Создать: /slot_add beginner 2030-10-02T18:00+04:00 8",
            reply_markup=admin_menu_keyboard(),
        )
        return
    lines = [
        "Ближайшие слоты (максимум 30; ID | формат | дата/время | "
        "занято/вместимость | статус):"
    ]
    lines.extend(
        "{} | {} | {} | {}/{} | {}".format(
            slot.id,
            CLASS_LABELS[slot.class_key],
            slot.starts_at.strftime("%d.%m.%Y %H:%M %Z"),
            slot.booked_count,
            slot.capacity,
            "открыт" if slot.status == "open" else "закрыт",
        )
        for slot in slots
    )
    lines.extend(
        [
            "",
            "Создать: /slot_add beginner 2030-10-02T18:00+04:00 8",
            "Вместимость: /slot_capacity ID ЧИСЛО",
            "Закрыть: /slot_close ID",
        ]
    )
    await message.answer("\n".join(lines), reply_markup=admin_menu_keyboard())


@router.message(F.text == CLASS_SLOTS)
@router.message(Command("slots"))
async def show_class_slots(message: Message, repository: Any) -> None:
    if await _deny_non_admin(message, repository):
        return
    await _show_class_slots(message, repository)


@router.message(Command("slot_add"))
async def add_class_slot(message: Message, repository: Any) -> None:
    admin_id = await _admin_id(message, repository)
    if admin_id is None:
        await _deny_non_admin(message, repository)
        return
    parts = (message.text or "").split()
    if len(parts) != 4:
        await message.answer(
            "Формат: /slot_add beginner 2030-10-02T18:00+04:00 8\n"
            "Ключ занятия: beginner, intermediate или individual. "
            "Время указывайте с часовым поясом."
        )
        return
    class_key = parts[1]
    if class_key not in CLASS_KEYS:
        await message.answer("Формат: beginner, intermediate или individual.")
        return
    try:
        starts_at = datetime.fromisoformat(parts[2])
        capacity = int(parts[3])
        if starts_at.tzinfo is None or starts_at.utcoffset() is None:
            raise ValueError("Укажите часовой пояс, например +04:00")
        slot = await repository.create_class_slot(
            class_key,
            starts_at,
            capacity,
            admin_id,
        )
    except ValueError as error:
        await message.answer(
            "Не удалось создать слот: {}. Пример: "
            "/slot_add beginner 2030-10-02T18:00+04:00 8".format(error)
        )
        return
    await message.answer(
        "Слот №{} создан: «{}», {} (вместимость {}).".format(
            slot.id,
            CLASS_LABELS[slot.class_key],
            slot.starts_at.strftime("%d.%m.%Y %H:%M %Z"),
            slot.capacity,
        ),
        reply_markup=admin_menu_keyboard(),
    )
    actions_logger.info(
        "action=create_class_slot admin_id=%s slot_id=%s class_key=%s capacity=%s",
        admin_id,
        slot.id,
        class_key,
        capacity,
    )


@router.message(Command("slot_capacity"))
async def change_class_slot_capacity(message: Message, repository: Any) -> None:
    admin_id = await _admin_id(message, repository)
    if admin_id is None:
        await _deny_non_admin(message, repository)
        return
    parts = (message.text or "").split()
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        await message.answer("Формат: /slot_capacity ID ЧИСЛО")
        return
    slot_id, capacity = int(parts[1]), int(parts[2])
    try:
        updated = await repository.update_class_slot_capacity(slot_id, capacity)
    except ValueError as error:
        await message.answer("Не удалось изменить вместимость: {}.".format(error))
        return
    if not updated:
        await message.answer("Слот с таким ID не найден.")
        return
    await message.answer("Вместимость слота №{} обновлена.".format(slot_id))
    actions_logger.info(
        "action=change_class_slot_capacity admin_id=%s slot_id=%s capacity=%s",
        admin_id,
        slot_id,
        capacity,
    )


@router.message(Command("slot_close"))
async def close_class_slot(message: Message, repository: Any) -> None:
    admin_id = await _admin_id(message, repository)
    if admin_id is None:
        await _deny_non_admin(message, repository)
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Формат: /slot_close ID")
        return
    slot_id = int(parts[1])
    if not await repository.close_class_slot(slot_id):
        await message.answer("Открытый слот с таким ID не найден.")
        return
    await message.answer("Слот №{} закрыт для новых записей.".format(slot_id))
    actions_logger.info(
        "action=close_class_slot admin_id=%s slot_id=%s",
        admin_id,
        slot_id,
    )


@router.message(F.text == SUPPORT_TICKETS)
async def show_support_tickets(message: Message, repository: Any) -> None:
    if await _deny_non_admin(message, repository):
        return
    tickets = await repository.list_open_support_tickets(limit=20)
    lines = [
        "Открытых обращений нет."
        if not tickets
        else (
            "Открытые обращения (ответ: /support_reply ID текст; "
            "закрыть: /support_close ID):"
        )
    ]
    lines.extend(
        "№{} | пользователь {} | {}".format(
            ticket.id,
            ticket.telegram_id,
            ticket.last_message.replace("\n", " ")[:120],
        )
        for ticket in tickets
    )
    await message.answer("\n".join(lines), reply_markup=admin_menu_keyboard())


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
        await message.answer("Укажите будущее время в формате ГГГГ-ММ-ДД ЧЧ:ММ.")
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


async def _process_lesson_refund(
    message: Message,
    payment_id: int,
    repository: Any,
    payment_gateway: YooKassaClient,
    admin_id: int,
    reason: Optional[str] = None,
) -> None:
    payment_service = PaymentService(repository, payment_gateway)
    result = await payment_service.process_refund(payment_id, admin_id, reason)

    if result.status is RefundStatus.INVALID:
        await message.answer(result.error_message)
    elif result.status is RefundStatus.UNAVAILABLE:
        await message.answer(
            "Возврат недоступен: платёж не найден или не находится в статусе "
            "успешной оплаты."
        )
    elif result.status is RefundStatus.PROVIDER_UNAVAILABLE:
        await message.answer(
            "Не удалось подтвердить результат возврата в ЮKassa. Баланс занятий "
            "зарезервирован; повторите /refund_check {} для сверки.".format(payment_id)
        )
    elif result.status is RefundStatus.MISMATCH:
        await message.answer(
            "Данные возврата не совпали. Баланс зарезервирован; требуется "
            "ручная сверка с ЮKassa."
        )
    elif result.status is RefundStatus.COMPLETED:
        await message.answer(
            "Возврат подтверждён. Списание {} неиспользованных занятий "
            "зафиксировано.".format(result.lessons)
        )
        actions_logger.warning(
            "action=refund payment_id=%s admin_id=%s refund_id=%s",
            payment_id,
            admin_id,
            result.provider_refund_id,
        )
    elif result.status is RefundStatus.ALREADY_PROCESSED:
        await message.answer(
            "ЮKassa подтвердила возврат, но локальная запись уже обработана. "
            "Проверьте аудит платежа."
        )
    elif result.status is RefundStatus.PENDING:
        await message.answer(
            "ЮKassa приняла возврат, он ещё обрабатывается. Повторите "
            "/refund_check {} позже.".format(payment_id)
        )
    elif result.status is RefundStatus.RELEASED:
        await message.answer(
            "ЮKassa отменила возврат. Резерв занятий снят, баланс восстановлен. "
            "При необходимости можно повторить /refund {} причина.".format(payment_id)
        )
    else:
        await message.answer(
            "ЮKassa вернула статус «{}». Баланс остаётся зарезервированным; "
            "требуется сверка с провайдером.".format(result.provider_status)
        )


@router.message(Command("refund"))
async def refund_lesson_payment(
    message: Message,
    repository: Any,
    payment_gateway: YooKassaClient,
) -> None:
    admin_id = await _admin_id(message, repository)
    if admin_id is None:
        await message.answer("Команда доступна только администратору студии.")
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].strip():
        await message.answer("Формат команды: /refund ID причина")
        return
    await _process_lesson_refund(
        message,
        int(parts[1]),
        repository,
        payment_gateway,
        admin_id,
        parts[2],
    )


@router.message(Command("refund_check"))
async def check_lesson_refund(
    message: Message,
    repository: Any,
    payment_gateway: YooKassaClient,
) -> None:
    admin_id = await _admin_id(message, repository)
    if admin_id is None:
        await message.answer("Команда доступна только администратору студии.")
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Формат команды: /refund_check ID")
        return
    await _process_lesson_refund(
        message,
        int(parts[1]),
        repository,
        payment_gateway,
        admin_id,
    )
