#!/usr/bin/env bash
# Установка Python-пакетов
pip install -r requirements.txt

# Установка браузера Chromium и системных зависимостей для него
playwright install chromium
playwright install-deps chromium
