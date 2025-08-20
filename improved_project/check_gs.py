import os
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

# Сначала загружаем переменные из .env файла
load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]

# Теперь os.getenv() найдет нужную переменную
sa_file = os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE")
sheet_id = os.getenv("GOOGLE_SHEET_ID")

# Проверка, что переменные загрузились
if not sa_file or not sheet_id:
    print("Ошибка: Переменные GOOGLE_SHEETS_CREDENTIALS_FILE или GOOGLE_SHEET_ID не найдены в .env файле.")
else:
    try:
        cred = Credentials.from_service_account_file(sa_file, scopes=SCOPES)
        client = gspread.authorize(cred)
        sh = client.open_by_key(sheet_id)
        print(f"Успешное подключение! Имя таблицы: '{sh.title}'")
    except FileNotFoundError:
        print(f"Ошибка: Файл с ключами не найден по пути, указанному в .env: '{sa_file}'")
    except Exception as e:
        print(f"Произошла ошибка при подключении: {e}")