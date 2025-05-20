import logging
import sys

DEFAULT_LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Keep track of configured state to avoid issues if setup_logging is called multiple times
_logging_configured = False

class ColorFormatter(logging.Formatter):
    """
    A logging formatter that adds ANSI colors to log levels for console output.
    """
    GREY = "\x1b[38;20m"
    BLUE = "\x1b[34;20m"
    GREEN = "\x1b[32;20m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    BOLD_RED = "\x1b[31;1m"
    RESET = "\x1b[0m"

    # Define LOG_FORMAT directly here as it's used by the class
    BASE_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    FORMATS = {
        logging.DEBUG: GREY + BASE_LOG_FORMAT + RESET,
        logging.INFO: BLUE + BASE_LOG_FORMAT + RESET,
        logging.WARNING: YELLOW + BASE_LOG_FORMAT + RESET,
        logging.ERROR: RED + BASE_LOG_FORMAT + RESET,
        logging.CRITICAL: BOLD_RED + BASE_LOG_FORMAT + RESET,
    }

    def __init__(self, fmt=BASE_LOG_FORMAT, datefmt=LOG_DATE_FORMAT, use_colors=True):
        # Initialize with the base format, colors will be applied in format()
        super().__init__(fmt=fmt, datefmt=datefmt)
        self.use_colors = use_colors
        # Store formatters for each level to avoid recreating them
        self.level_formatters = {}
        for level, _format in self.FORMATS.items():
            self.level_formatters[level] = logging.Formatter(_format, datefmt=datefmt)
        self.default_formatter = logging.Formatter(fmt, datefmt=datefmt)


    def format(self, record):
        if self.use_colors:
            formatter = self.level_formatters.get(record.levelno, self.default_formatter)
        else:
            # If not using colors, ensure a non-colored formatter for all levels
            # This can be a single formatter instance using the base LOG_FORMAT
            if not hasattr(self, 'plain_formatter'):
                self.plain_formatter = logging.Formatter(ColorFormatter.BASE_LOG_FORMAT, datefmt=self.datefmt)
            formatter = self.plain_formatter
        return formatter.format(record)

def setup_logging(level=DEFAULT_LOG_LEVEL, use_colors=True):
    """
    Configures basic logging for the application.
    This function should ideally be called once at the application startup.
    """
    global _logging_configured
    if _logging_configured:
        # print("Warning: setup_logging() called multiple times. Skipping reconfiguration.")
        # Optionally, allow re-configuration by re-getting the root logger and clearing handlers
        return

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove any existing handlers to prevent duplicates if this function is somehow called again
    # for handler in root_logger.handlers[:]:
    #     root_logger.removeHandler(handler)

    # Configure console handler
    # Check if a handler of this type already exists to avoid duplicate logs
    # Handler names can be used for more specific checks if needed.
    if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(ColorFormatter(use_colors=use_colors))
        root_logger.addHandler(console_handler)
    
    # Example: File handler (optional, can be uncommented and customized)
    # try:
    #     file_handler = logging.FileHandler("app.log", encoding='utf-8')
    #     file_formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT) # Non-colored for file
    #     file_handler.setFormatter(file_formatter)
    #     file_handler.setLevel(logging.DEBUG) # Example: log DEBUG and above to file
    #     root_logger.addHandler(file_handler)
    # except IOError as e:
    #     # Use print here as logging might not be fully working if file handler fails
    #     print(f"Error setting up file handler: {e}")

    _logging_configured = True
    # print(f"Logging configured. Root level: {logging.getLevelName(root_logger.level)}")


def get_logger(name: str) -> logging.Logger:
    """
    Retrieves a logger instance with the specified name.
    The logger will inherit its configuration from the root logger setup.
    """
    # Ensure setup_logging has been called at least once.
    if not _logging_configured:
        # Fallback to default setup if not configured. This is not ideal.
        # Application entry point (main.py) should call setup_logging().
        # print("Warning: Logging not configured. Calling setup_logging() with defaults from get_logger().")
        setup_logging()
        
    logger = logging.getLogger(name)
    return logger

if __name__ == '__main__':
    # This block is for testing the logger.py itself.
    # In a real application, setup_logging() would be called in main.py.
    
    print("--- Testing Logger with Colors (Default) ---")
    setup_logging(level=logging.DEBUG, use_colors=True) # Reset and setup for this test run

    logger_main = get_logger("MainApp")
    logger_main.debug("This is a debug message from MainApp.")
    logger_main.info("This is an info message from MainApp.")
    logger_main.warning("This is a warning message from MainApp.")
    logger_main.error("This is an error message from MainApp.")
    logger_main.critical("This is a critical message from MainApp.")

    logger_module = get_logger("MyModule.SubModule")
    logger_module.info("Info message from MyModule.SubModule.")
    try:
        1 / 0
    except ZeroDivisionError:
        logger_module.error("Error calculating division", exc_info=True) # exc_info=True logs stack trace

    print("\n--- Testing Logger without Colors ---")
    # Need to reset handlers if re-configuring. For simplicity, assume fresh start or use a flag.
    # For testing, let's clear existing handlers from root to simulate a new setup call.
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
    _logging_configured = False # Reset flag for test
    
    setup_logging(level=logging.INFO, use_colors=False)
    
    logger_plain = get_logger("PlainLogger")
    logger_plain.debug("This debug message should NOT be visible (level is INFO).")
    logger_plain.info("Plain info message (no color).")
    logger_plain.warning("Plain warning message (no color).")
    logger_plain.error("Plain error message (no color).")

    print("\nFinished logger tests.")
