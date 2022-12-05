import logging
import os
import sys
import time

import requests
import telegram
from dotenv import load_dotenv
from http import HTTPStatus

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setStream(sys.stdout)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


def check_tokens():
    """Функция проверяет наличие всех токенов."""
    if not PRACTICUM_TOKEN or not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.critical('Отсутствует один или несколько токенов')
        return False
    return True


def send_message(bot, message):
    """Функция отправляет сообщение в Telegram."""
    try:
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message
        )
    except Exception as error:
        logger.error(f'Ошибка при отправке сообщения Telegram - {error}')
    else:
        logger.debug('Сообщение успешно отправленно в Telegram')


def get_api_answer(timestamp):
    """Функция делает запрос к API и возвращает ответ в виде объекта Python."""
    try:
        response = requests.get(
            url=ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp}
        )
    except requests.RequestException as error:
        logging.error(f'Ошибка при запросе к основному API: {error}')
    if response.status_code != HTTPStatus.OK:
        raise ConnectionError
    response = response.json()
    if not isinstance(response, dict):
        raise TypeError
    return response


def check_response(response):
    """Функция принимет словарь на вход и проверяет его содержимое."""
    response_fields = [
        'id',
        'status',
        'homework_name',
        'reviewer_comment',
        'date_updated',
        'lesson_name',
    ]
    if not isinstance(response, dict):
        raise TypeError
    homework_list = response.get('homeworks')
    if not isinstance(homework_list, list):
        raise TypeError
    if len(homework_list) < 1:
        return None
    for homework in homework_list:
        for field in response_fields:
            if not homework.get(field):
                logging.error(
                    f'В ответе API отсутствует ожидаемый ключ - {field}'
                )
    return homework_list


def parse_status(homework):
    """
    Функция принимает на вход домашнюю работу.
    Проверяет изменение статуса и возвращает строку.
    """
    status = homework.get('status')
    if status is None:
        raise TypeError
    if status not in HOMEWORK_VERDICTS:
        raise TypeError
    homework_name = homework.get('homework_name')
    if homework_name is None:
        raise TypeError
    verdict = HOMEWORK_VERDICTS.get(status)
    if verdict is None:
        logging.error(f'Неожиданный статус домашней работы - {status}')
        return None
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        sys.exit()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time()) - RETRY_PERIOD
    previous_message: str = ''
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                message = parse_status(homeworks[0])
            else:
                message = previous_message
                logger.debug('Нет изменений')
            if message != previous_message:
                send_message(bot, message)
                previous_message = message
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if message != previous_message:
                send_message(bot, message)
                previous_message = message
        finally:
            timestamp += RETRY_PERIOD
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
