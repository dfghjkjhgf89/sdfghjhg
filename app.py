from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from models import User, Subscription, Payment, Referral, Admin, Whitelist, StopCommand, PaymentStatus, SubscriptionType
from config import ADMIN_USERNAME, ADMIN_PASSWORD, ADMIN_EMAIL, JWT_SECRET_KEY
import jwt
from functools import wraps
from sqlalchemy import desc, func
from database import get_db

app = Flask(__name__)
app.config['SECRET_KEY'] = JWT_SECRET_KEY
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class AdminUser(UserMixin):
    pass

@login_manager.user_loader
def load_user(user_id):
    with get_db() as db:
        admin = db.query(Admin).filter_by(id=int(user_id)).first()
        if admin:
            user = AdminUser()
            user.id = admin.id
            return user
    return None

def init_admin():
    with get_db() as db:
        admin = db.query(Admin).filter_by(username=ADMIN_USERNAME).first()
        if not admin:
            admin = Admin(
                username=ADMIN_USERNAME,
                password_hash=generate_password_hash(ADMIN_PASSWORD),
                email=ADMIN_EMAIL
            )
            db.add(admin)
            db.commit()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        with get_db() as db:
            admin = db.query(Admin).filter_by(username=username).first()
            
            if admin and check_password_hash(admin.password_hash, password):
                user = AdminUser()
                user.id = admin.id
                login_user(user)
                admin.last_login = datetime.utcnow()
                db.commit()
                return redirect(url_for('index'))
            
        flash('Неверное имя пользователя или пароль')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    with get_db() as db:
        users = db.query(User).order_by(desc(User.registration_date)).all()
        active_subs = db.query(func.count(Subscription.id)).filter_by(is_active=True).scalar()
        total_users = db.query(func.count(User.id)).scalar()
        active_users = db.query(func.count(User.id)).filter_by(is_active=True).scalar()
        total_revenue = db.query(func.sum(Payment.amount)).filter_by(status=PaymentStatus.COMPLETED).scalar() or 0
        
        stats = {
            'active_subscriptions': active_subs,
            'total_users': total_users,
            'active_users': active_users,
            'total_revenue': total_revenue
        }
        
        return render_template('index.html', users=users, stats=stats)

@app.route('/user/<int:user_id>')
@login_required
def user_details(user_id):
    with get_db() as db:
        user = db.query(User).filter_by(id=user_id).first()
        if not user:
            flash('Пользователь не найден')
            return redirect(url_for('index'))
        
        active_sub = db.query(Subscription).filter_by(
            user_id=user.id, 
            is_active=True
        ).order_by(desc(Subscription.start_date)).first()
        
        sub_history = db.query(Subscription).filter_by(
            user_id=user.id
        ).order_by(desc(Subscription.start_date)).all()
        
        payments = db.query(Payment).filter_by(
            user_id=user.id
        ).order_by(desc(Payment.created_at)).all()
        
        referrals = [ref.referred for ref in user.referrals_made]
        
        return render_template(
            'user_details.html',
            user=user,
            active_subscription=active_sub,
            subscription_history=sub_history,
            payments=payments,
            referrals=referrals
        )

@app.route('/api/user/<int:user_id>/toggle_status', methods=['POST'])
@login_required
def toggle_user_status(user_id):
    with get_db() as db:
        user = db.query(User).filter_by(id=user_id).first()
        if user:
            user.is_active = not user.is_active
            db.commit()
            return jsonify({'status': 'success', 'is_active': user.is_active})
    return jsonify({'status': 'error', 'message': 'Пользователь не найден'}), 404

@app.route('/api/subscription/<int:sub_id>/cancel', methods=['POST'])
@login_required
def cancel_subscription(sub_id):
    with get_db() as db:
        sub = db.query(Subscription).filter_by(id=sub_id).first()
        if sub:
            sub.is_active = False
            sub.is_auto_renewal = False
            db.commit()
            return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': 'Подписка не найдена'}), 404

@app.route('/api/user/<int:user_id>/add_subscription', methods=['POST'])
@login_required
def add_subscription(user_id):
    data = request.json
    sub_type = data.get('subscription_type')
    duration_days = data.get('duration', 30)
    
    with get_db() as db:
        user = db.query(User).filter_by(id=user_id).first()
        if not user:
            return jsonify({'status': 'error', 'message': 'Пользователь не найден'}), 404
        
        # Деактивируем текущую активную подписку
        current_sub = db.query(Subscription).filter_by(
            user_id=user_id,
            is_active=True
        ).first()
        
        if current_sub:
            current_sub.is_active = False
            current_sub.is_auto_renewal = False
        
        # Создаем новую подписку
        new_sub = Subscription(
            user_id=user_id,
            subscription_type=SubscriptionType[sub_type],
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=duration_days),
            is_active=True,
            is_auto_renewal=data.get('auto_renewal', False)
        )
        
        db.add(new_sub)
        db.commit()
        
        return jsonify({
            'status': 'success',
            'subscription': {
                'id': new_sub.id,
                'type': new_sub.subscription_type.value,
                'start_date': new_sub.start_date.isoformat(),
                'end_date': new_sub.end_date.isoformat()
            }
        })

@app.route('/api/stats')
@login_required
def get_stats():
    with get_db() as db:
        total_users = db.query(func.count(User.id)).scalar()
        active_users = db.query(func.count(User.id)).filter_by(is_active=True).scalar()
        total_subs = db.query(func.count(Subscription.id)).scalar()
        active_subs = db.query(func.count(Subscription.id)).filter_by(is_active=True).scalar()
        total_revenue = db.query(func.sum(Payment.amount)).filter_by(status=PaymentStatus.COMPLETED).scalar() or 0
        
        # Статистика по типам подписок
        sub_types = db.query(
            Subscription.subscription_type,
            func.count(Subscription.id)
        ).group_by(Subscription.subscription_type).all()
        
        sub_stats = {str(t.value): c for t, c in sub_types}
        
        return jsonify({
            'total_users': total_users,
            'active_users': active_users,
            'total_subscriptions': total_subs,
            'active_subscriptions': active_subs,
            'total_revenue': total_revenue,
            'subscription_types': sub_stats
        })

if __name__ == '__main__':
    init_admin()
    app.run(debug=True, port=8000) 