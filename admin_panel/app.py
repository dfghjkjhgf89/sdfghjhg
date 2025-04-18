import os
import sys
import logging
from functools import wraps
# Ensure the project root is in the path *before* other imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import asyncio
from config import DATABASE_URL, ADMIN_USERNAME, ADMIN_PASSWORD, BOT_TOKEN, TBANK_SECRET_KEY, ADMIN_TG_ACCOUNT
from models import User, Subscription, Whitelist, SessionLocal, init_db, Referral, Admin, StopCommand, Payment, PaymentStatus
from aiogram import Bot
from flask_sqlalchemy import SQLAlchemy

# Настройка логирования
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load .env from project root
load_dotenv(os.path.join(project_root, '.env'))

# Initialize database before creating app
try:
    init_db()
    logger.info("База данных успешно инициализирована")
except Exception as e:
    logger.error(f"Ошибка при инициализации базы данных: {e}")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Initialize bot instance
try:
    bot = Bot(token=BOT_TOKEN)
    logger.info("Бот успешно инициализирован")
except Exception as e:
    logger.error(f"Ошибка при инициализации бота: {e}")
    bot = None

# Создаем московскую временную зону (UTC+3)
MSK = timezone(timedelta(hours=3))

# Добавляем константу для тестовой длительности
SUBSCRIPTION_DURATION = timedelta(minutes=10)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            logger.debug(f"Доступ к {f.__name__} запрещен: пользователь не вошел")
            return redirect(url_for('login'))
        logger.debug(f"Доступ к {f.__name__} разрешен")
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    logger.debug("Перенаправление с / на /users")
    return redirect(url_for('users'))

@app.route('/toggle_user_active/<int:user_id>', methods=['POST'])
def toggle_user_active(user_id):
    try:
        # Получаем сессию базы данных; способ может отличаться в зависимости от вашего проекта.
        with get_db() as db:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                flash("Пользователь не найден.", "error")
            else:
                user.is_active = not user.is_active
                db.commit()
                flash("Статус пользователя изменён.", "success")
    except Exception as e:
        app.logger.error(f"Ошибка при переключении статуса пользователя {user_id}: {e}")
        flash("Ошибка при изменении статуса пользователя.", "error")
    return redirect(url_for('users'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == ADMIN_USERNAME and check_password_hash(generate_password_hash(ADMIN_PASSWORD), password):
            session['logged_in'] = True
            return redirect(url_for('users'))
        else:
            flash('Неверные учетные данные', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/users')
@login_required
def users():
    logger.debug("Запрос к /users")
    try:
        db = next(get_db())
        logger.debug("Получен доступ к БД для /users")
        
        # Получаем всех пользователей и их статусы автоплатежей
        users_data = []
        users = db.query(User).all()
        now = datetime.now(MSK)
        
        for user in users:
            stop_command = db.query(StopCommand).filter(StopCommand.telegram_id == user.telegram_id).first()
            user_data = {
                'user': user,
                'autopayment_enabled': not bool(stop_command),
                'active_subscription': None,
                'subscription_end': None
            }
            
            # Получаем активную подписку
            active_sub = db.query(Subscription).filter(
                Subscription.user_id == user.id,
                Subscription.end_date > now,
                Subscription.is_active == True
            ).order_by(Subscription.end_date.desc()).first()
            
            if active_sub:
                # Проверяем, есть ли успешный платеж для этой подписки
                payment = db.query(Payment).filter(
                    Payment.subscription_id == active_sub.id,
                    Payment.status == PaymentStatus.COMPLETED
                ).first()
                
                if payment:
                    user_data['active_subscription'] = active_sub
                    # Конвертируем время окончания подписки в московское
                    end_date_utc = active_sub.end_date
                    if end_date_utc.tzinfo is None:
                        end_date_utc = end_date_utc.replace(tzinfo=timezone.utc)
                    user_data['subscription_end'] = end_date_utc.astimezone(MSK)
                    logger.debug(f"Найдена активная подписка для пользователя {user.id}: {active_sub.id}, окончание: {user_data['subscription_end']}")
            
            users_data.append(user_data)

        logger.debug(f"Найдено {len(users)} пользователей")
        return render_template('users.html', users_data=users_data)
    except Exception as e:
        logger.exception("Ошибка при получении списка пользователей:")
        flash(f'Ошибка при получении списка пользователей: {str(e)}', 'error')
        logger.debug("Перенаправление с /users на / из-за ошибки")
        return redirect(url_for('index'))

@app.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    try:
        db = next(get_db())
        user = db.get(User, user_id)
        if not user:
            flash('Пользователь не найден', 'error')
            return redirect(url_for('users'))
        
        if request.method == 'POST':
            user.referral_link_override = request.form.get('referral_link')
            user.referral_status_override = request.form.get('referral_status') == 'true'
            user.is_active = request.form.get('is_active') == 'true'
            db.commit()
            flash('Пользователь успешно обновлен', 'success')
            return redirect(url_for('users'))
        
        return render_template('edit_user.html', user=user)
    except Exception as e:
        flash(f'Ошибка при редактировании пользователя: {str(e)}', 'error')
        return redirect(url_for('users'))

@app.route('/whitelist', methods=['GET', 'POST'])
@login_required
def whitelist():
    try:
        db = next(get_db())
        if request.method == 'POST':
            telegram_id = request.form.get('telegram_id')
            if telegram_id:
                try:
                    telegram_id = int(telegram_id)
                    whitelist_entry = Whitelist(telegram_id=telegram_id)
                    db.add(whitelist_entry)
                    db.commit()
                    flash('Telegram ID успешно добавлен в белый список', 'success')
                except ValueError:
                    flash('Telegram ID должен быть числом', 'error')
                except Exception as e:
                    flash(f'Ошибка при добавлении в белый список: {str(e)}', 'error')
        
        whitelist_entries = db.query(Whitelist).all()
        return render_template('whitelist.html', whitelist_entries=whitelist_entries)
    except Exception as e:
        flash(f'Ошибка при работе с белым списком: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/delete_whitelist/<int:entry_id>')
@login_required
def delete_whitelist(entry_id):
    try:
        db = next(get_db())
        entry = db.get(Whitelist, entry_id)
        if entry:
            db.delete(entry)
            db.commit()
            flash('Запись успешно удалена из белого списка', 'success')
        else:
            flash('Запись не найдена', 'error')
    except Exception as e:
        flash(f'Ошибка при удалении записи: {str(e)}', 'error')
    return redirect(url_for('whitelist'))

@app.route('/subscriptions')
@login_required
def subscriptions():
    try:
        db = next(get_db())
        now = datetime.now()
        today = now.date()
        tomorrow = today + timedelta(days=1)
        
        payments_today = db.query(Subscription).filter(
            Subscription.start_date >= today,
            Subscription.start_date < tomorrow
        ).all()
        
        # Показываем только те, у кого end_date > сейчас
        ending_today = db.query(Subscription).filter(
            Subscription.end_date >= now,
            Subscription.end_date < tomorrow
        ).all()
        
        return render_template('subscriptions.html', 
                             payments_today=payments_today,
                             ending_today=ending_today)
    except Exception as e:
        flash(f'Ошибка при получении информации о подписках: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/broadcast')
@login_required
def broadcast_page():
    try:
        db = next(get_db())
        users = db.query(User).filter(User.telegram_id.isnot(None)).all()
        return render_template('broadcast.html', users=users)
    except Exception as e:
        flash(f'Ошибка при загрузке страницы рассылки: {str(e)}', 'error')
        return redirect(url_for('index'))

# ВНИМАНИЕ: для production рассылку лучше делать через очередь задач (Celery, RQ) или отдельный сервис!
async def send_message_async(user_id, text):
    try:
        logger.debug(f"Попытка отправить сообщение пользователю {user_id}")
        await bot.send_message(user_id, text)
        logger.info(f"Сообщение успешно отправлено пользователю {user_id}")
        return True, None
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения пользователю {user_id}: {e}")
        return False, str(e)

def send_message_sync(user_id, text):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(send_message_async(user_id, text))
        loop.close()
        return result
    except Exception as e:
        logger.error(f"Ошибка при запуске event loop для пользователя {user_id}: {e}")
        return False, str(e)

@app.route('/send_broadcast', methods=['POST'])
@login_required
def send_broadcast():
    if bot is None:
        logger.error("Бот не инициализирован. Рассылка невозможна.")
        flash('Ошибка: Бот не инициализирован.', 'error')
        return redirect(url_for('broadcast_page'))

    try:
        message = request.form.get('message_text')
        broadcast_type = request.form.get('broadcast_type')
        selected_user_form_id = request.form.get('selected_user_id')

        message_log = f"{message[:20]}..." if message else "[пустое сообщение]"
        logger.debug(f"Получен запрос на рассылку: тип={broadcast_type}, выбранный пользователь ID={selected_user_form_id}, сообщение='{message_log}'")

        if not message:
            flash('Введите текст сообщения', 'error')
            return redirect(url_for('broadcast_page'))

        db = next(get_db())
        target_users = []

        if broadcast_type == 'all':
            target_users = db.query(User).filter(User.telegram_id.isnot(None)).all()
            logger.debug(f"Выбраны все пользователи с telegram_id, найдено {len(target_users)}")
        elif broadcast_type == 'selected' and selected_user_form_id:
            try:
                user_id = int(selected_user_form_id)
                user = db.query(User).filter(User.id == user_id, User.telegram_id.isnot(None)).first()
                if user:
                    target_users = [user]
                else:
                    logger.warning(f"Выбранный пользователь с ID {selected_user_form_id} не найден или не имеет telegram_id.")
            except ValueError:
                logger.warning(f"Некорректный ID пользователя: {selected_user_form_id}")
        else:
            # Если не выбран пользователь или не указан тип — всем
            target_users = db.query(User).filter(User.telegram_id.isnot(None)).all()
            logger.debug(f"Выбраны все пользователи с telegram_id, найдено {len(target_users)}")

        if not target_users:
            flash('Нет пользователей для рассылки', 'error')
            return redirect(url_for('broadcast_page'))

        success_count = 0
        error_count = 0
        error_messages = []

        for user in target_users:
            success, error = send_message_sync(user.telegram_id, message)
            if success:
                success_count += 1
            else:
                error_count += 1
                error_messages.append(f"Пользователь {user.id}: {error}")

        if error_count > 0:
            flash(f'Рассылка завершена. Успешно: {success_count}, Ошибок: {error_count}. Подробности: {", ".join(error_messages)}', 'warning')
        else:
            flash(f'Рассылка успешно завершена. Отправлено сообщений: {success_count}', 'success')

        return redirect(url_for('broadcast_page'))

    except Exception as e:
        logger.exception("Ошибка при выполнении рассылки:")
        flash(f'Ошибка при выполнении рассылки: {str(e)}', 'error')
        return redirect(url_for('broadcast_page'))

@app.route('/user/<int:user_id>')
@login_required
def user_details(user_id):
    try:
        db = next(get_db())
        user = db.query(User).get(user_id)
        if not user:
            flash('Пользователь не найден', 'error')
            return redirect(url_for('users'))

        # Получаем активную подписку
        now = datetime.now(MSK)
        active_sub = (db.query(Subscription)
            .join(Payment, Subscription.payments)
            .filter(
                Subscription.user_id == user.id,
                Subscription.end_date > now,
                Subscription.is_active == True,
                Payment.status == PaymentStatus.COMPLETED
            )
            .order_by(Subscription.end_date.desc())
            .first())

        # Получаем историю подписок (только успешно оплаченные)
        subscription_history = (db.query(Subscription)
            .join(Payment, Subscription.payments)
            .filter(
                Subscription.user_id == user.id,
                Payment.status == PaymentStatus.COMPLETED
            )
            .order_by(Subscription.start_date.desc())
            .all())

        # Получаем рефералов через связь referrals_made
        referrals = [ref.referred_user for ref in user.referrals_made]

        # Проверяем статус автоплатежей
        stop_command = db.query(StopCommand).filter(
            StopCommand.telegram_id == user.telegram_id
        ).first()

        logger.debug(f"Active subscription for user {user_id}: {active_sub}")
        logger.debug(f"Subscription history count: {len(subscription_history)}")

        return render_template('user_details.html',
                             user=user,
                             active_subscription=active_sub,
                             subscription_history=subscription_history,
                             referrals=referrals,
                             autopayment_enabled=not bool(stop_command))
    except Exception as e:
        logger.exception(f"Ошибка при получении информации о пользователе {user_id}:")
        flash(f'Ошибка: {str(e)}', 'error')
        return redirect(url_for('users'))

@app.route('/user/<int:user_id>/subscription', methods=['GET', 'POST'])
@login_required
def manage_subscription(user_id):
    try:
        db = next(get_db())
        user = db.query(User).get(user_id)
        if not user:
            flash('Пользователь не найден', 'error')
            return redirect(url_for('users'))

        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'extend':
                days = int(request.form.get('days', 0))
                if days <= 0:
                    flash('Количество дней должно быть положительным числом', 'error')
                    return redirect(url_for('manage_subscription', user_id=user_id))

                now = datetime.now(MSK)
                # Находим текущую активную подписку
                current_sub = db.query(Subscription).filter(
                    Subscription.user_id == user.id,
                    Subscription.end_date > now,
                    Subscription.is_active == True
                ).first()

                if current_sub:
                    # Продлеваем существующую подписку
                    current_sub.end_date = now + SUBSCRIPTION_DURATION
                else:
                    # Создаем новую подписку
                    new_sub = Subscription(
                        user_id=user.id,
                        start_date=now,
                        end_date=now + SUBSCRIPTION_DURATION,
                        is_active=True
                    )
                    db.add(new_sub)

                db.commit()
                flash(f'Подписка успешно продлена на 10 минут', 'success')

            elif action == 'cancel':
                # Отменяем все активные подписки
                active_subs = db.query(Subscription).filter(
                    Subscription.user_id == user.id,
                    Subscription.is_active == True
                ).all()
                for sub in active_subs:
                    sub.is_active = False
                db.commit()
                flash('Все активные подписки отменены', 'success')

            return redirect(url_for('user_details', user_id=user_id))

        # Получаем текущую подписку для отображения
        now = datetime.now(MSK)
        current_sub = db.query(Subscription).filter(
            Subscription.user_id == user.id,
            Subscription.end_date > now,
            Subscription.is_active == True
        ).first()

        return render_template('manage_subscription.html',
                             user=user,
                             current_subscription=current_sub,
                             subscription_duration="10 минут")
    except Exception as e:
        logger.exception(f"Ошибка при управлении подпиской пользователя {user_id}:")
        flash(f'Ошибка: {str(e)}', 'error')
        return redirect(url_for('users'))

@app.route('/send_user_message', methods=['POST'])
@login_required
def send_user_message():
    try:
        user_id = request.form.get('user_id')
        message = request.form.get('message')
        
        if not user_id or not message:
            flash('Необходимо указать ID пользователя и текст сообщения', 'error')
            return redirect(url_for('users'))

        db = next(get_db())
        user = db.query(User).get(user_id)
        if not user or not user.telegram_id:
            flash('Пользователь не найден или не имеет Telegram ID', 'error')
            return redirect(url_for('users'))

        success, error = send_message_sync(user.telegram_id, message)
        if success:
            flash('Сообщение успешно отправлено', 'success')
        else:
            flash(f'Ошибка при отправке сообщения: {error}', 'error')

        return redirect(url_for('users'))
    except Exception as e:
        logger.exception("Ошибка при отправке сообщения:")
        flash(f'Ошибка: {str(e)}', 'error')
        return redirect(url_for('users'))