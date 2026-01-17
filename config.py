import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ETHERSCAN_API_KEY = os.getenv('ETHERSCAN_API_KEY')
SOLSCAN_API_KEY = os.getenv('SOLSCAN_API_KEY', '')
BSC_SCAN_API_KEY = os.getenv('BSC_SCAN_API_KEY', '')
POLYGONSCAN_API_KEY = os.getenv('POLYGONSCAN_API_KEY', '')

# Validate required config
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is required")
if not ETHERSCAN_API_KEY:
    raise ValueError("ETHERSCAN_API_KEY is required")
