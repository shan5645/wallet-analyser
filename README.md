# Telegram Wallet Analyzer Bot 🤖

A powerful Telegram bot that analyzes crypto wallet activity across multiple blockchains.

## Features

- 🔍 Analyze up to 15 wallets simultaneously
- ⛓️ Multi-chain support (Ethereum, Solana, BSC, Polygon)
- 📊 Track last active time and last trade
- 💰 Calculate profit/loss metrics
- 📈 Historical analysis (7, 30, 60 days)
- ⚡ Fast async processing

## Setup

### 1. Clone the Repository
\`\`\`bash
git clone https://github.com/YOUR_USERNAME/telegram-wallet-analyzer.git
cd telegram-wallet-analyzer
\`\`\`

### 2. Install Dependencies
\`\`\`bash
pip install -r requirements.txt
\`\`\`

### 3. Configure Environment Variables
\`\`\`bash
cp .env.example .env
# Edit .env with your API keys
\`\`\`

### 4. Get API Keys

#### Telegram Bot Token
1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Send `/newbot` command
3. Follow instructions to create your bot
4. Copy the API token

#### Etherscan API Key
1. Go to [Etherscan.io](https://etherscan.io/register)
2. Register for a free account
3. Navigate to API Keys section
4. Create new API key

#### Solscan API Key (Optional)
1. Visit [Solscan.io](https://solscan.io)
2. Register and request API access

### 5. Run the Bot
\`\`\`bash
python bot.py
\`\`\`

## Usage

### Commands
- `/start` - Start the bot and see welcome message
- `/help` - Display help information
- `/analyze <addresses>` - Analyze wallet(s)

### Examples
\`\`\`
/analyze 0x742d35Cc6634C0532925a3b844Bc454e4438f44e

/analyze addr1, addr2, addr3
\`\`\`

## Deployment Options

### Option 1: Run on Your Computer
Just run `python bot.py` and keep your terminal open.

### Option 2: Deploy to Cloud (Free Options)

#### Railway.app
1. Push code to GitHub
2. Go to [Railway.app](https://railway.app)
3. Click "New Project" → "Deploy from GitHub"
4. Select your repository
5. Add environment variables in Railway dashboard
6. Deploy!

#### Render.com
1. Push code to GitHub
2. Go to [Render.com](https://render.com)
3. Create new "Web Service"
4. Connect your GitHub repository
5. Add environment variables
6. Deploy!

### Option 3: Docker
\`\`\`bash
docker build -t wallet-bot .
docker run -d --env-file .env wallet-bot
\`\`\`

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License.
\`\`\`

### 4.6 Create `Dockerfile` (Optional)
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
```

## Step 5: Copy the Bot Code

Copy the bot code I provided earlier and save it as `bot.py`, but update the imports:
```python
# At the top of bot.py, replace the config section with:
from config import (
    TELEGRAM_BOT_TOKEN,
    ETHERSCAN_API_KEY,
    SOLSCAN_API_KEY
)
```

## Step 6: Commit and Push to GitHub
```bash
# Add all files
git add .

# Commit changes
git commit -m "Initial commit: Telegram wallet analyzer bot"

# Push to GitHub
git push origin main
```

## Step 7: Set Up Secrets (for Deployment)

### If using GitHub Actions:
1. Go to your repository on GitHub
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **"New repository secret"**
4. Add each secret:
   - `TELEGRAM_BOT_TOKEN`
   - `ETHERSCAN_API_KEY`
   - `SOLSCAN_API_KEY`

## Step 8: Deploy Your Bot

### Option A: Run Locally
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env with your actual API keys

# Run the bot
python bot.py
```

### Option B: Deploy to Railway (Free Cloud Hosting)

1. Go to [Railway.app](https://railway.app)
2. Sign up with GitHub
3. Click **"New Project"** → **"Deploy from GitHub repo"**
4. Select your `telegram-wallet-analyzer` repository
5. Click **"Add variables"** and add:
   - `TELEGRAM_BOT_TOKEN`
   - `ETHERSCAN_API_KEY`
   - `SOLSCAN_API_KEY`
6. Railway will automatically detect and deploy your bot!

### Option C: Deploy to Render.com (Free Cloud Hosting)

1. Go to [Render.com](https://render.com)
2. Sign up with GitHub
3. Click **"New +"** → **"Web Service"**
4. Connect your repository
5. Settings:
   - **Name**: `wallet-analyzer-bot`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
6. Add environment variables
7. Click **"Create Web Service"**

### Option D: Deploy to Heroku
```bash
# Install Heroku CLI
# Create Procfile
echo "worker: python bot.py" > Procfile

# Login to Heroku
heroku login

# Create app
heroku create your-wallet-bot

# Set config vars
heroku config:set TELEGRAM_BOT_TOKEN=your_token
heroku config:set ETHERSCAN_API_KEY=your_key
heroku config:set SOLSCAN_API_KEY=your_key

# Deploy
git push heroku main

# Scale worker
heroku ps:scale worker=1
```

## Step 9: Get Your API Keys

### Telegram Bot Token
1. Open Telegram
2. Search for **@BotFather**
3. Send `/newbot`
4. Follow instructions
5. Copy the token

### Etherscan API Key
1. Go to https://etherscan.io/register
2. Verify your email
3. Go to https://etherscan.io/myapikey
4. Click **"Add"** to create new API key
5. Copy the key

### Solscan API Key (Optional)
1. Visit https://pro-api.solscan.io
2. Sign up for API access
3. Get your API token

## Step 10: Test Your Bot

1. Open Telegram
2. Search for your bot by username
3. Send `/start`
4. Try analyzing a wallet:
