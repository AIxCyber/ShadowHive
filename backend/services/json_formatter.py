import json
import logging


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            data["exception"] = self.formatException(record.exc_info)
        task_id = getattr(record, "task_id", None)
        if task_id:
            data["task_id"] = task_id
        request_id = getattr(record, "request_id", None)
        if request_id:
            data["request_id"] = request_id
        return json.dumps(data, default=str)
