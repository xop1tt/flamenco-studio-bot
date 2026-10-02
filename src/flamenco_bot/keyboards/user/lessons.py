import logging
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from ...runtime.admin_access import get_admin_id
from . import (
    BOOK_CLASS,
    BACK_TO_CLASSES,
    BACK_TO_PURCHASES,
    CANCEL,
    MAIN_MENU,
    class_menu_keyboard,
    lessons_menu_keyboard,
    main_menu_keyboard,
    purchase_menu_keyboard,
    purchase_confirmation_keyboard,
)
from .navigation import cancel_current_action
from .main_menu import ensure_profile
from ...handlers.states import LessonForm
from ...database.repository import SlotUnavailableError
from ...payments import LessonPackage, PURCHASE_OPTIONS, YooKassaClient
from ...class_catalog import CLASS_KEYS_BY_LABEL, CLASS_LABELS
from ...services import (
    AdminNotifier,
    BookingService,
    CheckoutFailedError,
    PaymentCheckStatus,
    PaymentService,
)


logger = logging.getLogger("bot.handlers.lessons")
router = Router(name="lessons_keyboard")
CLASS_CHOICES = set(CLASS_KEYS_BY_LABEL)


def class_slots_keyboard(class_key: str, slots: Any) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="{} (свободно {})".format(
                        slot.starts_at.strftime("%d.%m.%Y %H:%M"),
                        slot.remaining,
                    ),
                    callback_data="book:{}:{}".format(class_key, slot.id),
                )
            ]
            for slot in slots
        ]
    )


@router.message(F.text == BOOK_CLASS)
async def choose_class(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Выберите подходящий формат занятия. Администратор подтвердит уровень "
        "и наличие мест.",
        reply_markup=class_menu_keyboard(),
    )
    logger.info(
        "Opened class selection telegram_id=%s",
        message.from_user.id if message.from_user else None,
    )


@router.message(F.text.in_(CLASS_CHOICES))
async def select_class(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    label = message.text
    if label is None:
        raise ValueError("Для выбора формата требуется текстовое сообщение")
    class_key = CLASS_KEYS_BY_LABEL[label]
    slots = await repository.list_available_class_slots(class_key)
    await state.clear()
    if not slots:
        await message.answer(
            "Сейчас нет свободных слотов для формата «{}». "
            "Попробуйте позже или обратитесь в поддержку.".format(
                CLASS_LABELS[class_key]
            ),
            reply_markup=lessons_menu_keyboard(),
        )
    else:
        await message.answer(
            "Выберите свободное время для занятия «{}». "
            "Запись подтвердится сразу после выбора.".format(CLASS_LABELS[class_key]),
            reply_markup=class_slots_keyboard(class_key, slots),
        )
    logger.info(
        "Selected class telegram_id=%s class_key=%s available_slots=%s",
        message.from_user.id if message.from_user else None,
        class_key,
        len(slots),
    )


@router.callback_query(F.data.startswith("book:"))
async def book_class_slot(
    callback: CallbackQuery,
    repository: Any,
) -> None:
    parts = (callback.data or "").split(":")
    sender = callback.from_user
    if (
        len(parts) != 3
        or parts[1] not in CLASS_LABELS
        or not parts[2].isdigit()
        or sender is None
    ):
        await callback.answer("Некорректная запись.", show_alert=True)
        return
    bot = callback.bot
    if bot is None:
        raise RuntimeError("Telegram bot is unavailable for callback handling")
    slot_id = int(parts[2])
    await repository.get_or_create_profile(
        telegram_id=sender.id,
        user_name=sender.full_name.strip() or "Участник студии",
        is_admin=False,
    )
    booking_service = BookingService(repository, AdminNotifier(bot, repository))
    try:
        booking = await booking_service.book(slot_id, sender.id)
    except SlotUnavailableError:
        await callback.answer(
            "Это место уже заняли или запись закрыта. Обновите список слотов.",
            show_alert=True,
        )
        return

    await callback.answer(
        "Вы уже записаны." if booking.already_booked else "Место подтверждено!"
    )
    await bot.send_message(
        sender.id,
        "Вы записаны на «{}» {}.".format(
            CLASS_LABELS[booking.class_key],
            booking.starts_at.strftime("%d.%m.%Y в %H:%M"),
        ),
        reply_markup=lessons_menu_keyboard(),
    )
    if not booking.already_booked:
        await booking_service.notify_admins_about_booking(booking, sender.full_name)


@router.message(F.text.in_(PURCHASE_OPTIONS))
async def select_purchase(
    message: Message,
    state: FSMContext,
) -> None:
    label = message.text
    if label is None:
        raise ValueError("Для выбора пакета требуется текстовое сообщение")
    package = PURCHASE_OPTIONS[label]
    await state.update_data(
        package_key=package.key,
        package_title=package.title,
        package_lessons=package.lessons,
        package_price_rub=package.price_rub,
    )
    await state.set_state(LessonForm.waiting_for_purchase_confirmation)
    await message.answer(
        "Купить «{}» за {} ₽? После оплаты занятия будут добавлены на ваш "
        "баланс.".format(package.title, package.price_rub),
        reply_markup=purchase_confirmation_keyboard(),
    )
    logger.info(
        "Selected lesson package telegram_id=%s package=%s",
        message.from_user.id if message.from_user else None,
        package.key,
    )


@router.message(F.text == BACK_TO_CLASSES)
async def back_to_classes(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Выберите формат занятия.",
        reply_markup=class_menu_keyboard(),
    )


@router.message(F.text == BACK_TO_PURCHASES)
async def back_to_purchase_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Выберите формат занятий.",
        reply_markup=purchase_menu_keyboard(),
    )


@router.message(LessonForm.waiting_for_purchase_confirmation)
async def submit_purchase_request(
    message: Message,
    state: FSMContext,
    repository: Any,
    payment_gateway: YooKassaClient,
) -> None:
    if message.from_user is None:
        raise ValueError("У сообщения отсутствует Telegram-пользователь")
    form_data = await state.get_data()
    package_key = form_data.get("package_key")
    package = next(
        (item for item in PURCHASE_OPTIONS.values() if item.key == package_key), None
    )
    package_title = form_data.get("package_title")
    package_lessons = form_data.get("package_lessons")
    package_price_rub = form_data.get("package_price_rub")
    if (
        package is None
        or not isinstance(package_title, str)
        or not isinstance(package_lessons, int)
        or not isinstance(package_price_rub, int)
    ):
        logger.error(
            "Purchase snapshot missing telegram_id=%s package_key=%s",
            message.from_user.id,
            package_key,
        )
        await state.clear()
        await message.answer(
            "Не удалось определить выбранный вариант. Выберите пакет заново.",
            reply_markup=purchase_menu_keyboard(),
        )
        return

    payment_service = PaymentService(repository, payment_gateway)
    if not payment_service.checkout_available:
        await state.clear()
        await message.answer(
            "Оплата недоступна: настройте ЮKassa и постоянное хранение PostgreSQL. "
            "Обратитесь к администратору студии.",
            reply_markup=purchase_menu_keyboard(),
        )
        logger.warning(
            "Purchase checkout unavailable configured=%s durable_storage=%s",
            payment_gateway.is_configured,
            getattr(repository, "supports_durable_payments", False),
        )
        return

    await ensure_profile(message, repository)
    snapshot_package = LessonPackage(
        key=package.key,
        title=package_title,
        lessons=package_lessons,
        price_rub=package_price_rub,
    )
    try:
        checkout = await payment_service.start_checkout(
            message.from_user.id, snapshot_package
        )
    except CheckoutFailedError:
        await state.clear()
        await message.answer(
            "Не удалось безопасно подтвердить создание платежа. Не запускайте "
            "повторную оплату; обратитесь к администратору для сверки.",
            reply_markup=purchase_menu_keyboard(),
        )
        return

    await state.clear()
    payment = checkout.payment
    confirmation_url = checkout.confirmation_url
    if confirmation_url is None:
        await message.answer(
            "Платёж №{} зарегистрирован, но получить безопасную ссылку на оплату "
            "не удалось. Не создавайте новый платёж; обратитесь к администратору "
            "для сверки.".format(payment.id),
            reply_markup=purchase_menu_keyboard(),
        )
        return
    await message.answer(
        "Платёж №{} создан на сумму {} ₽. Перейдите к оплате, затем нажмите "
        "«Проверить оплату».".format(payment.id, checkout.amount_minor // 100),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Перейти к оплате",
                        url=confirmation_url,
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Проверить оплату",
                        callback_data="lesson_payment_check:{}".format(payment.id),
                    )
                ],
            ]
        ),
    )


@router.callback_query(F.data.startswith("lesson_payment_check:"))
async def check_lesson_payment(
    callback: CallbackQuery,
    repository: Any,
    payment_gateway: YooKassaClient,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer("Не удалось определить пользователя.", show_alert=True)
        return
    try:
        payment_id = int((callback.data or "").split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Некорректный номер платежа.", show_alert=True)
        return

    payment_service = PaymentService(repository, payment_gateway)
    result = await payment_service.check_payment(payment_id, callback.from_user.id)

    if result.status is PaymentCheckStatus.NOT_FOUND:
        await callback.answer("Платёж не найден.", show_alert=True)
    elif result.status is PaymentCheckStatus.ALREADY_SUCCEEDED:
        await callback.answer("Оплата уже подтверждена.")
        await callback.message.answer(
            "Платёж уже подтверждён. Остаток занятий: {}.".format(result.credits)
        )
    elif result.status is PaymentCheckStatus.CANCELED:
        await callback.answer("Платёж отменён.", show_alert=True)
    elif result.status is PaymentCheckStatus.REFUND_PENDING:
        await callback.answer(
            "Возврат уже обрабатывается. Занятия временно недоступны.",
            show_alert=True,
        )
    elif result.status is PaymentCheckStatus.PROVIDER_UNAVAILABLE:
        await callback.answer(
            "Не удалось проверить платёж. Попробуйте позже.",
            show_alert=True,
        )
    elif result.status is PaymentCheckStatus.MISMATCH:
        await callback.answer(
            "Данные платежа не совпали. Обратитесь к администратору.",
            show_alert=True,
        )
    elif result.status is PaymentCheckStatus.ALREADY_PROCESSED:
        await callback.answer("Статус платежа уже обработан.")
        await callback.message.answer(
            "Платёж уже подтверждён. Остаток занятий: {}.".format(result.credits)
        )
    elif result.status is PaymentCheckStatus.STATUS_CHANGED:
        await callback.answer("Статус платежа уже обработан.")
        await callback.message.answer(
            "Статус платежа изменился во время сверки. Проверьте позже "
            "или обратитесь к администратору."
        )
    elif result.status is PaymentCheckStatus.CONFIRMED:
        await callback.answer("Оплата подтверждена.")
        await callback.message.answer(
            "Оплата подтверждена. На баланс добавлено {} занятий. Остаток: {}.".format(
                result.payment.lessons, result.credits
            )
        )
    elif result.status is PaymentCheckStatus.PROVIDER_CANCELED:
        await callback.answer("Платёж отменён.", show_alert=True)
    else:
        await callback.answer("Оплата ещё не подтверждена.")


@router.message(F.text == CANCEL)
async def cancel_lesson_flow(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    await cancel_current_action(message, state, repository)
    logger.info(
        "Canceled lesson flow telegram_id=%s",
        message.from_user.id if message.from_user else None,
    )


@router.message(F.text == MAIN_MENU)
async def return_from_lessons(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    await state.clear()
    await message.answer(
        "Главное меню студии фламенко.",
        reply_markup=main_menu_keyboard(
            is_admin=await get_admin_id(message, repository) is not None
        ),
    )
