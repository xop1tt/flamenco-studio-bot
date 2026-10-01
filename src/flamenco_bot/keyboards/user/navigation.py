from typing import Any

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from ...runtime.admin_access import get_admin_id
from ...handlers.states import AccountForm, AdminForm, LessonForm
from . import (
    account_menu_keyboard,
    class_menu_keyboard,
    main_menu_keyboard,
    purchase_menu_keyboard,
)
from ..admin import admin_menu_keyboard


async def cancel_current_action(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    current_state = await state.get_state()
    await state.clear()

    if current_state in {
        AccountForm.waiting_for_phone.state,
        AccountForm.waiting_for_phone_code.state,
        AccountForm.waiting_for_name.state,
    }:
        reply_markup = account_menu_keyboard()
    elif (
        current_state
        in {
            AdminForm.waiting_for_search.state,
            AdminForm.waiting_for_name_target.state,
            AdminForm.waiting_for_name_value.state,
            AdminForm.waiting_for_phone_target.state,
            AdminForm.waiting_for_phone_value.state,
        }
        and await get_admin_id(message, repository) is not None
    ):
        reply_markup = admin_menu_keyboard()
    elif current_state == LessonForm.waiting_for_booking_time.state:
        reply_markup = class_menu_keyboard()
    elif current_state == LessonForm.waiting_for_purchase_confirmation.state:
        reply_markup = purchase_menu_keyboard()
    else:
        reply_markup = main_menu_keyboard(
            is_admin=await get_admin_id(message, repository) is not None
        )

    await message.answer("Действие отменено.", reply_markup=reply_markup)
