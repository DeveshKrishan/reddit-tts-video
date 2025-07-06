import logging
import time


class UtcFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        ct = time.gmtime(record.created)
        if datefmt:
            s = time.strftime(datefmt, ct)
        else:
            s = time.strftime("%Y-%m-%d %H:%M:%S", ct)
        return s + " UTC"


handler = logging.StreamHandler()
formatter = UtcFormatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.handlers = [handler]
logger.propagate = False
