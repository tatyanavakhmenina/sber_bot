import os
from dotenv import load_dotenv
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from transformers import pipeline
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from labor_code_data import labor_code
from functools import lru_cache

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Инициализация модели для генерации ответов
summarizer = pipeline("summarization", model="google/pegasus-xsum")

class LaborCodeSearch:
    def __init__(self, labor_code_data):
        self.labor_code = labor_code_data
        self.vectorizer = TfidfVectorizer()
        self._create_index()
    
    def _create_index(self):
        """Создает TF-IDF индекс для быстрого поиска"""
        texts = list(self.labor_code.values())
        self.tfidf_matrix = self.vectorizer.fit_transform(texts)
        self.article_numbers = list(self.labor_code.keys())
    
    def search(self, query: str, top_k: int = 3) -> list:
        """Ищет релевантные статьи по запросу"""
        query_vector = self.vectorizer.transform([query])
        similarities = cosine_similarity(query_vector, self.tfidf_matrix)[0]
        
        # Получаем топ-k результатов
        top_indices = similarities.argsort()[-top_k:][::-1]
        
        results = []
        for idx in top_indices:
            if similarities[idx] > 0.1:  # Порог релевантности
                article_number = self.article_numbers[idx]
                results.append((article_number, self.labor_code[article_number], similarities[idx]))
        
        return results

# Создаем глобальный экземпляр поисковика
searcher = LaborCodeSearch(labor_code)

@lru_cache(maxsize=1000)
def cached_search(query: str) -> list:
    """Кэширует результаты поиска для частых запросов"""
    return searcher.search(query)

def preprocess_text(text: str) -> str:
    """Предобработка текста для улучшения поиска"""
    # Удаляем технические примечания в скобках
    text = re.sub(r'\([^)]*\)', '', text)
    # Удаляем множественные пробелы
    text = re.sub(r'\s+', ' ', text)
    return text.strip().lower()

async def generate_response(query: str, relevant_articles: list) -> str:
    """Генерирует структурированный ответ на основе релевантных статей"""
    if not relevant_articles:
        return "К сожалению, я не нашел подходящих статей по вашему вопросу. Попробуйте переформулировать вопрос."
    
    # Формируем структурированный ответ
    response = "В соответствии с Трудовым кодексом РФ:\n\n"
    
    if "отпуск" in query.lower():
        response += "Чтобы взять ежегодный оплачиваемый отпуск:\n\n"
        response += "1. Подайте письменное заявление работодателю (за 2 недели)\n"
        response += "2. Дождитесь согласования дат отпуска\n"
        response += "3. Получите приказ об отпуске\n\n"
        
        response += "Важная информация:\n"
        for num, text, _ in relevant_articles:
            if num == "114":
                response += "- Каждый работник имеет право на ежегодный отпуск с сохранением места работы и среднего заработка\n"
            elif num == "115":
                response += "- Продолжительность отпуска - 28 календарных дней\n"
            elif num == "122":
                response += "- Право на отпуск возникает через 6 месяцев непрерывной работы\n"
            elif num == "123":
                response += "- График отпусков утверждается работодателем с учетом мнения профсоюза\n"
    
    response += "\nПравовое основание:\n"
    for num, text, _ in relevant_articles:
        key_points = extract_key_points(text)
        response += f"Статья {num} ТК РФ: {key_points}\n"
    
    return response

def extract_key_points(text: str) -> str:
    """Извлекает ключевые моменты из текста статьи"""
    # Удаляем технические примечания
    text = re.sub(r'\([^)]*\)', '', text)
    # Берем первое предложение или первые 200 символов
    sentences = text.split('.')
    if sentences:
        return sentences[0].strip() + '.'
    return text[:200].strip() + '...'


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    welcome_text = """
Здравствуйте! Я бот-консультант по трудовому праву РФ. 

Я могу помочь вам разобраться в вопросах:
- оформления отпуска
- трудовых договоров
- рабочего времени
- заработной платы
- и других аспектах трудового законодательства

Просто задайте мне вопрос в свободной форме!
"""
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = """
Как со мной работать:

1. Задавайте вопросы простым языком
2. Можно указывать конкретную статью: "статья 114"
3. Можно задавать уточняющие вопросы

Примеры вопросов:
- Как правильно уволиться?
- Сколько дней отпуска положено?
- Что делать если задерживают зарплату?
"""
    await update.message.reply_text(help_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user_message = preprocess_text(update.message.text)
    
    # Проверка на запрос конкретной статьи
    if "статья" in user_message:
        article_match = re.search(r'статья\s+(\d+)', user_message)
        if article_match:
            article_number = article_match.group(1)
            if article_number in labor_code:
                await update.message.reply_text(f"Статья {article_number} ТК РФ:\n\n{labor_code[article_number]}")
                return
    
    # Поиск релевантных статей с использованием кэширования
    relevant_articles = cached_search(user_message)
    
    # Генерация ответа
    response = await generate_response(user_message, relevant_articles)
    await update.message.reply_text(response)

def main():
    """Запуск бота"""
    if not BOT_TOKEN:
        logger.error("Не найден токен бота. Установите переменную окружения BOT_TOKEN")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()