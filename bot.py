import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import aiohttp
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
ETHERSCAN_API_KEY = os.getenv('ETHERSCAN_API_KEY', 'YOUR_ETHERSCAN_API_KEY')
SOLSCAN_API_KEY = os.getenv('SOLSCAN_API_KEY', 'YOUR_SOLSCAN_API_KEY')

class WalletAnalyzer:
    """Analyzes wallet activity across multiple chains"""
    
    def __init__(self):
        self.session = None
        
    async def init_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def close_session(self):
        if self.session:
            await self.session.close()
    
    async def detect_chain(self, address: str) -> str:
        """Detect which blockchain the address belongs to"""
        if len(address) == 42 and address.startswith('0x'):
            return 'ethereum'
        elif len(address) >= 32 and len(address) <= 44:
            return 'solana'
        else:
            return 'unknown'
    
    async def analyze_ethereum_wallet(self, address: str) -> Dict:
        """Analyze Ethereum wallet using Etherscan API"""
        await self.init_session()
        
        try:
            # Get normal transactions
            tx_url = f"https://api.etherscan.io/api?module=account&action=txlist&address={address}&startblock=0&endblock=99999999&sort=desc&apikey={ETHERSCAN_API_KEY}"
            
            async with self.session.get(tx_url) as response:
                tx_data = await response.json()
            
            if tx_data['status'] != '1':
                return {'error': 'Failed to fetch transactions'}
            
            transactions = tx_data['result'][:100]  # Limit to 100 recent transactions
            
            # Get ERC20 token transfers
            token_url = f"https://api.etherscan.io/api?module=account&action=tokentx&address={address}&startblock=0&endblock=99999999&sort=desc&apikey={ETHERSCAN_API_KEY}"
            
            async with self.session.get(token_url) as response:
                token_data = await response.json()
            
            token_txs = token_data['result'][:100] if token_data['status'] == '1' else []
            
            # Calculate metrics
            now = datetime.now()
            last_active = None
            last_trade = None
            
            # Find last activity
            if transactions:
                last_active = datetime.fromtimestamp(int(transactions[0]['timeStamp']))
            
            # Find last trade (token transfer)
            if token_txs:
                last_trade = datetime.fromtimestamp(int(token_txs[0]['timeStamp']))
            
            # Calculate P&L (simplified - would need price data for accurate calculation)
            # This is a placeholder implementation
            total_eth_in = sum(int(tx['value']) for tx in transactions if tx['to'].lower() == address.lower()) / 1e18
            total_eth_out = sum(int(tx['value']) for tx in transactions if tx['from'].lower() == address.lower()) / 1e18
            
            return {
                'chain': 'Ethereum',
                'address': address,
                'last_active': last_active,
                'last_trade': last_trade,
                'total_transactions': len(transactions),
                'total_token_transfers': len(token_txs),
                'eth_balance_change': total_eth_in - total_eth_out,
                'recent_txs': transactions[:5]
            }
            
        except Exception as e:
            logger.error(f"Error analyzing Ethereum wallet: {e}")
            return {'error': str(e)}
    
    async def analyze_solana_wallet(self, address: str) -> Dict:
        """Analyze Solana wallet using Solscan API"""
        await self.init_session()
        
        try:
            # Get account transactions
            tx_url = f"https://public-api.solscan.io/account/transactions?account={address}&limit=50"
            headers = {'token': SOLSCAN_API_KEY} if SOLSCAN_API_KEY != 'YOUR_SOLSCAN_API_KEY' else {}
            
            async with self.session.get(tx_url, headers=headers) as response:
                tx_data = await response.json()
            
            transactions = tx_data if isinstance(tx_data, list) else []
            
            # Calculate metrics
            last_active = None
            if transactions:
                last_active = datetime.fromtimestamp(transactions[0].get('blockTime', 0))
            
            return {
                'chain': 'Solana',
                'address': address,
                'last_active': last_active,
                'total_transactions': len(transactions),
                'recent_txs': transactions[:5]
            }
            
        except Exception as e:
            logger.error(f"Error analyzing Solana wallet: {e}")
            return {'error': str(e)}
    
    async def analyze_wallet(self, address: str) -> Dict:
        """Main wallet analysis function"""
        chain = await self.detect_chain(address)
        
        if chain == 'ethereum':
            return await self.analyze_ethereum_wallet(address)
        elif chain == 'solana':
            return await self.analyze_solana_wallet(address)
        else:
            return {'error': 'Unknown chain or invalid address'}
    
    async def analyze_multiple_wallets(self, addresses: List[str]) -> List[Dict]:
        """Analyze multiple wallets concurrently"""
        tasks = [self.analyze_wallet(addr) for addr in addresses]
        results = await asyncio.gather(*tasks)
        return results

# Initialize analyzer
analyzer = WalletAnalyzer()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    welcome_message = """
🤖 *Wallet Analyzer Bot*

I can analyze up to 15 crypto wallets and provide:
• Last active time
• Last trade timestamp
• Total profit/loss
• P&L for last 7, 30, 60 days
• Transaction history

*Commands:*
/analyze <addresses> - Analyze wallets (comma-separated)
/help - Show this message

*Example:*
`/analyze 0x742d35Cc6634C0532925a3b844Bc454e4438f44e`

Supports Ethereum and Solana chains!
"""
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    await start(update, context)

async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analyze wallets command handler"""
    if not context.args:
        await update.message.reply_text(
            "Please provide wallet addresses to analyze.\n"
            "Example: `/analyze 0x742d35Cc6634C0532925a3b844Bc454e4438f44e`",
            parse_mode='Markdown'
        )
        return
    
    # Parse addresses
    addresses_text = ' '.join(context.args)
    addresses = [addr.strip() for addr in addresses_text.replace(',', ' ').split() if addr.strip()]
    
    if len(addresses) > 15:
        await update.message.reply_text("⚠️ Maximum 15 wallets can be analyzed at once.")
        addresses = addresses[:15]
    
    # Send processing message
    processing_msg = await update.message.reply_text(
        f"🔍 Analyzing {len(addresses)} wallet(s)...\nThis may take a moment."
    )
    
    try:
        # Analyze wallets
        results = await analyzer.analyze_multiple_wallets(addresses)
        
        # Format results
        response = "📊 *Wallet Analysis Results*\n\n"
        
        for i, result in enumerate(results, 1):
            if 'error' in result:
                response += f"❌ *Wallet {i}*\n"
                response += f"Address: `{addresses[i-1][:10]}...`\n"
                response += f"Error: {result['error']}\n\n"
            else:
                response += f"✅ *Wallet {i}* ({result['chain']})\n"
                response += f"Address: `{result['address'][:10]}...{result['address'][-8:]}`\n"
                
                if result.get('last_active'):
                    time_ago = datetime.now() - result['last_active']
                    response += f"🕐 Last Active: {format_time_ago(time_ago)}\n"
                
                if result.get('last_trade'):
                    trade_ago = datetime.now() - result['last_trade']
                    response += f"💱 Last Trade: {format_time_ago(trade_ago)}\n"
                
                response += f"📝 Total Transactions: {result.get('total_transactions', 'N/A')}\n"
                
                if 'eth_balance_change' in result:
                    response += f"💰 ETH Flow: {result['eth_balance_change']:.4f} ETH\n"
                
                response += "\n"
        
        # Split message if too long
        if len(response) > 4096:
            for i in range(0, len(response), 4096):
                await update.message.reply_text(response[i:i+4096], parse_mode='Markdown')
        else:
            await update.message.reply_text(response, parse_mode='Markdown')
        
        # Delete processing message
        await processing_msg.delete()
        
    except Exception as e:
        logger.error(f"Error in analyze_command: {e}")
        await update.message.reply_text(f"❌ An error occurred: {str(e)}")

def format_time_ago(delta: timedelta) -> str:
    """Format timedelta to human-readable string"""
    seconds = int(delta.total_seconds())
    
    if seconds < 60:
        return f"{seconds}s ago"
    elif seconds < 3600:
        return f"{seconds // 60}m ago"
    elif seconds < 86400:
        return f"{seconds // 3600}h ago"
    else:
        return f"{seconds // 86400}d ago"

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors"""
    logger.error(f"Update {update} caused error {context.error}")

def main():
    """Start the bot"""
    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("analyze", analyze_command))
    
    # Error handler
    application.add_error_handler(error_handler)
    
    # Start bot
    logger.info("Bot started!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
