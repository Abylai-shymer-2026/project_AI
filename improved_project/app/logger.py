import logging

FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(level=level, format=FMT, datefmt=DATEFMT)
    # Make aiogram quieter if needed:
    logging.getLogger("aiogram.event").setLevel(logging.INFO)
    logging.getLogger("aiogram.dispatcher").setLevel(logging.INFO)

