import logging
from pathlib import Path

# Create logs directory if it doesn't exist
logs_dir = Path(__file__).resolve().parent.parent / "logs"
logs_dir.mkdir(exist_ok=True)

# Define log file path
log_file = logs_dir / "application.log"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file, mode='w'),  # Overwrites log on each run
        logging.StreamHandler()  # Also prints to console
    ]
)

# Centralized logger instance
logger = logging.getLogger("agentic_ai")