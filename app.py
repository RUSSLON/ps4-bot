import os
import re
import time
from flask import Flask, request, render_template_string, jsonify
import telebot

TELEGRAM_TOKEN = "8634501513:AAH68W9fsXOQRgWTV58ko44r9yL-A2JFn0A"
# Render автоматически подставит ваш домен
HOST_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://russlon.onrender.com")

app = Flask(__name__)
bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)

active_stream = {"kp_id": None, "timestamp": 0}

# ==========================================
# 1. ПЛЕЕР ДЛЯ PS4 (ИНТЕГРАЦИЯ KINOBOX)
# ==========================================
@app.route('/')
def index():
    # Держим ссылку активной 2 часа (7200 секунд)
    if time.time() - active_stream['timestamp'] > 7200 or not active_stream['kp_id']:
        return "<h1 style='color:white; background:black; text-align:center; padding-top:20%; height:100vh; margin:0;'>Жду ссылку на Кинопоиск в Telegram.</h1>"
    
    html = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>PS4 Kinobox Stream</title>
        <style>
            body, html { width: 100%; height: 100%; background: #000; margin: 0; overflow: hidden; }
            .kinobox_div { width: 100vw; height: 100vh; }
        </style>
    </head>
    <body>
        <div class="kinobox_div"></div>
        <script src="https://kinobox.tv/kinobox.min.js"></script>
        <script>
            // Инициализация плеера с ID Кинопоиска
            new Kinobox('.kinobox_div', {
                search: { kinopoisk: '{{ kp_id }}' },
                players: ['Rezka', 'VideoCDN', 'Kodik', 'Alloha', 'Hdvb']
            }).init();

            // Автообновление страницы, если в Telegram прислали новый фильм
            let currentKp = '{{ kp_id }}';
            setInterval(async () => {
                try {
                    const res = await fetch('/api/status');
                    const data = await res.json();
                    if (data.kp_id && data.kp_id !== currentKp) {
                        window.location.reload();
                    }
                } catch (e) {}
            }, 3000);
        </script>
    </body>
    </html>
    """
    return render_template_string(html, kp_id=active_stream['kp_id'])

@app.route('/api/status')
def status():
    return jsonify(active_stream)

# ==========================================
# 2. ТЕЛЕГРАМ БОТ
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
    return f"Webhook настроен на: {HOST_URL}"

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Отправь мне ссылку на фильм с Кинопоиска (или просто его числовой ID).")

@bot.message_handler(func=lambda msg: True)
def handle_link(message):
    text = message.text
    
    # Регулярное выражение для извлечения цифр из ссылки Кинопоиска
    match = re.search(r'film/.*?(\d+)', text) or re.search(r'series/.*?(\d+)', text)
    kp_id = match.group(1) if match else None
    
    # Если пользователь прислал просто цифры (ID)
    if not kp_id and text.isdigit():
        kp_id = text

    if kp_id:
        active_stream['kp_id'] = kp_id
        active_stream['timestamp'] = time.time()
        bot.reply_to(message, f"✅ Фильм/Сериал найден!\n\nЕсли плеер на PS4 уже открыт, он обновится автоматически.\nИли откройте: 👉 {HOST_URL}")
    else:
        bot.reply_to(message, "Не удалось найти ID. Отправьте ссылку вида: https://www.kinopoisk.ru/film/326/")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
