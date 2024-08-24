import logging


class UpdateLogger(logging.Logger):
    def __init__(self):
        super().__init__(__name__, logging.INFO)
        self.log_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(filename)s -   %(message)s"
        )
        # 设置屏幕打印的格式
        sh = logging.StreamHandler()
        sh.setFormatter(self.log_formatter)
        self.addHandler(sh)

    def set_log_file(self, log_file, mode="w"):
        fh = logging.FileHandler(log_file, encoding="utf8", mode=mode)
        fh.setFormatter(self.log_formatter)
        self.addHandler(fh)

    def set_log_level(self, log_level):
        self.setLevel(log_level)


# default logger for the project
logger = UpdateLogger()
