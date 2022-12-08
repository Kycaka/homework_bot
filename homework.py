import logging
import os
import sys
import time
from http import HTTPStatus

import json
import requests
import telegram
from dotenv import load_dotenv

from exceptions import (
    GetAPICustomError,
    SendMessageCustomError,
    ParseStatusError,
    JsonError,
)

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
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def send_message(bot, message):
    """Функция отправляет сообщение в Telegram."""
    try:
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message
        )
    except telegram.error.TelegramError:
        logger.error('Ошибка при отправке сообщения Telegram')
        raise SendMessageCustomError
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
    except requests.RequestException:
        logging.error('Ошибка при запросе к основному API')
        raise GetAPICustomError
    if response.status_code != HTTPStatus.OK:
        raise ConnectionError
    try:
        response = response.json()
    except json.JSONDecodeError:
        logger.error('Ответ от API не был преобзаван в json')
        raise JsonError
    if not isinstance(response, dict):
        raise TypeError
    return response


def check_response(response):
    """Функция принимет словарь на вход и проверяет его содержимое."""
    RESPONSE_FIELDS = (
        'id',
        'status',
        'homework_name',
        'reviewer_comment',
        'date_updated',
        'lesson_name',
    )
    if not isinstance(response, dict):
        raise TypeError
    homework_list = response.get('homeworks')
    if not isinstance(homework_list, list):
        raise TypeError
    for homework in homework_list:
        for field in RESPONSE_FIELDS:
            if not homework.get(field):
                logging.error(
                    f'В ответе API отсутствует ожидаемый ключ - {field}'
                )
# Здесь после исправления ошибки всегда вылезает ошибка из pytest
# "Убедитесь, что при корректном ответе API
# функция `check_response` не вызывает исключений."
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
        raise ParseStatusError
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logger.critical('Отсутствует один или несколько токенов')
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
        except ParseStatusError:
            logging.error('Неожиданный статус домашней работы')
        except Exception as error:
            logger.error(f'Сбой в работе программы: {error}')
        finally:
            timestamp += RETRY_PERIOD
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
