import os
from flask import Flask, request, render_template_string
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from HdRezkaApi import HdRezkaApi
import time

# Токен берем напрямую
TELEGRAM_TOKEN = "8634501513:AAH68W9fsXOQRgWTV58ko44r9yL-A2JFn0A"
# Render сам подставит ваш адрес сайта сюда!
HOST_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://ваш-сайт.onrender.com")

app = Flask(__name__)
bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)

active_stream = {"url": None, "timestamp": 0}
user_streams_cache = {}

# ==========================================
# 1. ПЛЕЕР ДЛЯ PS4
# ==========================================
@app.route('/')
def index():
    if time.time() - active_stream['timestamp'] > 600 or not active_stream['url']:
        return "<h1 style='color:white; background:black; text-align:center; padding-top:20%; height:100vh; margin:0;'>Нет активного видео. Отправьте ссылку боту.</h1>"
    
    html = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>PS4 Stream</title>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; user-select: none; }
            body, html { width: 100%; height: 100%; background: #000; overflow: hidden; font-family: Arial, sans-serif; }
            #video-container { position: relative; width: 100vw; height: 100vh; display: flex; align-items: center; justify-content: center; }
            video { width: 100%; height: 100%; object-fit: contain; }
            .controls {
                position: absolute; bottom: 0; left: 0; right: 0;
                background: linear-gradient(transparent, rgba(0,0,0,0.85));
                padding: 20px 30px; display: flex; flex-direction: column; gap: 12px;
                transition: opacity 0.4s ease; opacity: 1;
            }
            .controls.hidden { opacity: 0; pointer-events: none; }
            .progress-bar-container { display: flex; align-items: center; gap: 15px; }
            .seekbar { flex: 1; height: 8px; cursor: pointer; accent-color: #0070d1; }
            .time-display { color: #fff; font-size: 16px; min-width: 110px; text-align: right; }
            .buttons { display: flex; align-items: center; justify-content: center; gap: 20px; }
            .btn { background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.3); color: #fff; padding: 10px 20px; border-radius: 6px; font-size: 18px; cursor: pointer; }
            .btn:hover { background: #0070d1; border-color: #0070d1; }
        </style>
    </head>
    <body>
        <div id="video-container">
            <video id="player" src="{{ video_url }}" autoplay></video>
            <div id="controls" class="controls">
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
            const player = document.getElementById('player'); const controls = document.getElementById('controls'); const seekbar = document.getElementById('seekbar'); const timeLabel = document.getElementById('time'); const playBtn = document.getElementById('playBtn');
            let hideTimeout = null; let isSeeking = false;
            function resetHideTimer() { controls.classList.remove('hidden'); clearTimeout(hideTimeout); hideTimeout = setTimeout(() => { if (!player.paused) controls.classList.add('hidden'); }, 3000); }
            ['mousemove', 'keydown', 'touchstart', 'click'].forEach(evt => document.addEventListener(evt, resetHideTimer));
            function fmtTime(s) { if (isNaN(s)) return "00:00"; const m = Math.floor(s / 60); const sec = Math.floor(s % 60); return (m < 10 ? '0' : '') + m + ':' + (sec < 10 ? '0' : '') + sec; }
            player.addEventListener('timeupdate', () => { if (!isSeeking && player.duration) { seekbar.value = (player.currentTime / player.duration) * 100; timeLabel.textContent = fmtTime(player.currentTime) + ' / ' + fmtTime(player.duration); } });
            seekbar.addEventListener('mousedown', () => isSeeking = true); seekbar.addEventListener('mouseup', () => { if (player.duration) player.currentTime = (seekbar.value / 100) * player.duration; isSeeking = false; }); seekbar.addEventListener('change', () => { if (player.duration) player.currentTime = (seekbar.value / 100) * player.duration; isSeeking = false; });
            function togglePlay() { if (player.paused) { player.play(); playBtn.textContent = 'Пауза'; } else { player.pause(); playBtn.textContent = 'Старт'; } }
            function skip(sec) { player.currentTime += sec; }
            function toggleFullscreen() { if (!document.fullscreenElement) document.documentElement.requestFullscreen(); else if (document.exitFullscreen) document.exitFullscreen(); }
        </script>
    </body>
    </html>
    """
    return render_template_string(html, video_url=active_stream['url'])

# ==========================================
# 2. TELEGRAM WEBHOOK И БОТ
# ==========================================
@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return 'OK', 200

@app.route('/set_webhook')
def set_webhook():
    bot.remove_webhook()
    bot.set_webhook(url=f"{HOST_URL}/{TELEGRAM_TOKEN}")
    return f"Webhook настроен на адрес: {HOST_URL}"

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Отправь мне ссылку на HDrezka.")

@bot.message_handler(func=lambda msg: 'rezka' in msg.text.lower())
def handle_rezka_link(message):
    msg_wait = bot.reply_to(message, "Парсинг ссылки...")
    try:
        rezka = HdRezkaApi(message.text.strip())
        streams = rezka.getStream()
        video_data = streams.videos if hasattr(streams, 'videos') else streams
        
        if not isinstance(video_data, dict):
            bot.edit_message_text("Ошибка извлечения.", chat_id=message.chat.id, message_id=msg_wait.message_id)
            return

        user_streams_cache[message.chat.id] = video_data
        markup = InlineKeyboardMarkup()
        for quality in video_data.keys():
            markup.add(InlineKeyboardButton(text=quality, callback_data=f"q_{quality}"))
        bot.edit_message_text("Выберите качество:", chat_id=message.chat.id, message_id=msg_wait.message_id, reply_markup=markup)
    except Exception as e:
        bot.edit_message_text(f"Ошибка: {str(e)}", chat_id=message.chat.id, message_id=msg_wait.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('q_'))
def quality_selected(call):
    quality = call.data.replace('q_', '')
    chat_id = call.message.chat.id

    if chat_id in user_streams_cache and quality in user_streams_cache[chat_id]:
        active_stream['url'] = user_streams_cache[chat_id][quality]
        active_stream['timestamp'] = time.time()
        
        bot.answer_callback_query(call.id, "Ссылка готова!")
        bot.edit_message_text(
            f"✅ Поток **{quality}** готов!\n\nОткройте в браузере PS4:\n👉 {HOST_URL}", 
            chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown"
        )
    else:
        bot.answer_callback_query(call.id, "Сессия устарела.")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)