import os
import time
import requests
from threading import Thread
from flask import Flask, request, render_template_string, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from HdRezkaApi import HdRezkaApi
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

TELEGRAM_TOKEN = "8634501513:AAH68W9fsXOQRgWTV58ko44r9yL-A2JFn0A"
HOST_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://ps4-bot.onrender.com")

app = Flask(__name__)
bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)

# Глобальные состояния
active_stream = {"url": "", "status": "stop"}
user_cache = {}
anubis_auth = {"cookies": {}, "ua": ""}

# --- ХАК: ПЕРЕДАЧА COOKIES ИЗ PLAYWRIGHT В HDREZKA API ---
old_request = requests.Session.request
def new_request(self, method, url, **kwargs):
    if anubis_auth["cookies"]:
        kwargs.setdefault('cookies', {}).update(anubis_auth["cookies"])
    if anubis_auth["ua"]:
        kwargs.setdefault('headers', {}).update({'User-Agent': anubis_auth["ua"]})
    return old_request(self, method, url, **kwargs)
requests.Session.request = new_request
# ---------------------------------------------------------

def solve_anubis(url):
    """Открывает скрытый браузер для прохождения защиты Anubis"""
    with sync_playwright() as p:
        # Аргументы для экономии ОЗУ на слабом сервере Render
        browser = p.chromium.launch(
            headless=True, 
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        context = browser.new_context()
        page = context.new_page()
        stealth_sync(page)
        
        page.goto(url)
        time.sleep(8) # Ждем, пока отработает JS-защита Anubis
        
        cookies = context.cookies()
        ua = page.evaluate("navigator.userAgent")
        browser.close()
        
        return {c['name']: c['value'] for c in cookies}, ua

# ==========================================
# 1. ЧИСТЫЙ ПЛЕЕР ДЛЯ PS4
# ==========================================
@app.route('/')
def index():
    html = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>PS4 Pure Player</title>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; user-select: none; }
            body, html { width: 100%; height: 100%; background: #000; overflow: hidden; font-family: Arial, sans-serif; }
            #video-container { position: relative; width: 100vw; height: 100vh; display: flex; align-items: center; justify-content: center; }
            video { width: 100%; height: 100%; object-fit: contain; }
            .controls { position: absolute; bottom: 0; left: 0; right: 0; background: linear-gradient(transparent, rgba(0,0,0,0.85)); padding: 20px 30px; display: flex; flex-direction: column; gap: 12px; transition: opacity 0.4s ease; opacity: 1; }
            .controls.hidden { opacity: 0; pointer-events: none; }
            .progress-bar-container { display: flex; align-items: center; gap: 15px; }
            .seekbar { flex: 1; height: 8px; cursor: pointer; accent-color: #0070d1; }
            .time-display { color: #fff; font-size: 16px; min-width: 110px; text-align: right; }
            .buttons { display: flex; align-items: center; justify-content: center; gap: 20px; }
            .btn { background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.3); color: #fff; padding: 10px 20px; border-radius: 6px; font-size: 18px; cursor: pointer; }
            .btn:hover { background: #0070d1; border-color: #0070d1; }
            #status-overlay { position: absolute; color: #fff; font-size: 24px; background: rgba(0,0,0,0.7); padding: 15px 30px; border-radius: 10px; text-align: center;}
        </style>
    </head>
    <body>
        <div id="video-container">
            <div id="status-overlay">Готов к работе.<br>Жду ссылку из Telegram...</div>
            <video id="player" autoplay></video>
            <div id="controls" class="controls hidden">
                <div class="progress-bar-container">
                    <input type="range" id="seekbar" class="seekbar" value="0" min="0" max="100" step="0.1">
                    <span id="time" class="time-display">00:00 / 00:00</span>
                </div>
                <div class="buttons">
                    <button class="btn" onclick="skip(-10)">-10s</button>
                    <button class="btn" id="playBtn" onclick="togglePlay()">Пауза</button>
                    <button class="btn" onclick="skip(10)">+10s</button>
                    <button class="btn" onclick="toggleFullscreen()">На весь экран</button>
                </div>
            </div>
        </div>
        <script>
            const player = document.getElementById('player'); const controls = document.getElementById('controls'); const seekbar = document.getElementById('seekbar'); const timeLabel = document.getElementById('time'); const playBtn = document.getElementById('playBtn'); const statusOverlay = document.getElementById('status-overlay');
            let currentUrl = ''; let hideTimeout = null; let isSeeking = false;
            
            function resetHideTimer() { controls.classList.remove('hidden'); clearTimeout(hideTimeout); hideTimeout = setTimeout(() => { if (!player.paused) controls.classList.add('hidden'); }, 3000); }
            ['mousemove', 'keydown', 'touchstart', 'click'].forEach(evt => document.addEventListener(evt, resetHideTimer));
            
            function fmtTime(s) { if (isNaN(s)) return "00:00"; const m = Math.floor(s / 60); const sec = Math.floor(s % 60); return (m < 10 ? '0' : '') + m + ':' + (sec < 10 ? '0' : '') + sec; }
            player.addEventListener('timeupdate', () => { if (!isSeeking && player.duration) { seekbar.value = (player.currentTime / player.duration) * 100; timeLabel.textContent = fmtTime(player.currentTime) + ' / ' + fmtTime(player.duration); } });
            
            seekbar.addEventListener('mousedown', () => isSeeking = true); 
            seekbar.addEventListener('mouseup', () => { if (player.duration) player.currentTime = (seekbar.value / 100) * player.duration; isSeeking = false; }); 
            seekbar.addEventListener('change', () => { if (player.duration) player.currentTime = (seekbar.value / 100) * player.duration; isSeeking = false; });
            
            function togglePlay() { if (player.paused) { player.play(); playBtn.textContent = 'Пауза'; } else { player.pause(); playBtn.textContent = 'Старт'; } }
            function skip(sec) { player.currentTime += sec; }
            function toggleFullscreen() { if (!document.fullscreenElement) document.documentElement.requestFullscreen(); else if (document.exitFullscreen) document.exitFullscreen(); }
            
            setInterval(async () => {
                try {
                    const res = await fetch('/api/status'); const data = await res.json();
                    
                    if (data.url === "stop") {
                        player.pause(); player.removeAttribute('src'); player.load();
                        statusOverlay.style.display = 'block'; controls.classList.add('hidden'); currentUrl = '';
                    } else if (data.url && data.url !== currentUrl) {
                        currentUrl = data.url; player.src = currentUrl; player.play();
                        statusOverlay.style.display = 'none'; playBtn.textContent = 'Пауза'; resetHideTimer();
                    }
                } catch (e) {}
            }, 1500);
        </script>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/api/status')
def status():
    return jsonify(active_stream)

# ==========================================
# 2. TELEGRAM BOT
# ==========================================
@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    # Запускаем обработку в фоновом потоке, чтобы Telegram не прервал долгий запрос Anubis
    Thread(target=bot.process_new_updates, args=([update],)).start()
    return 'OK', 200

@app.route('/set_webhook')
def set_webhook():
    bot.remove_webhook()
    bot.set_webhook(url=f"{HOST_URL}/{TELEGRAM_TOKEN}")
    return f"Webhook настроен на: {HOST_URL}"

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "Отправьте мне ссылку на фильм с сайта HDrezka.\nКоманда /stop очистит экран PS4.")

@bot.message_handler(commands=['stop', 'clear'])
def stop_video(message):
    active_stream['url'] = "stop"
    bot.reply_to(message, "🛑 Видео на PS4 остановлено.")

@bot.message_handler(func=lambda msg: 'rezka' in msg.text.lower())
def handle_link(message):
    url = message.text.strip()
    msg_wait = bot.reply_to(message, "🕵️‍♂️ Прохожу защиту Anubis (это займет 8-10 секунд)...")
    
    try:
        # 1. Получаем пропуска с помощью невидимого браузера
        cookies, ua = solve_anubis(url)
        anubis_auth["cookies"] = cookies
        anubis_auth["ua"] = ua
        
        # 2. Инициализируем парсер с уже подсунутыми пропусками
        rezka = HdRezkaApi(url)
        translations = rezka.translations
        user_cache[message.chat.id] = {'rezka_obj': rezka}

        markup = InlineKeyboardMarkup()
        if translations:
            for name, tr_id in list(translations.items())[:15]:
                markup.add(InlineKeyboardButton(text=name, callback_data=f"tr_{tr_id}"))
            bot.edit_message_text("🎙 Выберите озвучку:", chat_id=message.chat.id, message_id=msg_wait.message_id, reply_markup=markup)
        else:
            markup.add(InlineKeyboardButton(text="Продолжить", callback_data="tr_default"))
            bot.edit_message_text("Озвучка одна по умолчанию. Нажмите продолжить:", chat_id=message.chat.id, message_id=msg_wait.message_id, reply_markup=markup)

    except Exception as e:
        bot.edit_message_text(f"Не удалось пройти Anubis. Ошибка: {str(e)}", chat_id=message.chat.id, message_id=msg_wait.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('tr_'))
def handle_translation(call):
    tr_id = call.data.replace('tr_', '')
    chat_id = call.message.chat.id
    
    if chat_id not in user_cache:
        bot.answer_callback_query(call.id, "Сессия устарела.")
        return
    
    bot.edit_message_text("Получаю ссылки на видео...", chat_id=chat_id, message_id=call.message.message_id)
    rezka = user_cache[chat_id]['rezka_obj']
    tr_id = None if tr_id == 'default' else tr_id

    try:
        if rezka.type == 'tv_series':
            stream = rezka.getStream(season=1, episode=1, translation_id=tr_id)
            bot.send_message(chat_id, "Внимание: включена 1 серия 1 сезона.")
        else:
            stream = rezka.getStream(translation_id=tr_id)
        
        videos = stream.videos
        user_cache[chat_id]['videos'] = videos
        
        markup = InlineKeyboardMarkup()
        for quality in videos.keys():
            markup.add(InlineKeyboardButton(text=quality, callback_data=f"q_{quality}"))
            
        bot.edit_message_text("📺 Выберите качество:", chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup)
    except Exception as e:
        bot.edit_message_text(f"Ошибка получения качества: {str(e)}", chat_id=chat_id, message_id=call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('q_'))
def handle_quality(call):
    quality = call.data.replace('q_', '')
    chat_id = call.message.chat.id

    if chat_id in user_cache and 'videos' in user_cache[chat_id]:
        direct_url = user_cache[chat_id]['videos'][quality]
        active_stream['url'] = direct_url
        bot.answer_callback_query(call.id, "Отправлено на PS4!")
        bot.edit_message_text(f"✅ Видео отправлено на PS4!\nКачество: {quality}", chat_id=chat_id, message_id=call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "Сессия устарела.")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
