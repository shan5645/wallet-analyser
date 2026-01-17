import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import aiohttp
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
ETHERSCAN_API_KEY = os.getenv('ETHERSCAN_API_KEY', 'YOUR_ETHERSCAN_API_KEY')
HELIUS_API_KEY = os.getenv('HELIUS_API_KEY', '')  # Optional but recommended for Solana
SOLSCAN_API_TOKEN = os.getenv('SOLSCAN_API_TOKEN', '')  # Optional for Solscan Pro

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
        elif len(address) >= 32 and len(address) <= 44 and not address.startswith('0x'):
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
            
            transactions = tx_data['result'][:100]
            
            # Get ERC20 token transfers
            token_url = f"https://api.etherscan.io/api?module=account&action=tokentx&address={address}&startblock=0&endblock=99999999&sort=desc&apikey={ETHERSCAN_API_KEY}"
            
            async with self.session.get(token_url) as response:
                token_data = await response.json()
            
            token_txs = token_data['result'][:100] if token_data['status'] == '1' else []
            
            # Get account balance
            balance_url = f"https://api.etherscan.io/api?module=account&action=balance&address={address}&tag=latest&apikey={ETHERSCAN_API_KEY}"
            
            async with self.session.get(balance_url) as response:
                balance_data = await response.json()
            
            eth_balance = int(balance_data['result']) / 1e18 if balance_data['status'] == '1' else 0
            
            # Calculate metrics
            now = datetime.now()
            last_active = None
            last_trade = None
            
            if transactions:
                last_active = datetime.fromtimestamp(int(transactions[0]['timeStamp']))
            
            if token_txs:
                last_trade = datetime.fromtimestamp(int(token_txs[0]['timeStamp']))
            
            # Calculate time-based metrics
            metrics_7d = self._calculate_period_metrics(transactions, token_txs, 7)
            metrics_30d = self._calculate_period_metrics(transactions, token_txs, 30)
            metrics_60d = self._calculate_period_metrics(transactions, token_txs, 60)
            
            return {
                'chain': 'Ethereum',
                'address': address,
                'last_active': last_active,
                'last_trade': last_trade,
                'current_balance': eth_balance,
                'total_transactions': len(transactions),
                'total_token_transfers': len(token_txs),
                'metrics_7d': metrics_7d,
                'metrics_30d': metrics_30d,
                'metrics_60d': metrics_60d,
            }
            
        except Exception as e:
            logger.error(f"Error analyzing Ethereum wallet: {e}")
            return {'error': str(e)}
    
    async def analyze_solana_wallet(self, address: str) -> Dict:
        """Analyze Solana wallet using Helius or public RPC"""
        await self.init_session()
        
        try:
            # Use Helius if API key is available, otherwise use public RPC
            if HELIUS_API_KEY:
                rpc_url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
            else:
                rpc_url = "https://api.mainnet-beta.solana.com"
            
            # Get account info and balance
            balance_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getBalance",
                "params": [address]
            }
            
            async with self.session.post(rpc_url, json=balance_payload) as response:
                balance_data = await response.json()
            
            balance_lamports = balance_data.get('result', {}).get('value', 0)
            sol_balance = balance_lamports / 1e9
            
            # Get transaction signatures
            sig_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [address, {"limit": 100}]
            }
            
            async with self.session.post(rpc_url, json=sig_payload) as response:
                sig_data = await response.json()
            
            signatures = sig_data.get('result', [])
            
            # Calculate metrics
            last_active = None
            if signatures:
                last_active = datetime.fromtimestamp(signatures[0].get('blockTime', 0))
            
            # Count transactions in different periods
            now = datetime.now()
            tx_7d = sum(1 for sig in signatures if datetime.fromtimestamp(sig.get('blockTime', 0)) > now - timedelta(days=7))
            tx_30d = sum(1 for sig in signatures if datetime.fromtimestamp(sig.get('blockTime', 0)) > now - timedelta(days=30))
            tx_60d = sum(1 for sig in signatures if datetime.fromtimestamp(sig.get('blockTime', 0)) > now - timedelta(days=60))
            
            return {
                'chain': 'Solana',
                'address': address,
                'last_active': last_active,
                'current_balance': sol_balance,
                'total_transactions': len(signatures),
                'transactions_7d': tx_7d,
                'transactions_30d': tx_30d,
                'transactions_60d': tx_60d,
            }
            
        except Exception as e:
            logger.error(f"Error analyzing Solana wallet: {e}")
            return {'error': str(e)}
    
    def _calculate_period_metrics(self, transactions: List, token_txs: List, days: int) -> Dict:
        """Calculate metrics for a specific time period"""
        now = datetime.now()
        cutoff = now - timedelta(days=days)
        
        period_txs = [tx for tx in transactions if datetime.fromtimestamp(int(tx['timeStamp'])) > cutoff]
        period_token_txs = [tx for tx in token_txs if datetime.fromtimestamp(int(tx['timeStamp'])) > cutoff]
        
        return {
            'transactions': len(period_txs),
            'token_transfers': len(period_token_txs),
            'total_activity': len(period_txs) + len(period_token_txs)
        }
    
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
• 🕐 Last active time
• 💱 Last trade timestamp
• 📊 Activity metrics (7, 30, 60 days)
• 💰 Current balance
• 📝 Transaction history

*Commands:*
/analyze <addresses> - Analyze wallets
/help - Show this message

*Example:*
`/analyze 0x742d35Cc6634C0532925a3b844Bc454e4438f44e`

Or multiple wallets:
`/analyze addr1 addr2 addr3`

*Supported Chains:*
✅ Ethereum (ETH)
✅ Solana (SOL)
"""
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    help_text = """
📚 *How to Use Wallet Analyzer*

*Single Wallet:*
`/analyze 0x742d35Cc6634C0532925a3b844Bc454e4438f44e`

*Multiple Wallets (up to 15):*
`/analyze wallet1 wallet2 wallet3`

*What You Get:*
• Last activity timestamp
• Transaction counts
• Period-based analytics (7/30/60 days)
• Current balances
• Token transfer activity

*Tips:*
• Use commas or spaces to separate addresses
• Works with both ETH and SOL addresses
• Analysis takes 5-15 seconds per wallet

Need help? Contact @YourUsername
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analyze wallets command handler"""
    if not context.args:
        await update.message.reply_text(
            "⚠️ Please provide wallet addresses to analyze.\n\n"
            "*Example:*\n"
            "`/analyze 0x742d35Cc6634C0532925a3b844Bc454e4438f44e`\n\n"
            "Or multiple:\n"
            "`/analyze addr1 addr2 addr3`",
            parse_mode='Markdown'
        )
        return
    
    # Parse addresses
    addresses_text = ' '.join(context.args)
    addresses = [addr.strip() for addr in addresses_text.replace(',', ' ').split() if addr.strip()]
    
    if len(addresses) > 15:
        await update.message.reply_text("⚠️ Maximum 15 wallets can be analyzed at once. Analyzing first 15...")
        addresses = addresses[:15]
    
    # Send processing message
    processing_msg = await update.message.reply_text(
        f"🔍 Analyzing {len(addresses)} wallet(s)...\n⏳ Please wait..."
    )
    
    try:
        # Analyze wallets
        results = await analyzer.analyze_multiple_wallets(addresses)
        
        # Format results
        messages = []
        current_message = "📊 *Wallet Analysis Results*\n\n"
        
        for i, result in enumerate(results, 1):
            wallet_info = f"{'='*40}\n"
            
            if 'error' in result:
                wallet_info += f"❌ *Wallet {i}*\n"
                wallet_info += f"Address: `{addresses[i-1][:15]}...`\n"
                wallet_info += f"Error: {result['error']}\n\n"
            else:
                wallet_info += f"✅ *Wallet {i}* - {result['chain']}\n"
                wallet_info += f"📍 `{result['address'][:8]}...{result['address'][-6:]}`\n\n"
                
                # Last activity
                if result.get('last_active'):
                    time_ago = datetime.now() - result['last_active']
                    wallet_info += f"🕐 *Last Active:* {format_time_ago(time_ago)}\n"
                    wallet_info += f"   ({result['last_active'].strftime('%Y-%m-%d %H:%M')})\n"
                
                # Last trade (Ethereum only)
                if result.get('last_trade'):
                    trade_ago = datetime.now() - result['last_trade']
                    wallet_info += f"💱 *Last Trade:* {format_time_ago(trade_ago)}\n"
                
                # Current balance
                if 'current_balance' in result:
                    currency = 'ETH' if result['chain'] == 'Ethereum' else 'SOL'
                    wallet_info += f"💰 *Balance:* {result['current_balance']:.4f} {currency}\n"
                
                wallet_info += f"\n📈 *Activity Metrics:*\n"
                
                # Ethereum metrics
                if result['chain'] == 'Ethereum':
                    wallet_info += f"   Total Txs: {result.get('total_transactions', 0)}\n"
                    wallet_info += f"   Token Transfers: {result.get('total_token_transfers', 0)}\n\n"
                    
                    for period, days in [('7d', 7), ('30d', 30), ('60d', 60)]:
                        metrics = result.get(f'metrics_{days}d', {})
                        wallet_info += f"   *Last {days} days:*\n"
                        wallet_info += f"      Txs: {metrics.get('transactions', 0)}\n"
                        wallet_info += f"      Tokens: {metrics.get('token_transfers', 0)}\n"
                
                # Solana metrics
                else:
                    wallet_info += f"   Total: {result.get('total_transactions', 0)} txs\n"
                    wallet_info += f"   Last 7d: {result.get('transactions_7d', 0)} txs\n"
                    wallet_info += f"   Last 30d: {result.get('transactions_30d', 0)} txs\n"
                    wallet_info += f"   Last 60d: {result.get('transactions_60d', 0)} txs\n"
                
                wallet_info += "\n"
            
            # Check if adding this wallet would exceed message limit
            if len(current_message) + len(wallet_info) > 4000:
                messages.append(current_message)
                current_message = wallet_info
            else:
                current_message += wallet_info
        
        # Add remaining message
        if current_message:
            messages.append(current_message)
        
        # Send all messages
        for msg in messages:
            await update.message.reply_text(msg, parse_mode='Markdown')
        
        # Delete processing message
        await processing_msg.delete()
        
    except Exception as e:
        logger.error(f"Error in analyze_command: {e}")
        await update.message.reply_text(f"❌ An error occurred: {str(e)}")
        try:
            await processing_msg.delete()
        except:
            pass

def format_time_ago(delta: timedelta) -> str:
    """Format timedelta to human-readable string"""
    seconds = int(delta.total_seconds())
    
    if seconds < 0:
        return "just now"
    elif seconds < 60:
        return f"{seconds}s ago"
    elif seconds < 3600:
        mins = seconds // 60
        return f"{mins}m ago"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"{hours}h ago"
    elif seconds < 2592000:  # 30 days
        days = seconds // 86400
        return f"{days}d ago"
    else:
        months = seconds // 2592000
        return f"{months}mo ago"

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors"""
    logger.error(f"Update {update} caused error {context.error}")

async def post_init(application: Application):
    """Initialize after app is created"""
    logger.info("Bot initialized successfully")
    logger.info(f"Etherscan API: {'✓' if ETHERSCAN_API_KEY != 'YOUR_ETHERSCAN_API_KEY' else '✗'}")
    logger.info(f"Helius API: {'✓ (Recommended for Solana)' if HELIUS_API_KEY else '✗ (Using public RPC)'}")

async def post_shutdown(application: Application):
    """Cleanup on shutdown"""
    await analyzer.close_session()
    logger.info("Bot shutdown complete")

def main():
    """Start the bot"""
    # Create application
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("analyze", analyze_command))
    
    # Error handler
    application.add_error_handler(error_handler)
    
    # Start bot
    logger.info("Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
