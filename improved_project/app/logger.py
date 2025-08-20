# app/logger.py
import logging
import sys


def setup_logging(level: int = logging.DEBUG) -> None:
    """
    Настраивает детальное логирование для отладки.
    """
    # Устанавливаем формат для всех сообщений
    log_format = "%(asctime)s - %(levelname)-8s - %(name)-20s - %(message)s"

    # Создаем обработчик, который выводит логи в консоль
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(level)
    stream_handler.setFormatter(logging.Formatter(log_format))

    # Получаем корневой логгер и настраиваем его
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Удаляем все предыдущие обработчики, чтобы избежать дублирования
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Добавляем наш новый, настроенный обработчик
    root_logger.addHandler(stream_handler)

    # Делаем логгер aiogram менее "шумным", чтобы видеть главное
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("openai").setLevel(logging.INFO)

    logging.info("Логирование настроено на уровень DEBUG.")