from aiogram.fsm.state import State, StatesGroup


class AccountForm(StatesGroup):
    waiting_for_phone = State()
    waiting_for_phone_code = State()
    waiting_for_name = State()


class LessonForm(StatesGroup):
    waiting_for_booking_time = State()
    waiting_for_purchase_confirmation = State()


class SupportForm(StatesGroup):
    waiting_for_message = State()


class AdminForm(StatesGroup):
    waiting_for_search = State()
    waiting_for_name_target = State()
    waiting_for_name_value = State()
    waiting_for_phone_target = State()
    waiting_for_phone_value = State()
    waiting_for_restart_confirmation = State()
    waiting_for_scheduled_restart = State()
