import asyncio
import logging
import re
import datetime
from functools import wraps
import aiohttp
import uuid
import hashlib
import json
from sqlalchemy import and_

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from config import (
    BOT_TOKEN,
    DEFAULT_REFERRAL_STATUS,
    ADMIN_TG_ACCOUNT,
    BOT_USERNAME,
    COMPANY_NAME,
    COMPANY_REGISTRATION_NUMBER,
    COMPANY_ADDRESS,
    COMPANY_BANK,
    COMPANY_ACCOUNT,
    COMPANY_SWIFT,
    COMPANY_IBAN,
    TBANK_SHOP_ID,
    TBANK_SECRET_KEY
)
from database import init_db, get_db
from models import User, Subscription, Whitelist, StopCommand, Payment, PaymentStatus, PaymentMethod, TariffPlan, SubscriptionType

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)

SUBSCRIPTION_DURATION = datetime.timedelta(minutes=10)  # Тестовая длительность - 10 минут

class RegistrationStates(StatesGroup):
    waiting_for_email = State()

main_inline_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="👤 Мой аккаунт", callback_data="my_account")],
        [InlineKeyboardButton(text="🔗 Ваша реферальная ссылка", callback_data="ref_link")],
        [InlineKeyboardButton(text="📊 Статус реф. ссылки", callback_data="ref_status")],
        [InlineKeyboardButton(text="⏳ Моя подписка", callback_data="my_subscription")],
        [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")]
    ]
)

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👤 Мой аккаунт"), KeyboardButton(text="🔗 Ваша реферальная ссылка")],
        [KeyboardButton(text="📊 Статус реф. ссылки"), KeyboardButton(text="⏳ Моя подписка")],
        [KeyboardButton(text="🆘 Поддержка")],
    ],
    resize_keyboard=True
)

def is_valid_email(email: str) -> bool:
    return "@" in email and "." in email

def check_registered_active(func):
    @wraps(func)
    async def wrapper(message_or_cq: types.Message | types.CallbackQuery, state: FSMContext | None = None, *args, **kwargs):
        if isinstance(message_or_cq, types.Message):
            user_tg = message_or_cq.from_user
            target_message = message_or_cq
        elif isinstance(message_or_cq, types.CallbackQuery):
            user_tg = message_or_cq.from_user
            target_message = message_or_cq.message
            await message_or_cq.answer()
        else:
            logger.error(f"check_registered_active applied to unsupported type: {type(message_or_cq)}")
            return

        telegram_id = user_tg.id
        user_db: User | None = None

        with get_db() as db:
            user_db = db.query(User).filter(User.telegram_id == telegram_id).first()

            if not user_db or not user_db.email or user_db.email.startswith("temp_") or not user_db.is_active:
                logger.warning(f"Access denied for {telegram_id} by check_registered_active: Not registered, no email, or inactive.")
                await target_message.answer("Пожалуйста, пройдите регистрацию (или убедитесь, что ваш аккаунт активен), используя /start.")
                if state and (not user_db or not user_db.email or user_db.email.startswith("temp_")):
                    logger.info(f"Redirecting user {telegram_id} to email input.")
                    if not user_db:
                        await state.update_data(new_telegram_id=telegram_id, new_username=user_tg.username)
                    else:
                        await state.update_data(user_id_to_update=user_db.id)
                    await target_message.answer("Пожалуйста, введите ваш email:", reply_markup=ReplyKeyboardRemove())
                    await state.set_state(RegistrationStates.waiting_for_email)
                return

            kwargs['user'] = user_db
            return await func(message_or_cq, *args, **kwargs)

    return wrapper

def check_access(handler):
    @wraps(handler)
    async def wrapper(message_or_cq: types.Message | types.CallbackQuery, state: FSMContext | None = None, *args, **kwargs):
        if isinstance(message_or_cq, types.Message):
            user_tg = message_or_cq.from_user
            target_message = message_or_cq
        elif isinstance(message_or_cq, types.CallbackQuery):
            user_tg = message_or_cq.from_user
            target_message = message_or_cq.message
            await message_or_cq.answer()
        else:
            logger.error(f"check_access applied to unsupported type: {type(message_or_cq)}")
            return
        
        telegram_id = user_tg.id
        user_db: User | None = None
        access_granted = False
        now = datetime.datetime.now(datetime.timezone.utc)

        with get_db() as db:
            user_db = db.query(User).filter(User.telegram_id == telegram_id).first()

            if not user_db or not user_db.email or user_db.email.startswith("temp_") or not user_db.is_active:
                logger.warning(f"Access denied for {telegram_id} by check_access: Not registered, no email, or inactive.")
                await target_message.answer("Пожалуйста, пройдите регистрацию (или убедитесь, что ваш аккаунт активен), используя /start.")
                if state and (not user_db or not user_db.email or user_db.email.startswith("temp_")):
                     logger.info(f"Redirecting user {telegram_id} to email input.")
                     if not user_db:
                         await state.update_data(new_telegram_id=telegram_id, new_username=user_tg.username)
                     else:
                         await state.update_data(user_id_to_update=user_db.id)
                     await target_message.answer("Пожалуйста, введите ваш email:", reply_markup=ReplyKeyboardRemove())
                     await state.set_state(RegistrationStates.waiting_for_email)
                return

            logger.debug(f"Checking whitelist for telegram_id: {telegram_id} (type: {type(telegram_id)})")
            whitelist_entry = db.query(Whitelist).filter(Whitelist.telegram_id == telegram_id).first()
            logger.debug(f"Whitelist query result for {telegram_id}: {whitelist_entry}")
            is_whitelisted = whitelist_entry is not None
            if is_whitelisted:
                logger.info(f"Access granted for {telegram_id}: Whitelisted.")
                access_granted = True
            else:
                active_subscription = (db.query(Subscription)
                                       .filter(Subscription.user_id == user_db.id)
                                       .filter(Subscription.end_date > now)
                                       .filter(Subscription.is_active == True)
                                       .order_by(Subscription.end_date.desc())
                                       .first())
                if active_subscription:
                    logger.info(f"Access granted for {telegram_id}: Active subscription until {active_subscription.end_date}.")
                    access_granted = True

            if access_granted:
                kwargs['user'] = user_db
                return await handler(message_or_cq, *args, **kwargs)
            else:
                logger.warning(f"Access denied for {telegram_id}: No active subscription or whitelist entry.")
                await target_message.answer("❌ У вас нет активного доступа к курсу.")
                return

    return wrapper

@dp.message(CommandStart())
async def handle_start(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    logger.info(f"User {telegram_id} ({username}) started the bot.")

    start_param = message.text.split()[1] if len(message.text.split()) > 1 else None
    
    if start_param:
        if start_param == "offer":
            await message.answer(
                "📄 Публичная оферта доступна по ссылке:\n"
                "https://docs.google.com/document/d/1tgPqQTkjQDgftj-a0vNOgs53mi7-sctjv4WJ2BF9DTA/edit",
                disable_web_page_preview=True
            )
            return
        elif start_param == "privacy":
            await message.answer(
                "🔒 Политика конфиденциальности доступна по ссылке:\n"
                "https://docs.google.com/document/d/10s0vc9sBXMeC8a-_VGSXzCPi0Z5k4AMy/edit",
                disable_web_page_preview=True
            )
            return

    with get_db() as db:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()

        if user:
            logger.info(f"User {telegram_id} already exists.")
            if not user.is_active:
                await message.answer("❌ Ваш аккаунт был деактивирован.")
                return
            if not user.email or user.email.startswith("temp_"):
                logger.info(f"User {telegram_id} needs email. Setting state.")
                await state.update_data(user_id_to_update=user.id)
                await message.answer(
                    f"👋 Здравствуйте, {first_name}! Похоже, ваш email не был указан. \n"
                    "📧 Пожалуйста, введите ваш email для продолжения:",
                    reply_markup=ReplyKeyboardRemove()
                )
                await state.set_state(RegistrationStates.waiting_for_email)
            else:
                await message.answer(f"👋 С возвращением, {first_name}!", reply_markup=main_keyboard)
        else:
            logger.info(f"New user: {telegram_id} ({username}). Requesting email.")
            await state.update_data(
                new_telegram_id=telegram_id,
                new_username=username
            )
            await message.answer(
                f"🎉 Добро пожаловать, {first_name}! \n"
                "📧 Для начала работы, пожалуйста, укажите вашу почту.",
                reply_markup=ReplyKeyboardRemove()
            )
            await state.set_state(RegistrationStates.waiting_for_email)

@dp.message(RegistrationStates.waiting_for_email, F.text)
async def handle_email(message: types.Message, state: FSMContext):
    email = message.text.strip()
    logger.info(f"Received email attempt: {email} from user {message.from_user.id}")

    if not is_valid_email(email):
        await message.answer("❌ Не похоже на email. Пожалуйста, введите корректный адрес электронной почты.")
        return

    with get_db() as db:
        existing_user_by_email = db.query(User).filter(User.email == email).first()
        user_data = await state.get_data()
        user_id_to_update = user_data.get('user_id_to_update')

        if existing_user_by_email and (not user_id_to_update or existing_user_by_email.id != user_id_to_update):
                await message.answer("❌ Этот email уже используется другим пользователем. Пожалуйста, введите другой email.")
                return

        if user_id_to_update:
            user_to_update = db.query(User).filter(User.id == user_id_to_update).first()
            if user_to_update:
                user_to_update.email = email
                db.commit()
                logger.info(f"Email updated for user {user_to_update.telegram_id}.")
                await message.answer("✅ Спасибо! Ваш email обновлен.", reply_markup=main_keyboard)
                await state.clear()
            else:
                logger.error(f"Could not find user with id {user_id_to_update} to update email.")
                await message.answer("❌ Произошла ошибка при обновлении email. Попробуйте /start снова.")
                await state.clear()
        else:
            new_telegram_id = user_data.get('new_telegram_id')
            new_username = user_data.get('new_username')

            if not new_telegram_id:
                 logger.error(f"Missing new_telegram_id in state data for user {message.from_user.id}")
                 await message.answer("❌ Произошла ошибка регистрации. Попробуйте /start снова.")
                 await state.clear()
                 return

            new_user = User(
                telegram_id=new_telegram_id,
                telegram_username=new_username,
                email=email
            )
            db.add(new_user)
            db.commit()
            logger.info(f"New user {new_telegram_id} registered with email {email}.")
            await message.answer("🎉 Спасибо! Вы успешно зарегистрированы.", reply_markup=main_keyboard)
            await state.clear()

@dp.message(RegistrationStates.waiting_for_email)
async def handle_email_incorrect_input(message: types.Message):
    await message.answer("Пожалуйста, введите ваш email текстом.")

@dp.message(F.text == "👤 Мой аккаунт")
@check_registered_active
async def handle_my_account(message: types.Message, *, user: User):
    logger.info(f"User {user.telegram_id} requested account info.")
    
    now = datetime.datetime.now(datetime.timezone.utc)
    access_status_text = "У вас отсутствует доступ к курсу ❌"
    with get_db() as db:
        is_whitelisted = db.query(Whitelist).filter(Whitelist.telegram_id == user.telegram_id).first() is not None
        stop_command = db.query(StopCommand).filter(StopCommand.telegram_id == user.telegram_id).first()
        autopayment_status = "❌ Автоплатежи отключены" if stop_command else "✅ Автоплатежи включены"
        
        if is_whitelisted:
            access_status_text = "✅ Доступ к курсу есть (белый список)"
        else:
            active_subscription = (db.query(Subscription)
                                   .filter(Subscription.user_id == user.id)
                                   .filter(Subscription.end_date > now)
                                   .order_by(Subscription.end_date.desc())
                                   .first())
            if active_subscription:
                end_date_str = active_subscription.end_date.strftime("%d.%m.%Y %H:%M")
                access_status_text = f"✅ Доступ к курсу есть (до {end_date_str} UTC)"

    account_info = (
        f"👤 Ваш аккаунт:\n"
        f"\n🆔 Telegram ID: `{user.telegram_id}`"
        f"\n📧 Email: `{user.email}`"
        f"\n{autopayment_status}"
        f"\n\n{access_status_text}"
    )
    await message.answer(account_info, parse_mode="Markdown")

@dp.message(F.text == "🔗 Ваша реферальная ссылка")
@check_access
async def handle_referral_link(message: types.Message, *, user: User):
    logger.info(f"User {user.telegram_id} requested referral link.")
    
    start_param = user.referral_link_override if user.referral_link_override else user.telegram_id
    
    ref_link = f"https://t.me/{BOT_USERNAME}?start={start_param}"
    
    await message.answer(f"🔗 Ваша реферальная ссылка:\n`{ref_link}`", parse_mode="Markdown")

@dp.message(lambda message: message.text == "/stop")
@check_registered_active
async def handle_stop_command(message: types.Message, *, user: User):
    logger.info(f"User {user.telegram_id} used /stop command")
    
    with get_db() as db:
        existing_stop = db.query(StopCommand).filter(StopCommand.telegram_id == user.telegram_id).first()
        
        if existing_stop:
            await message.answer("❌ У вас уже отключены автоплатежи\nЧтобы возобновить автоплатежи - введите команду /resume")
        else:
            stop_command = StopCommand(
                user_id=user.id,
                telegram_id=user.telegram_id
            )
            db.add(stop_command)
            db.commit()
            await message.answer("Автоплатежи выключены! ❌\nЧтобы возобновить автоплатежи - введите команду /resume")

@dp.message(lambda message: message.text == "/resume")
@check_registered_active
async def handle_resume_command(message: types.Message, *, user: User):
    logger.info(f"User {user.telegram_id} used /resume command")
    
    with get_db() as db:
        existing_stop = db.query(StopCommand).filter(StopCommand.telegram_id == user.telegram_id).first()
        
        if existing_stop:
            db.delete(existing_stop)
            db.commit()
            await message.answer("Автоплатежи были включены ✅\nВ следующем месяце произойдет списание!")
        else:
            await message.answer("✅ У вас уже включены автоплатежи!\nЧтобы выключить автоплатежи - введите команду /stop")

@dp.message(F.text == "📊 Статус реф. ссылки")
@check_access
async def handle_referral_status(message: types.Message, *, user: User):
    logger.info(f"User {user.telegram_id} requested referral status.")
    # По умолчанию неактивна, если админ не включил override
    status_flag = user.referral_status_override
    if status_flag is None:
        status_flag = False  # по умолчанию неактивна

    status_icon = "✅" if status_flag else "❌"
    status_text = "Активна" if status_flag else "Не активна"

    await message.answer(f"📊 Статус вашей реферальной ссылки: {status_icon} ({status_text})")

@dp.message(F.text == "⏳ Моя подписка")
@check_registered_active
async def handle_my_subscription(message: types.Message, *, user: User):
    logger.info(f"User {user.telegram_id} requested subscription status.")
    now = datetime.datetime.now(datetime.timezone.utc)
    
    with get_db() as db:
        # Проверяем активную подписку
        active_subscription = (db.query(Subscription)
                               .filter(Subscription.user_id == user.id)
                               .filter(Subscription.end_date > now)
                               .filter(Subscription.is_active == True)
                               .order_by(Subscription.end_date.desc())
                               .first())
        
        # Добавляем логирование для отладки
        logger.info(f"Active subscription query result: {active_subscription}")
        if active_subscription:
            logger.info(f"Subscription details - End date: {active_subscription.end_date}, Now: {now}")
        
        is_whitelisted = db.query(Whitelist).filter(Whitelist.telegram_id == user.telegram_id).first() is not None
        
        if active_subscription:
            end_date_str = active_subscription.end_date.strftime("%d.%m.%Y %H:%M UTC")
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="buy_access")]
                ]
            )
            await message.answer(
                f"✅ Ваш доступ к обучающему курсу активен до: {end_date_str}\n\n"
                "Для продления подписки нажмите на кнопку ниже:",
                reply_markup=keyboard
            )
        elif is_whitelisted:
            await message.answer(
                "✨ У вас постоянный доступ к курсу (белый список)."
            )
        else:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="💳 Оплатить 1500₽", callback_data="process_payment")]
                ]
            )
            await message.answer(
                "📚 Продукт: Приватный чат \"СИСТЕМНИК УБТ ПРИВАТ\"\n\n"
                "🗓 Тарифный план: СИСТЕМНИК УБТ (Карта РФ)\n\n"
                "💰 Сумма к оплате: 1500 RUB\n\n"
                "✨ После оплаты будет предоставлен доступ:\n\n"
                "📱 Группа «СИСТЕМНИК УБТ ПРИВАТ»\n\n"
                "📋 Оплачивая подписку вы принимаете условия "
                "[Публичной оферты](https://docs.google.com/document/d/1tgPqQTkjQDgftj-a0vNOgs53mi7-sctjv4WJ2BF9DTA/edit) и "
                "[Политики конфиденциальности](https://docs.google.com/document/d/10s0vc9sBXMeC8a-_VGSXzCPi0Z5k4AMy/edit)",
                reply_markup=keyboard,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )

@dp.message(F.text == "🆘 Поддержка")
@check_registered_active
async def handle_support(message: types.Message, *, user: User):
    logger.info(f"User {user.telegram_id} requested support.")
    await message.answer(
        "ℹ️ Если не получается оплатить, читаем:\n\n"
        "⚠️ Бот иногда не справляется с большими наплывами участников. "
        "Пробуйте раз в несколько минут, или через час, в любом случае рано или поздно всё прогрузится!\n\n"
        "📨 Только по долгим проблемам с оплатой — @" + ADMIN_TG_ACCOUNT
    )

@dp.callback_query(F.data == "process_payment")
@check_registered_active
async def handle_process_payment(callback: types.CallbackQuery, *, user: User):
    logger.info("НАЖАТА КНОПКА ОПЛАТИТЬ 1500Р")
    order_id = f"{user.telegram_id}_{int(datetime.datetime.now().timestamp())}"
    amount = 1500  # сумма в рублях
    description = "Подписка на СИСТЕМНИК УБТ ПРИВАТ"
    try:
        pay_url, payment_id = await tbank_create_payment(int(amount), order_id, description, user.email)
        now = datetime.datetime.now(datetime.timezone.utc)
        with get_db() as db:
            # Получаем базовый тариф
            basic_tariff = db.query(TariffPlan).filter(TariffPlan.type == SubscriptionType.BASIC).first()
            if not basic_tariff:
                raise Exception("Базовый тариф не найден")

            # Деактивируем все предыдущие подписки пользователя
            db.query(Subscription).filter(
                Subscription.user_id == user.id,
                Subscription.is_active == True
            ).update({
                'is_active': False,
                'auto_renewal': False,
                'rebill_id': None
            })
            
            # Создаем новую подписку
            new_sub = Subscription(
                user_id=user.id,
                tariff_id=basic_tariff.id,  # Добавляем tariff_id
                start_date=now,
                end_date=now + SUBSCRIPTION_DURATION,
                payment_amount=amount,
                is_active=False
            )
            db.add(new_sub)
            db.flush()

            # Создаем запись о платеже
            new_payment = Payment(
                user_id=user.id,
                subscription_id=new_sub.id,
                external_id=payment_id,  # Исправляем payment_id на external_id
                amount=amount,
                currency='RUB',
                status=PaymentStatus.PENDING,
                payment_method=PaymentMethod.CARD
            )
            db.add(new_payment)
            db.commit()
    except Exception as e:
        logger.error(f"Ошибка при создании платежа: {e}")
        await callback.message.edit_text(f"❌ Ошибка при создании платежа: {e}")
        await callback.answer()
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Перейти к оплате", url=pay_url)],
            [InlineKeyboardButton(text="Проверить оплату", callback_data=f"check_payment_{payment_id}")],
            [InlineKeyboardButton(text="« Назад", callback_data="back")]
        ]
    )
    await callback.message.edit_text(
        f"💳 Для оплаты нажмите кнопку ниже. После оплаты вернитесь и нажмите 'Проверить оплату'.\n\n"
        f"Сумма: {amount}₽\n"
        f"⏳ Длительность подписки: 10 минут (тестовый режим)\n\n"
        "Если возникнут вопросы — обращайтесь в поддержку.",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("check_payment_"))
@check_registered_active
async def handle_check_payment(callback: types.CallbackQuery, *, user: User):
    payment_id = callback.data.replace("check_payment_", "")
    logger.info(f"Checking payment {payment_id} for user {user.telegram_id}")
    
    if not payment_id.isdigit():
        await callback.answer("❌ Некорректный платеж. Попробуйте начать оплату заново.", show_alert=True)
        return

    # Получаем информацию о платеже
    payment_info = await tbank_get_payment_info(payment_id)
    logger.info(f"Payment info received: {payment_info}")
    
    if not payment_info or not payment_info.get("Success"):
        await callback.answer("❌ Ошибка при проверке платежа. Попробуйте позже.", show_alert=True)
        return

    status = payment_info.get("Status", "")
    
    if status == "CONFIRMED":
        now = datetime.datetime.now(datetime.timezone.utc)
        logger.info(f"Payment confirmed at {now}")
        
        with get_db() as db:
            payment = db.query(Payment).filter(
                Payment.external_id == payment_id,
                Payment.user_id == user.id
            ).first()
            
            if not payment:
                logger.error(f"Payment {payment_id} not found in database for user {user.id}")
                await callback.answer("❌ Платеж не найден. Попробуйте начать оплату заново.", show_alert=True)
                return
                
            sub = db.query(Subscription).filter(
                Subscription.id == payment.subscription_id,
                Subscription.user_id == user.id
            ).first()
            
            if sub:
                logger.info(f"Found subscription {sub.id}, updating...")
                sub.is_active = True
                sub.end_date = now + SUBSCRIPTION_DURATION
                sub.auto_renewal = True
                sub.rebill_id = payment_info.get("RebillId")
                sub.last_payment_date = now
                sub.next_payment_date = now + SUBSCRIPTION_DURATION
                sub.payment_amount = payment_info.get("Amount", 1500) / 100
                sub.failed_payments = 0
                
                payment.status = PaymentStatus.COMPLETED
                payment.completed_at = now
                
                db.commit()
                logger.info(f"Subscription {sub.id} updated successfully. End date: {sub.end_date}")

                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="✅ Перейти в канал", url="https://t.me/+vy7Idslu1FQ4MWQy")],
                        [InlineKeyboardButton(text="❌ Отключить автоплатеж", callback_data="disable_autopayment")]
                    ]
                )
                
                end_time = (now + SUBSCRIPTION_DURATION).strftime("%H:%M:%S UTC")
                
                await callback.message.edit_text(
                    "✅ Оплата успешно подтверждена!\n\n"
                    f"⏳ Доступ предоставлен на 10 минут (до {end_time})\n\n"
                    "🔄 Автоплатеж включен. После окончания доступа мы автоматически продлим его еще на 10 минут.\n"
                    "Вы всегда можете отключить автопродление в меню «Моя подписка».\n\n"
                    "📱 Ссылка на канал уже доступна по кнопке ниже:",
                    reply_markup=keyboard
                )
    elif status == "REJECTED" or status == "DEADLINE_EXPIRED" or status == "CANCELED":
        # Платеж отклонен или отменен
        error_message = payment_info.get("Message", "Неизвестная ошибка")
        await callback.message.edit_text(
            f"❌ Оплата не прошла\n\n"
            f"Причина: {error_message}\n\n"
            "Вы можете попробовать оплатить снова:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="💳 Попробовать снова", callback_data="process_payment")],
                    [InlineKeyboardButton(text="« Назад", callback_data="back")]
                ]
            )
        )
    elif status == "NEW" or status == "AUTHORIZED" or status == "PENDING":
        # Платеж в процессе
        await callback.answer(
            "⏳ Платеж обрабатывается, пожалуйста, подождите...\n"
            "Нажмите кнопку проверки через 30 секунд.",
            show_alert=True
        )
    else:
        # Неизвестный статус
        await callback.message.edit_text(
            "❓ Неизвестный статус платежа\n\n"
            "Пожалуйста, попробуйте оплатить снова или обратитесь в поддержку:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="💳 Попробовать снова", callback_data="process_payment")],
                    [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")],
                    [InlineKeyboardButton(text="« Назад", callback_data="back")]
                ]
            )
        )

# Добавляем обработчик для отключения автоплатежа
@dp.callback_query(F.data == "disable_autopayment")
@check_registered_active
async def handle_disable_autopayment(callback: types.CallbackQuery, *, user: User):
    with get_db() as db:
        sub = db.query(Subscription).filter(
            Subscription.user_id == user.id,
            Subscription.is_active == True
        ).first()
        
        if sub and sub.auto_renewal:
            sub.auto_renewal = False
            sub.rebill_id = None
            db.commit()
            await callback.message.edit_text(
                "✅ Автоплатеж успешно отключен.\n"
                "Текущая подписка будет действовать до окончания оплаченного периода.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(text="🔄 Включить автоплатеж", callback_data="enable_autopayment")
                    ]]
                )
            )
        else:
            await callback.answer("❌ Автоплатеж уже отключен", show_alert=True)

# Добавляем обработчик для включения автоплатежа
@dp.callback_query(F.data == "enable_autopayment")
@check_registered_active
async def handle_enable_autopayment(callback: types.CallbackQuery, *, user: User):
    with get_db() as db:
        sub = db.query(Subscription).filter(
            Subscription.user_id == user.id,
            Subscription.is_active == True
        ).first()
        
        if sub and not sub.auto_renewal:
            # Здесь нужно создать новый платеж для получения rebill_id
            await callback.message.edit_text(
                "Для включения автоплатежа необходимо совершить новый платеж.\n"
                "После оплаты автоплатеж будет активирован автоматически.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(text="💳 Оплатить", callback_data="process_payment")
                    ]]
                )
            )
        else:
            await callback.answer("✅ Автоплатеж уже включен", show_alert=True)

@dp.callback_query(F.data == "back")
async def process_back(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("Главное меню:")

def generate_token(params: dict, secret_key: str) -> str:
    params = dict(params)
    params.pop('Token', None)
    params['Password'] = secret_key
    sorted_keys = sorted(params.keys())
    values_str = ''.join(str(params[k]) for k in sorted_keys)
    return hashlib.sha256(values_str.encode('utf-8')).hexdigest()

async def tbank_create_payment(amount: int, order_id: str, description: str, user_email: str) -> tuple[str, str]:
    url = "https://securepay.tinkoff.ru/v2/Init"
    payload = {
        "TerminalKey": TBANK_SHOP_ID,
        "Amount": amount * 100,  # сумма в копейках
        "OrderId": order_id,
        "Description": description,
        "DATA": {
            "Email": user_email
        },
        # Добавляем параметры для рекуррентных платежей
        "Recurrent": "Y",  # Включаем рекуррентные платежи
        "CustomerKey": str(order_id.split('_')[0]),  # Используем telegram_id как CustomerKey
    }
    sign_params = {k: v for k, v in payload.items() if k not in ("Token", "DATA")}
    token = generate_token(sign_params, TBANK_SECRET_KEY)
    payload["Token"] = token
    headers = {"Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            text = await resp.text()
            try:
                data = await resp.json()
            except Exception:
                raise Exception(f"Ошибка создания платежа: {resp.status}, ответ: {text}")
            if data.get("Success"):
                return data["PaymentURL"], str(data["PaymentId"])
            else:
                raise Exception(f"Ошибка создания платежа: {data}")

async def tbank_check_payment(payment_id: str) -> bool:
    url = "https://securepay.tinkoff.ru/v2/GetState"
    payload = {
        "TerminalKey": TBANK_SHOP_ID,
        "PaymentId": payment_id
    }
    token = generate_token(payload, TBANK_SECRET_KEY)
    payload["Token"] = token
    headers = {"Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            text = await resp.text()
            try:
                data = await resp.json()
            except Exception:
                raise Exception(f"Ошибка проверки статуса: {resp.status}, ответ: {text}")
            return data.get('Status') in ('CONFIRMED', 'AUTHORIZED')

async def notify_user(telegram_id: int, message: str):
    """Отправляет уведомление пользователю."""
    try:
        await bot.send_message(telegram_id, message)
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления пользователю {telegram_id}: {e}")

@dp.callback_query()
async def debug_all_callbacks(callback: types.CallbackQuery):
    logger.info(f"DEBUG CALLBACK: {callback.data}")
    await callback.answer()

async def tbank_get_payment_info(payment_id: str) -> dict:
    url = "https://securepay.tinkoff.ru/v2/GetState"
    payload = {
        "TerminalKey": TBANK_SHOP_ID,
        "PaymentId": payment_id
    }
    token = generate_token(payload, TBANK_SECRET_KEY)
    payload["Token"] = token
    headers = {"Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            try:
                return await resp.json()
            except Exception:
                return None

async def notify_upcoming_payment(subscription: Subscription):
    """Отправляет уведомление о предстоящем списании."""
    try:
        message = (
            "ℹ️ Уведомление о предстоящем списании\n\n"
            f"Через 2 минуты будет произведено автоматическое продление подписки.\n"
            f"Сумма к списанию: {subscription.payment_amount}₽\n\n"
            "Чтобы отключить автопродление, используйте команду /stop"
        )
        await bot.send_message(subscription.user.telegram_id, message)
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления о предстоящем списании: {e}")

# Функция для проверки и обработки автоплатежей
async def process_auto_payments():
    """Обработка автоматических платежей для активных подписок."""
    logger.info("Начало обработки автоматических платежей")
    
    now = datetime.datetime.now(datetime.timezone.utc)
    notification_threshold = datetime.timedelta(minutes=2)  # За 2 минуты до списания
    
    with get_db() as db:
        # Получаем подписки для уведомления
        subscriptions_to_notify = db.query(Subscription).filter(
            and_(
                Subscription.auto_renewal == True,
                Subscription.is_active == True,
                Subscription.next_payment_date - notification_threshold <= now,
                Subscription.next_payment_date > now,
                Subscription.notification_sent == False,  # Новое поле
                Subscription.rebill_id.isnot(None)
            )
        ).all()

        # Отправляем уведомления
        for subscription in subscriptions_to_notify:
            await notify_upcoming_payment(subscription)
            subscription.notification_sent = True
            db.commit()

        # Получаем подписки для автоплатежа
        subscriptions = db.query(Subscription).filter(
            and_(
                Subscription.auto_renewal == True,
                Subscription.is_active == True,
                Subscription.next_payment_date <= now,
                Subscription.rebill_id.isnot(None)
            )
        ).all()
        
        for subscription in subscriptions:
            try:
                # Создаем платеж
                order_id = f"auto_{subscription.user.telegram_id}_{int(now.timestamp())}"
                payment = await tbank_create_rebill_payment(
                    rebill_id=subscription.rebill_id,
                    amount=subscription.payment_amount,
                    order_id=order_id,
                    description=f"Автоплатеж за подписку {subscription.id}"
                )
                
                if payment and await tbank_check_payment(payment.get('PaymentId')):
                    # Обновляем даты подписки
                    subscription.end_date = subscription.end_date + SUBSCRIPTION_DURATION
                    subscription.last_payment_date = now
                    subscription.next_payment_date = subscription.end_date - datetime.timedelta(minutes=2)
                    subscription.failed_payments = 0
                    subscription.notification_sent = False  # Сбрасываем флаг уведомления
                    
                    # Создаем запись о платеже
                    new_payment = Payment(
                        user_id=subscription.user_id,
                        subscription_id=subscription.id,
                        external_id=payment.get('PaymentId'),  # Исправляем payment_id на external_id
                        amount=subscription.payment_amount,
                        currency='RUB',
                        status=PaymentStatus.COMPLETED,
                        payment_method=PaymentMethod.CARD,
                        completed_at=now
                    )
                    db.add(new_payment)
                    
                    await notify_user(
                        subscription.user.telegram_id,
                        f"✅ Автоплатеж успешно выполнен\n"
                        f"Сумма: {subscription.payment_amount}₽\n"
                        f"Подписка продлена до: {subscription.end_date.strftime('%d.%m.%Y %H:%M')} UTC"
                    )
                else:
                    subscription.failed_payments += 1
                    
                    if subscription.failed_payments >= 3:
                        subscription.auto_renewal = False
                        subscription.rebill_id = None
                        await notify_user(
                            subscription.user.telegram_id,
                            "❌ Автоплатеж отключен из-за повторных неудач.\n"
                            "Для возобновления подписки, пожалуйста, оплатите её заново."
                        )
                    else:
                        retry_in = 2 ** subscription.failed_payments  # Экспоненциальная задержка
                        subscription.next_payment_date = now + datetime.timedelta(minutes=retry_in)
                        await notify_user(
                            subscription.user.telegram_id,
                            f"⚠️ Автоплатеж не удался (попытка {subscription.failed_payments}/3).\n"
                            f"Следующая попытка через {retry_in} минут."
                        )
                
                db.commit()
                
            except Exception as e:
                logger.error(f"Ошибка при обработке автоплатежа для подписки {subscription.id}: {e}")
                db.rollback()

# Запускаем проверку автоплатежей каждые 10 секунд
async def schedule_auto_payments():
    while True:
        try:
            await process_auto_payments()
        except Exception as e:
            logger.error(f"Ошибка в планировщике автоплатежей: {e}")
        await asyncio.sleep(10)  # Проверяем каждые 10 секунд вместо часа

async def tbank_create_rebill_payment(rebill_id: str, amount: int, order_id: str, description: str) -> bool:
    """Создает рекуррентный платеж через Тинькофф."""
    url = "https://securepay.tinkoff.ru/v2/Init"
    payload = {
        "TerminalKey": TBANK_SHOP_ID,
        "Amount": amount * 100,  # сумма в копейках
        "OrderId": order_id,
        "Description": description,
        "Recurrent": "Y",
        "PaymentMethod": "Recurrent",
        "RebillId": rebill_id
    }
    sign_params = {k: v for k, v in payload.items() if k not in ("Token", "DATA")}
    token = generate_token(sign_params, TBANK_SECRET_KEY)
    payload["Token"] = token
    headers = {"Content-Type": "application/json"}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                data = await resp.json()
                if data.get("Success"):
                    # Проверяем статус платежа
                    payment_id = str(data["PaymentId"])
                    for _ in range(3):  # Пробуем 3 раза
                        await asyncio.sleep(5)  # Ждем 5 секунд
                        payment_info = await tbank_get_payment_info(payment_id)
                        if payment_info and payment_info.get("Status") == "CONFIRMED":
                            return True
                    return False
                return False
    except Exception as e:
        logger.error(f"Ошибка при создании рекуррентного платежа: {e}")
        return False

async def main():
    logger.info("bot.py main() called!")
    logger.info("Initializing database...")
    init_db()
    
    # Создаем базовый тариф, если его нет
    with get_db() as db:
        basic_tariff = db.query(TariffPlan).filter(TariffPlan.type == SubscriptionType.BASIC).first()
        if not basic_tariff:
            basic_tariff = TariffPlan(
                type=SubscriptionType.BASIC,
                name="СИСТЕМНИК УБТ (Карта РФ)",
                description="Приватный чат СИСТЕМНИК УБТ ПРИВАТ",
                price=1500.0,
                duration_days=30,
                is_active=True
            )
            db.add(basic_tariff)
            db.commit()
            logger.info("Basic tariff plan created")
    
    logger.info("Database initialized.")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook deleted successfully")
    except Exception as e:
        logger.error(f"Failed to delete webhook: {e}")

    # Запускаем планировщик автоплатежей
    asyncio.create_task(schedule_auto_payments())
    logger.info("Auto-payments scheduler started")

    logger.info("Starting bot polling...")
    await dp.start_polling(bot)
    logger.info("Polling stopped!")