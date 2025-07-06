import json
import logging
import time


class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        return json.dumps(log_record)


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.handlers = [handler]
logger.propagate = False
