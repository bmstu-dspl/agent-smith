import os
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')

# Проверка на случай, если токен не найден
if not BOT_TOKEN:
    raise ValueError("TOKEN не найден в .env файле")