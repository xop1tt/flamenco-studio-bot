import logging
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ...runtime.admin_access import get_admin_id
from . import (
    BOOK_CLASS,
    BACK_TO_CLASSES,
    BACK_TO_PURCHASES,
    CANCEL,
    MAIN_MENU,
    booking_input_keyboard,
    class_menu_keyboard,
    lessons_menu_keyboard,
    main_menu_keyboard,
    purchase_menu_keyboard,
    purchase_confirmation_keyboard,
)
from .navigation import cancel_current_action
from .main_menu import ensure_profile
from ...handlers.states import LessonForm
from ...payments import PaymentProviderError, PURCHASE_OPTIONS, YooKassaClient


logger = logging.getLogger("bot.handlers.lessons")
router = Router(name="lessons_keyboard")
CLASS_CHOICES = {
    "Фламенко для начинающих",
    "Продолжающая группа",
    "Индивидуальное занятие",
}
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
async def select_class(message: Message, state: FSMContext) -> None:
    await state.update_data(class_name=message.text)
    await state.set_state(LessonForm.waiting_for_booking_time)
    await message.answer(
        "Напишите удобные дни и время для этого занятия. "
        "Это будет пожелание, а не подтвержденная запись.",
        reply_markup=booking_input_keyboard(),
    )
    logger.info(
        "Selected class telegram_id=%s class_name=%s",
        message.from_user.id if message.from_user else None,
        message.text,
    )


@router.message(F.text.in_(PURCHASE_OPTIONS))
async def select_purchase(
    message: Message,
    state: FSMContext,
) -> None:
    package = PURCHASE_OPTIONS[message.text]
    await state.update_data(package_key=package.key)
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


@router.message(LessonForm.waiting_for_booking_time)
async def submit_booking_request(
    message: Message,
    state: FSMContext,
    repository: Any,
) -> None:
    preferred_time = (message.text or "").strip()
    if not preferred_time or len(preferred_time) > 300:
        logger.warning(
            "Rejected booking request telegram_id=%s reason=invalid_length length=%s",
            message.from_user.id if message.from_user else None,
            len(preferred_time),
        )
        await message.answer("Укажите пожелания по времени (до 300 символов).")
        return
    if message.from_user is None:
        raise ValueError("У сообщения отсутствует Telegram-пользователь")

    form_data = await state.get_data()
    class_name = form_data.get("class_name", "Занятие фламенко")
    await ensure_profile(message, repository)
    request = await repository.create_lesson_request(
        telegram_id=message.from_user.id,
        kind="booking",
        details="{}; пожелания по времени: {}".format(class_name, preferred_time),
    )
    await state.clear()
    await message.answer(
        "Заявка №{} сохранена. Запись пока не подтверждена: администратору "
        "нужно проверить заявку и подтвердить свободное время.".format(request.id),
        reply_markup=lessons_menu_keyboard(),
    )
    logger.info(
        "Booking request submitted telegram_id=%s request_id=%s",
        message.from_user.id,
        request.id,
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
        (
            item
            for item in PURCHASE_OPTIONS.values()
            if item.key == package_key
        ),
        None,
    )
    if package is None:
        logger.error(
            "Purchase package missing telegram_id=%s package_key=%s",
            message.from_user.id,
            package_key,
        )
        await state.clear()
        await message.answer(
            "Не удалось определить выбранный вариант. Выберите пакет заново.",
            reply_markup=purchase_menu_keyboard(),
        )
        return

    if (
        not payment_gateway.is_configured
        or not getattr(repository, "supports_durable_payments", False)
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

    await ensure_profile(message, repository)
    try:
        provider_payment = await payment_gateway.create_payment(
            amount_minor=package.price_rub * 100,
            description="Фламенко: {}".format(package.title),
            telegram_id=message.from_user.id,
            package_key=package.key,
        )
    except PaymentProviderError as error:
        await state.clear()
        logger.error(
            "Failed to create YooKassa payment telegram_id=%s error=%s",
            message.from_user.id,
            error,
        )
        await message.answer(
            "Не удалось создать платёж. Попробуйте позже или обратитесь "
            "к администратору.",
            reply_markup=purchase_menu_keyboard(),
        )
        return

    if not provider_payment.confirmation_url or not provider_payment.confirmation_url.startswith(
        "https://"
    ):
        raise PaymentProviderError(
            "ЮKassa вернула некорректную ссылку для подтверждения оплаты"
        )

    payment = await repository.create_lesson_payment(
        telegram_id=message.from_user.id,
        package_key=package.key,
        lessons=package.lessons,
        amount_minor=package.price_rub * 100,
        provider_payment_id=provider_payment.payment_id,
        confirmation_url=provider_payment.confirmation_url,
    )
    await state.clear()
    await message.answer(
        "Платёж №{} создан на сумму {} ₽. Перейдите к оплате, затем нажмите "
        "«Проверить оплату».".format(payment.id, package.price_rub),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Перейти к оплате",
                        url=payment.confirmation_url,
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
        package.key,
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
            logger.warning(
                "Lesson payment already completed payment_id=%s actor_id=%s",
                payment.id,
                callback.from_user.id,
            )
        credits = await repository.get_lesson_credits(callback.from_user.id)
        await callback.answer("Оплата подтверждена.")
        await callback.message.answer(
            "Оплата подтверждена. На баланс добавлено {} занятий. "
            "Остаток: {}.".format(payment.lessons, credits)
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
