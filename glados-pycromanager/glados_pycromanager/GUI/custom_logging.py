import logging
from pathlib import Path

def _add_stream_handler(logger: logging.Logger):

    stream_handler = logging.StreamHandler()
    formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.INFO)

    logger.addHandler(stream_handler)

    return logger


def _add_file_handler(logger: logging.Logger, log_path: Path):

    file_handler = logging.FileHandler(log_path, mode='w')
    formatter = logging.Formatter(
        fmt='%(asctime)s %(name)-12s %(levelname)-8s %(message)s', datefmt='%m-%d %H:%M')

    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    logger.addHandler(file_handler)

    return logger


def create_logger(root_dir: Path, caller: str) -> logging.Logger:

    log_path = root_dir / 'logs' / f'{caller}.log'
    logger = logging.getLogger(caller)
    root = logging.getLogger()

    logger.setLevel(logging.INFO)

    # If haven't already launched handlers...
    if not len(logger.handlers):

        _add_file_handler(logger=logger, log_path=log_path)
        _add_stream_handler(logger=logger)

        logger.info('Logging started.')

    # Delete the Qtconsole stderr handler
    # ... as it automatically logs both DEBUG & INFO to stderr
    if root.handlers:
        root.handlers = []

    return logger


def log_dataframe(df, logger: logging.Logger, name: str = "DataFrame") -> None:

    logger.debug(
        f'''{name} head:\n {df.head()}\n----------\n''')


def log_dataframes(*args, logger: logging.Logger) -> None:

    for gdf in args:

        logger.debug(
            f'''DataFrame head:\n {gdf.head()}\n----------\n''')
