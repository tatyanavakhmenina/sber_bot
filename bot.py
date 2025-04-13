import telebot
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pandas as pd
import numpy as np

# --- Настройки ---
TOKEN = "7845674514:AAHm8FNNqRX26fw6N929iHXqvwVd4LNhWZ0"
GOOGLE_SHEET_NAME = "Данные по продажам магазинов"
CREDENTIALS_FILE = "credentials.json"

bot = telebot.TeleBot(TOKEN)
registered_users = {}
plans_df_global = pd.DataFrame(columns=['ID магазина'] + ["груши", "яблоки", "апельсины", "мандарины", "ананасы"])
sales_df_global = pd.DataFrame(
    columns=['Дата', 'ID магазина'] + ["груши", "яблоки", "апельсины", "мандарины", "ананасы"])
shops_sheet_gspread = None  # Для прямого доступа к листу магазинов через gspread
sales_data_entry = {}
plan_data_entry = {}
products = ["груши", "яблоки", "апельсины", "мандарины", "ананасы"]
products_genitive = ["груш", "яблок", "апельсинов", "мандаринов", "ананасов"]

# --- Аутентификация в Google Sheets ---
scope = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
gc = gspread.authorize(creds)
spreadsheet = gc.open(GOOGLE_SHEET_NAME)
shops_sheet_gspread = spreadsheet.worksheet("Магазины")


# --- Загрузка зарегистрированных пользователей ---
def load_registered_users():
    global registered_users, shops_sheet_gspread
    registered_users = {}
    if shops_sheet_gspread:
        shops_data = shops_sheet_gspread.get_all_values()
        for row in shops_data[1:]:
            if len(row) >= 4 and row[1] and row[2]:
                fio = row[1]
                user_id = int(row[2])
                role = row[3].lower() if len(row) > 3 else None
                shop_id = row[0] if role == 'директор' and len(row) > 0 else None
                registered_users[user_id] = {'fio': fio, 'role': role, 'shop_id': shop_id}


# --- Функции для работы с данными в DataFrame ---

def add_daily_sales(shop_id, sales):
    global sales_df_global
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        shop_id = str(shop_id)  # Преобразуем ID магазина в строку для консистентности

        # Проверяем и преобразуем значения продаж
        sales_int = {}
        for product in products:
            try:
                sales_int[product] = max(0, int(sales.get(product, 0)))
            except (ValueError, TypeError):
                sales_int[product] = 0

        new_row = pd.DataFrame([{'Дата': today, 'ID магазина': shop_id, **sales_int}])
        sales_df_global = pd.concat([sales_df_global, new_row], ignore_index=True)
        print(f"Данные о продажах успешно добавлены для магазина {shop_id}")
    except Exception as e:
        print(f"Ошибка при добавлении данных о продажах: {str(e)}")
        raise


def set_monthly_plan(shop_id, plan):
    global plans_df_global
    try:
        shop_id = str(shop_id).strip()  # Преобразуем ID магазина в строку и убираем пробелы
        if not shop_id:
            raise ValueError("ID магазина не может быть пустым")

        # Проверяем и преобразуем значения плана
        plan_int = {}
        for product in products:
            try:
                value = plan.get(product, 0)
                plan_int[product] = max(0, int(value))
            except (ValueError, TypeError):
                plan_int[product] = 0

        # Удаляем старый план для этого магазина
        plans_df_global = plans_df_global[plans_df_global['ID магазина'] != shop_id]

        # Создаем новую строку с планом
        new_plan = {'ID магазина': shop_id}
        new_plan.update(plan_int)

        # Добавляем новый план
        new_row = pd.DataFrame([new_plan])
        plans_df_global = pd.concat([plans_df_global, new_row], ignore_index=True)

        print(f"План продаж успешно обновлен для магазина {shop_id}")
        print(f"Текущие планы:\n{plans_df_global}")  # Для отладки

    except Exception as e:
        print(f"Ошибка при установке плана продаж: {str(e)}")
        raise


def add_user_to_sheet(fio, user_id, role, shop_id=None):
    global shops_sheet_gspread
    if shops_sheet_gspread:
        shops_sheet_gspread.append_row([shop_id if shop_id else '', fio, user_id, role])
        load_registered_users()  # Обновляем registered_users после добавления пользователя


def has_director_reported_today(shop_id):
    today = datetime.now().strftime("%Y-%m-%d")
    reported = not sales_df_global[
        (sales_df_global['Дата'] == today) & (sales_df_global['ID магазина'] == shop_id)].empty
    return reported


# --- Обработчики команд ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    if user_id in registered_users:
        role = registered_users[user_id]['role']
        shop_id = registered_users[user_id].get('shop_id')
        if role == 'директор':
            bot.reply_to(message,
                         f"Здравствуйте, директор магазина {shop_id}! Доступные команды:\n/report - Внести данные о продажах.")
        elif role == 'торговый представитель':
            bot.reply_to(message,
                         "Здравствуйте, торговый представитель! Доступные команды:\n/set_plan - Установить месячный план продаж.\n/report_all - Просмотреть отчет по всем магазинам.")
    else:
        bot.reply_to(message,
                     "Здравствуйте! Для использования бота вам необходимо зарегистрироваться. Используйте команду /register.")


@bot.message_handler(commands=['register'])
def register_user(message):
    user_id = message.from_user.id
    bot.send_message(message.chat.id, "Пожалуйста, введите ваше ФИО:")
    bot.register_next_step_handler(message, process_fio, user_id)


def process_fio(message, user_id):
    fio = message.text.strip()
    bot.send_message(message.chat.id, "Выберите вашу роль (директор или торговый представитель):")
    bot.register_next_step_handler(message, process_role, user_id, fio)


def process_role(message, user_id, fio):
    role = message.text.strip().lower()
    if role in ['директор', 'торговый представитель']:
        if role == 'директор':
            bot.send_message(message.chat.id, "Введите ID вашего магазина:")
            bot.register_next_step_handler(message, process_shop_id, user_id, fio, role)
        else:
            add_user_to_sheet(fio, user_id, role)
            bot.reply_to(message,
                         "Регистрация прошла успешно. Вы зарегистрированы как торговый представитель.\n\nДля установки плана продаж используйте /set_plan.\nДля просмотра доступных команд используйте /start.")
    else:
        bot.reply_to(message, "Некорректная роль. Пожалуйста, выберите 'директор' или 'торговый представитель'.")
        bot.register_next_step_handler(message, process_role, user_id, fio)


def process_shop_id(message, user_id, fio, role):
    shop_id = message.text.strip()
    if shop_id.isdigit():
        add_user_to_sheet(fio, user_id, role, shop_id)
        bot.reply_to(message,
                     f"Регистрация прошла успешно. Вы зарегистрированы как директор магазина {shop_id}.\n\nДля внесения данных о продажах используйте команду /report.")
    else:
        bot.reply_to(message, "Некорректный ID магазина. Пожалуйста, введите числовой ID.")
        bot.register_next_step_handler(message, process_shop_id, user_id, fio, role)


@bot.message_handler(commands=['set_plan'])
def set_plan_command(message):
    user_id = message.from_user.id
    if user_id in registered_users and registered_users[user_id]['role'] == 'торговый представитель':
        bot.send_message(message.chat.id, "Пожалуйста, введите ID магазина для установки плана:")
        bot.register_next_step_handler(message, process_plan_shop_id_new)
    else:
        bot.reply_to(message, "У вас нет прав для выполнения этой команды.")


def process_plan_shop_id_new(message):
    user_id = message.from_user.id
    shop_id = message.text.strip()
    if shop_id.isdigit():
        plan_data_entry[user_id] = {'shop_id': shop_id, 'plan': {}}
        bot.send_message(message.chat.id, f"Пожалуйста, введите план продаж для {products_genitive[0]} (шт.):")
        bot.register_next_step_handler(message, process_plan_step_new, 0)
    else:
        bot.reply_to(message, "Некорректный ID магазина. Пожалуйста, введите числовой ID.")
        bot.register_next_step_handler(message, process_plan_shop_id_new)


def process_plan_step_new(message, product_index):
    user_id = message.from_user.id
    if user_id in plan_data_entry:
        try:
            quantity = int(message.text)
            if quantity >= 0:
                if 'plan' not in plan_data_entry[user_id]:
                    plan_data_entry[user_id]['plan'] = {}

                plan_data_entry[user_id]['plan'][products[product_index]] = quantity

                if product_index < len(products) - 1:
                    bot.send_message(message.chat.id,
                                     f"Введите план продаж для {products_genitive[product_index + 1]} (шт.):")
                    bot.register_next_step_handler(message, process_plan_step_new, product_index + 1)
                else:
                    shop_id = plan_data_entry[user_id]['shop_id']
                    plan_data = plan_data_entry[user_id]['plan']

                    try:
                        set_monthly_plan(shop_id, plan_data)
                        bot.send_message(message.chat.id,
                                         f"План продаж на месяц успешно установлен для магазина {shop_id}!\n\nДоступные команды:\n/set_plan - Установить месячный план продаж\n/report_all - Просмотреть отчет по всем магазинам")
                    except Exception as e:
                        bot.send_message(message.chat.id,
                                         f"Ошибка при установке плана: {str(e)}")
                    finally:
                        del plan_data_entry[user_id]
            else:
                bot.reply_to(message, "Пожалуйста, введите неотрицательное число.")
                bot.register_next_step_handler(message, process_plan_step_new, product_index)
        except ValueError:
            bot.reply_to(message, "Пожалуйста, введите корректное числовое значение.")
            bot.register_next_step_handler(message, process_plan_step_new, product_index)
    else:
        bot.reply_to(message,
                     "Произошла ошибка. Пожалуйста, начните процесс установки плана заново с команды /set_plan")


@bot.message_handler(commands=['report'])
def report_sales(message):
    user_id = message.from_user.id
    if user_id in registered_users and registered_users[user_id]['role'] == 'директор':
        shop_id = registered_users[user_id]['shop_id']
        if not has_director_reported_today(shop_id):
            sales_data_entry[user_id] = {'shop_id': shop_id, 'sales': {}}
            bot.send_message(message.chat.id, f"Введите количество проданных {products_genitive[0]}:")
            bot.register_next_step_handler(message, process_sales_step_new, 0)
        else:
            bot.reply_to(message, "Вы уже вносили данные о продажах сегодня.")
    else:
        bot.reply_to(message, "У вас нет прав для выполнения этой команды или вы не зарегистрированы как директор.")


def process_sales_step_new(message, product_index):
    user_id = message.from_user.id
    if user_id in sales_data_entry:
        try:
            quantity = int(message.text)
            if quantity >= 0:
                sales_data_entry[user_id]['sales'][products[product_index]] = quantity
                if product_index < len(products) - 1:
                    bot.send_message(message.chat.id,
                                     f"Введите количество проданных {products_genitive[product_index + 1]}:")
                    bot.register_next_step_handler(message, process_sales_step_new, product_index + 1)
                else:
                    shop_id = sales_data_entry[user_id]['shop_id']
                    sales_data = sales_data_entry[user_id]['sales']
                    add_daily_sales(shop_id, sales_data)
                    bot.send_message(message.chat.id,
                                     "Данные о продажах успешно внесены!\n\nДоступные команды:\n/report - Внести данные о продажах")
                    del sales_data_entry[user_id]
            else:
                bot.reply_to(message, "Пожалуйста, введите неотрицательное число.")
                bot.register_next_step_handler(message, process_sales_step_new, product_index)
        except ValueError:
            bot.reply_to(message, "Пожалуйста, введите корректное числовое значение.")
            bot.register_next_step_handler(message, process_sales_step_new, product_index)
    else:
        bot.reply_to(message, "Произошла ошибка. Пожалуйста, начните процесс внесения данных заново с команды /report")


@bot.message_handler(commands=['report_all'])
def view_all_reports(message):
    user_id = message.from_user.id
    if user_id in registered_users and registered_users[user_id]['role'] == 'торговый представитель':
        try:
            today = datetime.now().strftime("%Y-%m-%d")

            # Проверяем наличие планов
            if plans_df_global.empty:
                bot.send_message(message.chat.id, "Нет установленных планов продаж.")
                return

            report_text = f"Отчет о выполнении плана продаж за {today}:\n\n"

            # Перебираем все уникальные магазины из планов
            for shop_id in plans_df_global['ID магазина'].unique():
                # Получаем план для текущего магазина
                shop_plan = plans_df_global[plans_df_global['ID магазина'] == shop_id].iloc[-1]

                # Получаем продажи за сегодня
                shop_sales = sales_df_global[
                    (sales_df_global['Дата'] == today) &
                    (sales_df_global['ID магазина'] == shop_id)
                    ]

                report_text += f"Магазин ID {shop_id}\n"

                # Получаем продажи за сегодня, если они есть
                today_sales = shop_sales.iloc[-1] if not shop_sales.empty else None

                # Формируем отчет по каждому продукту
                for product in products:
                    try:
                        plan_qty = int(shop_plan[product])
                        sold_qty = int(today_sales[product]) if today_sales is not None else 0

                        if plan_qty > 0:
                            percentage = (sold_qty / plan_qty) * 100
                            report_text += f"{product.capitalize()}: {sold_qty}/{plan_qty} ({percentage:.1f}%)\n"
                        else:
                            report_text += f"{product.capitalize()}: {sold_qty}/0 (-)\n"
                    except (ValueError, TypeError, KeyError) as e:
                        print(f"Ошибка при расчете показателей для магазина {shop_id}, продукт {product}: {str(e)}")
                        report_text += f"{product.capitalize()}: Ошибка расчета\n"

                report_text += "\n"

            if len(report_text.strip()) <= len(f"Отчет о выполнении плана продаж за {today}:\n\n"):
                bot.send_message(message.chat.id, "Нет данных для отображения.")
                return

            # Разбиваем длинное сообщение на части
            max_message_length = 4096
            for i in range(0, len(report_text), max_message_length):
                bot.send_message(message.chat.id, report_text[i:i + max_message_length])

        except Exception as e:
            error_message = f"Произошла ошибка при формировании отчета: {str(e)}"
            print(error_message)
            bot.reply_to(message, "Произошла ошибка при формировании отчета. Пожалуйста, попробуйте позже.")
    else:
        bot.reply_to(message,
                     "У вас нет прав для выполнения этой команды или вы не зарегистрированы как торговый представитель.")


# --- Запуск бота ---
if __name__ == '__main__':
    load_registered_users()
    print("Бот запущен...")
    bot.polling(none_stop=True)