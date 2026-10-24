import os
import re
import time
from flask import Flask, request, render_template_string, jsonify
import telebot

TELEGRAM_TOKEN = "8634501513:AAH68W9fsXOQRgWTV58ko44r9yL-A2JFn0A"
HOST_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://ps4-bot.onrender.com")

app = Flask(__name__)
bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
active_stream = {"kp_id": None, "timestamp": 0}

@app.route('/')
def index():
    if time.time() - active_stream['timestamp'] > 7200 or not active_stream['kp_id']:
        return "<h1 style='color:white; background:black; text-align:center; padding-top:20%; height:100vh; margin:0;'>Жду ссылку на Кинопоиск в Telegram.</h1>"
    
    html = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>PS4 Stream</title>
        <style>
            body, html { width: 100%; height: 100%; background: #000; margin: 0; overflow: hidden; }
            iframe { width: 100vw; height: 100vh; border: none; }
        </style>
    </head>
    <body>
        <iframe src="https://kinodivbox.github.io/iframe?id={{ kp_id }}" allowfullscreen></iframe>
        
        <script>
            // Сохраняем текущий ID (если его нет, строка будет пустой)
            let currentKp = '{{ kp_id or "" }}';
            
            setInterval(async () => {
                try {
                    const res = await fetch('/api/status');
                    const data = await res.json();
                    const newKp = data.kp_id || "";
                    
                    // Если ID изменился (в том числе если он стал пустым после /stop), перезагружаем страницу
                    if (newKp !== currentKp) { window.location.reload(); }
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

# 1. КОМАНДА /start
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    text = (
        "Привет! Я бот для трансляции фильмов на PS4.\n\n"
        "Отправь мне ссылку на фильм с Кинопоиска (или его ID).\n\n"
        "Доступные команды:\n"
        "/stop — принудительно остановить видео и очистить экран PS4."
    )
    bot.reply_to(message, text)

# 2. КОМАНДА /stop (Должна быть ДО обработчика ссылок)
@bot.message_handler(commands=['stop', 'clear'])
def stop_stream(message):
    active_stream['kp_id'] = None
    active_stream['timestamp'] = 0
    bot.reply_to(message, "🛑 Воспроизведение остановлено. Экран PS4 вернется в режим ожидания.")

# 3. ОБРАБОТЧИК ССЫЛОК И ТЕКСТА
@bot.message_handler(func=lambda msg: True)
def handle_link(message):
    text = message.text
    match = re.search(r'film/.*?(\d+)', text) or re.search(r'series/.*?(\d+)', text)
    kp_id = match.group(1) if match else (text if text.isdigit() else None)

    if kp_id:
        active_stream['kp_id'] = kp_id
        active_stream['timestamp'] = time.time()
        bot.reply_to(message, f"✅ Готово! Плеер на PS4 обновится автоматически.\n👉 {HOST_URL}")
    else:
        bot.reply_to(message, "Не удалось найти ID. Отправьте ссылку с Кинопоиска (например: https://www.kinopoisk.ru/film/326/).")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
