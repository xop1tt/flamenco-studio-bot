import logging
from urllib.parse import urlsplit
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramAPIError
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
from ...database.repository import PaymentAttemptUnresolved, SlotUnavailableError
from ...payments import PaymentProviderError, PURCHASE_OPTIONS, YooKassaClient
from ...class_catalog import CLASS_KEYS_BY_LABEL, CLASS_LABELS


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
    try:
        booking = await repository.book_class_slot(slot_id, sender.id)
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
        admin_ids = await repository.list_admin_ids()
        delivered_admins = 0
        for admin_id in admin_ids:
            try:
                await bot.send_message(
                    admin_id,
                    "Новая запись №{}: {} — {}, участник {} (ID {}).".format(
                        booking.id,
                        CLASS_LABELS[booking.class_key],
                        booking.starts_at.strftime("%d.%m.%Y в %H:%M %Z"),
                        sender.full_name,
                        sender.id,
                    ),
                )
                delivered_admins += 1
            except TelegramAPIError as error:
                logger.warning(
                    "Class booking notification failed booking_id=%s "
                    "admin_id=%s error_type=%s",
                    booking.id,
                    admin_id,
                    type(error).__name__,
                )
        if not admin_ids or delivered_admins < len(admin_ids):
            logger.error(
                "Class booking confirmed without notifying all admins "
                "booking_id=%s recipients=%s delivered=%s",
                booking.id,
                len(admin_ids),
                delivered_admins,
            )
    logger.info(
        "Class booking confirmed slot_id=%s telegram_id=%s duplicate=%s",
        slot_id,
        sender.id,
        booking.already_booked,
    )


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

    if not payment_gateway.is_configured or not getattr(
        repository, "supports_durable_payments", False
    ):
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

    try:
        await ensure_profile(message, repository)
        attempt = await repository.begin_lesson_payment_attempt(
            telegram_id=message.from_user.id,
            package_key=package.key,
            package_title=package_title,
            lessons=package_lessons,
            amount_minor=package_price_rub * 100,
        )
        provider_payment = await payment_gateway.create_payment(
            amount_minor=attempt.amount_minor,
            description="Фламенко: {}".format(attempt.package_title),
            telegram_id=message.from_user.id,
            package_key=attempt.package_key,
            idempotence_key=str(attempt.idempotence_key),
        )
    except (PaymentProviderError, PaymentAttemptUnresolved, ValueError) as error:
        await state.clear()
        logger.error(
            "Failed to create YooKassa payment telegram_id=%s error_type=%s",
            message.from_user.id,
            type(error).__name__,
        )
        await message.answer(
            "Не удалось безопасно подтвердить создание платежа. Не запускайте "
            "повторную оплату; обратитесь к администратору для сверки.",
            reply_markup=purchase_menu_keyboard(),
        )
        return

    payment = await repository.create_lesson_payment(
        telegram_id=message.from_user.id,
        package_key=attempt.package_key,
        package_title=attempt.package_title,
        lessons=attempt.lessons,
        amount_minor=attempt.amount_minor,
        provider_payment_id=provider_payment.payment_id,
        confirmation_url=provider_payment.confirmation_url or "",
        idempotence_key=attempt.idempotence_key,
    )
    await state.clear()
    confirmation_url = provider_payment.confirmation_url
    try:
        parsed_confirmation_url = (
            urlsplit(confirmation_url) if confirmation_url is not None else None
        )
    except ValueError:
        parsed_confirmation_url = None
    if (
        parsed_confirmation_url is None
        or parsed_confirmation_url.scheme != "https"
        or not parsed_confirmation_url.hostname
        or parsed_confirmation_url.username is not None
        or parsed_confirmation_url.password is not None
    ):
        logger.error(
            "YooKassa confirmation URL invalid payment_id=%s",
            payment.id,
        )
        await message.answer(
            "Платёж №{} зарегистрирован, но получить безопасную ссылку на оплату "
            "не удалось. Не создавайте новый платёж; обратитесь к администратору "
            "для сверки.".format(payment.id),
            reply_markup=purchase_menu_keyboard(),
        )
        return
    await message.answer(
        "Платёж №{} создан на сумму {} ₽. Перейдите к оплате, затем нажмите "
        "«Проверить оплату».".format(payment.id, attempt.amount_minor // 100),
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
    logger.info(
        "Lesson payment created telegram_id=%s payment_id=%s package=%s",
        message.from_user.id,
        payment.id,
        attempt.package_key,
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

    payment = await repository.get_lesson_payment(
        payment_id,
        callback.from_user.id,
    )
    if payment is None:
        logger.warning(
            "Lesson payment check failed reason=not_found payment_id=%s actor_id=%s",
            payment_id,
            callback.from_user.id,
        )
        await callback.answer("Платёж не найден.", show_alert=True)
        return
    if payment.status == "succeeded":
        credits = await repository.get_lesson_credits(callback.from_user.id)
        await callback.answer("Оплата уже подтверждена.")
        await callback.message.answer(
            "Платёж уже подтверждён. Остаток занятий: {}.".format(credits)
        )
        return
    if payment.status == "canceled":
        await callback.answer("Платёж отменён.", show_alert=True)
        return
    if payment.status == "refund_pending":
        await callback.answer(
            "Возврат уже обрабатывается. Занятия временно недоступны.",
            show_alert=True,
        )
        return

    try:
        provider_payment = await payment_gateway.get_payment(
            payment.provider_payment_id
        )
    except PaymentProviderError as error:
        logger.error(
            "Failed to check YooKassa payment payment_id=%s error=%s",
            payment.id,
            error,
        )
        await callback.answer(
            "Не удалось проверить платёж. Попробуйте позже.",
            show_alert=True,
        )
        return

    metadata_user_id = provider_payment.metadata.get("telegram_id")
    metadata_package = provider_payment.metadata.get("package_key")
    if (
        provider_payment.payment_id != payment.provider_payment_id
        or provider_payment.amount_minor != payment.amount_minor
        or provider_payment.currency != "RUB"
        or metadata_user_id != str(callback.from_user.id)
        or metadata_package != payment.package_key
    ):
        logger.error("YooKassa payment details mismatch payment_id=%s", payment.id)
        await callback.answer(
            "Данные платежа не совпали. Обратитесь к администратору.",
            show_alert=True,
        )
        return

    if provider_payment.status == "succeeded":
        completed = await repository.complete_lesson_payment(
            payment.id,
            callback.from_user.id,
        )
        if not completed:
            latest_payment = await repository.get_lesson_payment(
                payment.id,
                callback.from_user.id,
            )
            credits = await repository.get_lesson_credits(callback.from_user.id)
            await callback.answer("Статус платежа уже обработан.")
            if latest_payment is not None and latest_payment.status == "succeeded":
                await callback.message.answer(
                    "Платёж уже подтверждён. Остаток занятий: {}.".format(credits)
                )
            else:
                await callback.message.answer(
                    "Статус платежа изменился во время сверки. Проверьте позже "
                    "или обратитесь к администратору."
                )
            return
        credits = await repository.get_lesson_credits(callback.from_user.id)
        await callback.answer("Оплата подтверждена.")
        await callback.message.answer(
            "Оплата подтверждена. На баланс добавлено {} занятий. Остаток: {}.".format(
                payment.lessons, credits
            )
        )
        logger.info("Lesson payment confirmed payment_id=%s", payment.id)
    elif provider_payment.status == "canceled":
        canceled = await repository.cancel_lesson_payment(
            payment.id,
            callback.from_user.id,
        )
        logger.info(
            "Lesson payment canceled payment_id=%s actor_id=%s updated=%s",
            payment.id,
            callback.from_user.id,
            canceled,
        )
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
