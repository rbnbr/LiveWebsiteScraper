import logging


def make_logger(name: str, filename: str, stream: bool = False):
    """
    :returns a logger with the provided name that logs to provided filename and also streams to stderr if set True.
    :param name:
    :param filename:
    :param stream:
    :return:
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(fmt='%(asctime)s %(levelname)-8s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    if filename != "":
        file_handler = logging.FileHandler(filename, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    if stream:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
        
    return logger

