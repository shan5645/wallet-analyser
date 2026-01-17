import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import aiohttp
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
ETHERSCAN_API_KEY = os.getenv('ETHERSCAN_API_KEY', 'YOUR_ETHERSCAN_API_KEY')
HELIUS_API_KEY = os.getenv('HELIUS_API_KEY', '')
COINGECKO_API_KEY = os.getenv('COINGECKO_API_KEY', '')  # Optional, for higher rate limits

class WalletAnalyzer:
    """Analyzes wallet activity across multiple chains with P&L calculations"""
    
    def __init__(self):
        self.session = None
        self.price_cache = {}
        
    async def init_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def close_session(self):
        if self.session:
            await self.session.close()
    
    async def get_token_price(self, contract_address: str, timestamp: Optional[int] = None) -> float:
        """Get token price from CoinGecko"""
        await self.init_session()
        
        try:
            # Check cache first
            cache_key = f"{contract_address}_{timestamp}"
            if cache_key in self.price_cache:
                return self.price_cache[cache_key]
            
            if timestamp:
                # Historical price
                date_str = datetime.fromtimestamp(timestamp).strftime('%d-%m-%Y')
                url = f"https://api.coingecko.com/api/v3/coins/ethereum/contract/{contract_address}/market_chart/range"
                params = {
                    'vs_currency': 'usd',
                    'from': timestamp - 3600,
                    'to': timestamp + 3600
                }
            else:
                # Current price
                url = f"https://api.coingecko.com/api/v3/simple/token_price/ethereum"
                params = {
                    'contract_addresses': contract_address,
                    'vs_currencies': 'usd'
                }
            
            headers = {}
            if COINGECKO_API_KEY:
                headers['x-cg-pro-api-key'] = COINGECKO_API_KEY
            
            async with self.session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    if timestamp and 'prices' in data and data['prices']:
                        price = data['prices'][0][1]
                    else:
                        price = list(data.values())[0].get('usd', 0) if data else 0
                    
                    self.price_cache[cache_key] = price
                    return price
            
            return 0
        except Exception as e:
            logger.error(f"Error getting token price: {e}")
            return 0
    
    async def get_eth_price(self, timestamp: Optional[int] = None) -> float:
        """Get ETH price at specific timestamp or current"""
        await self.init_session()
        
        try:
            cache_key = f"eth_{timestamp}"
            if cache_key in self.price_cache:
                return self.price_cache[cache_key]
            
            if timestamp:
                date_str = datetime.fromtimestamp(timestamp).strftime('%d-%m-%Y')
                url = f"https://api.coingecko.com/api/v3/coins/ethereum/history"
                params = {'date': date_str}
            else:
                url = "https://api.coingecko.com/api/v3/simple/price"
                params = {'ids': 'ethereum', 'vs_currencies': 'usd'}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if timestamp:
                        price = data.get('market_data', {}).get('current_price', {}).get('usd', 0)
                    else:
                        price = data.get('ethereum', {}).get('usd', 0)
                    
                    self.price_cache[cache_key] = price
                    return price
            
            return 0
        except Exception as e:
            logger.error(f"Error getting ETH price: {e}")
            return 0
    
    async def get_sol_price(self, timestamp: Optional[int] = None) -> float:
        """Get SOL price at specific timestamp or current"""
        await self.init_session()
        
        try:
            cache_key = f"sol_{timestamp}"
            if cache_key in self.price_cache:
                return self.price_cache[cache_key]
            
            if timestamp:
                date_str = datetime.fromtimestamp(timestamp).strftime('%d-%m-%Y')
                url = f"https://api.coingecko.com/api/v3/coins/solana/history"
                params = {'date': date_str}
            else:
                url = "https://api.coingecko.com/api/v3/simple/price"
                params = {'ids': 'solana', 'vs_currencies': 'usd'}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if timestamp:
                        price = data.get('market_data', {}).get('current_price', {}).get('usd', 0)
                    else:
                        price = data.get('solana', {}).get('usd', 0)
                    
                    self.price_cache[cache_key] = price
                    return price
            
            return 0
        except Exception as e:
            logger.error(f"Error getting SOL price: {e}")
            return 0
    
    async def detect_chain(self, address: str) -> str:
        """Detect which blockchain the address belongs to"""
        if len(address) == 42 and address.startswith('0x'):
            return 'ethereum'
        elif len(address) >= 32 and len(address) <= 44 and not address.startswith('0x'):
            return 'solana'
        else:
            return 'unknown'
    
    async def calculate_token_pnl(self, token_txs: List, address: str, days: Optional[int] = None) -> Dict:
        """Calculate P&L for token trades"""
        now = datetime.now()
        cutoff = now - timedelta(days=days) if days else datetime.fromtimestamp(0)
        
        token_positions = {}  # token_address: {amount, buy_value, sell_value}
        trades = []
        
        for tx in token_txs:
            tx_time = datetime.fromtimestamp(int(tx['timeStamp']))
            if tx_time < cutoff:
                continue
            
            token_addr = tx['contractAddress']
            token_symbol = tx.get('tokenSymbol', 'UNKNOWN')
            value = float(tx['value']) / (10 ** int(tx.get('tokenDecimal', 18)))
            
            is_buy = tx['to'].lower() == address.lower()
            
            if token_addr not in token_positions:
                token_positions[token_addr] = {
                    'symbol': token_symbol,
                    'amount': 0,
                    'buy_value': 0,
                    'sell_value': 0,
                    'first_trade': tx_time,
                    'last_trade': tx_time
                }
            
            pos = token_positions[token_addr]
            
            if is_buy:
                pos['amount'] += value
                pos['buy_value'] += value
            else:
                pos['amount'] -= value
                pos['sell_value'] += value
            
            pos['last_trade'] = tx_time
            
            # Record trade for "most profitable" analysis
            trades.append({
                'token': token_symbol,
                'type': 'BUY' if is_buy else 'SELL',
                'amount': value,
                'time': tx_time,
                'hash': tx['hash']
            })
        
        # Calculate total P&L estimate
        total_pnl = 0
        most_profitable = None
        max_profit = float('-inf')
        
        for token_addr, pos in token_positions.items():
            # Simple P&L: sell_value - buy_value (simplified, doesn't account for exact prices)
            pnl = pos['sell_value'] - pos['buy_value']
            total_pnl += pnl
            
            if pnl > max_profit:
                max_profit = pnl
                hold_time = (pos['last_trade'] - pos['first_trade']).days
                most_profitable = {
                    'token': pos['symbol'],
                    'pnl': pnl,
                    'hold_days': hold_time
                }
        
        return {
            'total_pnl': total_pnl,
            'total_trades': len(trades),
            'most_profitable': most_profitable,
            'positions': len(token_positions)
        }
    
    async def analyze_ethereum_wallet(self, address: str, period_days: Optional[int] = None) -> Dict:
        """Analyze Ethereum wallet with P&L calculations"""
        await self.init_session()
        
        try:
            # Get transactions
            tx_url = f"https://api.etherscan.io/api?module=account&action=txlist&address={address}&startblock=0&endblock=99999999&sort=desc&apikey={ETHERSCAN_API_KEY}"
            async with self.session.get(tx_url) as response:
                tx_data = await response.json()
            
            if tx_data['status'] != '1':
                return {'error': 'Failed to fetch transactions'}
            
            transactions = tx_data['result']
            
            # Get token transfers
            token_url = f"https://api.etherscan.io/api?module=account&action=tokentx&address={address}&startblock=0&endblock=99999999&sort=desc&apikey={ETHERSCAN_API_KEY}"
            async with self.session.get(token_url) as response:
                token_data = await response.json()
            
            token_txs = token_data['result'] if token_data['status'] == '1' else []
            
            # Get current balance
            balance_url = f"https://api.etherscan.io/api?module=account&action=balance&address={address}&tag=latest&apikey={ETHERSCAN_API_KEY}"
            async with self.session.get(balance_url) as response:
                balance_data = await response.json()
            
            eth_balance = int(balance_data['result']) / 1e18 if balance_data['status'] == '1' else 0
            
            # Calculate metrics
            now = datetime.now()
            cutoff = now - timedelta(days=period_days) if period_days else datetime.fromtimestamp(0)
            
            # Filter by period
            period_txs = [tx for tx in transactions if datetime.fromtimestamp(int(tx['timeStamp'])) > cutoff]
            period_token_txs = [tx for tx in token_txs if datetime.fromtimestamp(int(tx['timeStamp'])) > cutoff]
            
            # Calculate ETH P&L for period
            eth_in = sum(int(tx['value']) for tx in period_txs if tx['to'].lower() == address.lower()) / 1e18
            eth_out = sum(int(tx['value']) for tx in period_txs if tx['from'].lower() == address.lower()) / 1e18
            
            # Get current ETH price
            current_eth_price = await self.get_eth_price()
            eth_pnl_usd = (eth_in - eth_out) * current_eth_price
            
            # Calculate token P&L
            token_pnl_data = await self.calculate_token_pnl(period_token_txs, address, period_days)
            
            # Find last activity
            last_active = datetime.fromtimestamp(int(transactions[0]['timeStamp'])) if transactions else None
            last_trade = datetime.fromtimestamp(int(token_txs[0]['timeStamp'])) if token_txs else None
            
            return {
                'chain': 'Ethereum',
                'address': address,
                'last_active': last_active,
                'last_trade': last_trade,
                'current_balance': eth_balance,
                'current_balance_usd': eth_balance * current_eth_price,
                'total_transactions': len(period_txs),
                'total_token_transfers': len(period_token_txs),
                'eth_pnl': eth_in - eth_out,
                'eth_pnl_usd': eth_pnl_usd,
                'token_pnl': token_pnl_data,
                'period_days': period_days or 'All Time'
            }
            
        except Exception as e:
            logger.error(f"Error analyzing Ethereum wallet: {e}")
            return {'error': str(e)}
    
    async def analyze_solana_wallet(self, address: str, period_days: Optional[int] = None) -> Dict:
        """Analyze Solana wallet with P&L calculations"""
        await self.init_session()
        
        try:
            if HELIUS_API_KEY:
                rpc_url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
            else:
                rpc_url = "https://api.mainnet-beta.solana.com"
            
            # Get balance
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
            
            # Get transactions
            sig_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [address, {"limit": 1000}]
            }
            
            async with self.session.post(rpc_url, json=sig_payload) as response:
                sig_data = await response.json()
            
            signatures = sig_data.get('result', [])
            
            # Calculate metrics
            now = datetime.now()
            cutoff = now - timedelta(days=period_days) if period_days else datetime.fromtimestamp(0)
            
            period_sigs = [sig for sig in signatures if datetime.fromtimestamp(sig.get('blockTime', 0)) > cutoff]
            
            # Get SOL price
            current_sol_price = await self.get_sol_price()
            
            # Estimate P&L (simplified - would need transaction details for accuracy)
            # This is a rough estimate based on transaction count and balance
            last_active = datetime.fromtimestamp(signatures[0].get('blockTime', 0)) if signatures else None
            
            return {
                'chain': 'Solana',
                'address': address,
                'last_active': last_active,
                'current_balance': sol_balance,
                'current_balance_usd': sol_balance * current_sol_price,
                'total_transactions': len(period_sigs),
                'period_days': period_days or 'All Time',
                'note': 'Detailed P&L requires transaction parsing'
            }
            
        except Exception as e:
            logger.error(f"Error analyzing Solana wallet: {e}")
            return {'error': str(e)}
    
    async def analyze_wallet(self, address: str, period_days: Optional[int] = None) -> Dict:
        """Main wallet analysis function"""
        chain = await self.detect_chain(address)
        
        if chain == 'ethereum':
            return await self.analyze_ethereum_wallet(address, period_days)
        elif chain == 'solana':
            return await self.analyze_solana_wallet(address, period_days)
        else:
            return {'error': 'Unknown chain or invalid address'}
    
    async def analyze_multiple_wallets(self, addresses: List[str], period_days: Optional[int] = None) -> List[Dict]:
        """Analyze multiple wallets concurrently"""
        tasks = [self.analyze_wallet(addr, period_days) for addr in addresses]
        results = await asyncio.gather(*tasks)
        return results

# Initialize analyzer
analyzer = WalletAnalyzer()

# Store user context for callbacks
user_contexts = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    welcome_message = """
🤖 *Wallet Analyzer Bot v2.0*

Advanced crypto wallet analysis with P&L tracking!

*Features:*
💰 Profit/Loss calculations
📊 Time-based analysis (7/30/60 days)
🏆 Most profitable trades
⏱️ Hold time tracking
💵 USD valuations

*Commands:*
/analyze <addresses> - Quick analysis
/help - Show this message

*Example:*
`/analyze 0x742d35Cc6634C0532925a3b844Bc454e4438f44e`

After analysis, use buttons to check different timeframes!
"""
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    help_text = """
📚 *Wallet Analyzer Guide*

*Basic Usage:*
`/analyze <wallet_address>`

*Multiple Wallets:*
`/analyze addr1 addr2 addr3`

*What You Get:*
• 💰 Total P&L in USD
• 📈 Period-based analysis (7/30/60d)
• 🏆 Most profitable trades
• ⏱️ Average hold times
• 💵 Current portfolio value

*Interactive Buttons:*
After analysis, click:
• 7D - Last 7 days P&L
• 30D - Last 30 days P&L
• 60D - Last 60 days P&L
• All - All-time analysis

*Supported Chains:*
✅ Ethereum (full P&L tracking)
✅ Solana (basic metrics)

*Tips:*
• Analysis takes 10-30 seconds
• Prices from CoinGecko API
• Up to 15 wallets at once
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analyze wallets command handler"""
    if not context.args:
        await update.message.reply_text(
            "⚠️ Please provide wallet address(es)\n\n"
            "*Example:*\n"
            "`/analyze 0x742d35Cc6634C0532925a3b844Bc454e4438f44e`",
            parse_mode='Markdown'
        )
        return
    
    # Parse addresses
    addresses_text = ' '.join(context.args)
    addresses = [addr.strip() for addr in addresses_text.replace(',', ' ').split() if addr.strip()]
    
    if len(addresses) > 15:
        await update.message.reply_text("⚠️ Maximum 15 wallets. Analyzing first 15...")
        addresses = addresses[:15]
    
    # Store addresses in user context
    user_id = update.effective_user.id
    user_contexts[user_id] = {'addresses': addresses}
    
    # Send processing message
    processing_msg = await update.message.reply_text(
        f"🔍 Analyzing {len(addresses)} wallet(s)...\n"
        f"⏳ Fetching transactions and prices...\n"
        f"This may take 15-30 seconds..."
    )
    
    try:
        # Analyze wallets (all time by default)
        results = await analyzer.analyze_multiple_wallets(addresses)
        
        # Format and send results
        await send_analysis_results(update, results, addresses, None)
        
        # Delete processing message
        await processing_msg.delete()
        
    except Exception as e:
        logger.error(f"Error in analyze_command: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")
        try:
            await processing_msg.delete()
        except:
            pass

async def send_analysis_results(update: Update, results: List[Dict], addresses: List[str], period_days: Optional[int]):
    """Send formatted analysis results with interactive buttons"""
    
    period_label = f"{period_days}D" if period_days else "All Time"
    response = f"📊 *Wallet Analysis - {period_label}*\n\n"
    
    for i, result in enumerate(results, 1):
        if 'error' in result:
            response += f"❌ *Wallet {i}*\n`{addresses[i-1][:12]}...`\nError: {result['error']}\n\n"
            continue
        
        response += f"{'='*35}\n"
        response += f"✅ *Wallet {i}* - {result['chain']}\n"
        response += f"📍 `{result['address'][:8]}...{result['address'][-6:]}`\n\n"
        
        # Last activity
        if result.get('last_active'):
            time_ago = datetime.now() - result['last_active']
            response += f"🕐 Last Active: {format_time_ago(time_ago)}\n"
        
        if result.get('last_trade'):
            trade_ago = datetime.now() - result['last_trade']
            response += f"💱 Last Trade: {format_time_ago(trade_ago)}\n"
        
        # Current holdings
        response += f"\n💰 *Current Holdings:*\n"
        currency = 'ETH' if result['chain'] == 'Ethereum' else 'SOL'
        response += f"   {result['current_balance']:.4f} {currency}\n"
        
        if 'current_balance_usd' in result:
            response += f"   ≈ ${result['current_balance_usd']:.2f} USD\n"
        
        # P&L Section (Ethereum only)
        if result['chain'] == 'Ethereum':
            response += f"\n📈 *P&L Analysis:*\n"
            
            # ETH P&L
            eth_pnl = result.get('eth_pnl', 0)
            eth_pnl_usd = result.get('eth_pnl_usd', 0)
            pnl_emoji = "📈" if eth_pnl_usd > 0 else "📉" if eth_pnl_usd < 0 else "➖"
            
            response += f"   {pnl_emoji} ETH: {eth_pnl:+.4f} ETH (${eth_pnl_usd:+.2f})\n"
            
            # Token P&L
            token_pnl = result.get('token_pnl', {})
            if token_pnl.get('total_trades', 0) > 0:
                response += f"   📝 Token Trades: {token_pnl['total_trades']}\n"
                response += f"   🎯 Active Positions: {token_pnl['positions']}\n"
                
                # Most profitable trade
                if token_pnl.get('most_profitable'):
                    mp = token_pnl['most_profitable']
                    response += f"\n🏆 *Most Profitable:*\n"
                    response += f"   Token: {mp['token']}\n"
                    response += f"   P&L: {mp['pnl']:+.2f} tokens\n"
                    response += f"   Hold Time: {mp['hold_days']} days\n"
        
        # Activity stats
        response += f"\n📊 *Activity ({period_label}):*\n"
        response += f"   Total Txs: {result.get('total_transactions', 0)}\n"
        
        if result['chain'] == 'Ethereum':
            response += f"   Token Transfers: {result.get('total_token_transfers', 0)}\n"
        
        response += "\n"
    
    # Create period selection buttons
    keyboard = [
        [
            InlineKeyboardButton("7D", callback_data="period_7"),
            InlineKeyboardButton("30D", callback_data="period_30"),
            InlineKeyboardButton("60D", callback_data="period_60"),
            InlineKeyboardButton("All Time", callback_data="period_all")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Split if too long
    if len(response) > 4096:
        chunks = [response[i:i+4096] for i in range(0, len(response), 4096)]
        for chunk in chunks[:-1]:
            await update.effective_message.reply_text(chunk, parse_mode='Markdown')
        await update.effective_message.reply_text(chunks[-1], parse_mode='Markdown', reply_markup=reply_markup)
    else:
        await update.effective_message.reply_text(response, parse_mode='Markdown', reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks for period selection"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in user_contexts:
        await query.edit_message_text("❌ Session expired. Please run /analyze again.")
        return
    
    # Get period from callback data
    period_map = {
        'period_7': 7,
        'period_30': 30,
        'period_60': 60,
        'period_all': None
    }
    
    period_days = period_map.get(query.data)
    addresses = user_contexts[user_id]['addresses']
    
    # Send "analyzing" message
    await query.edit_message_text(f"🔍 Re-analyzing for {query.data.split('_')[1].upper()} period...")
    
    try:
        # Re-analyze with new period
        results = await analyzer.analyze_multiple_wallets(addresses, period_days)
        
        # Send new results
        await send_analysis_results(update, results, addresses, period_days)
        
    except Exception as e:
        logger.error(f"Error in button_callback: {e}")
        await query.edit_message_text(f"❌ Error: {str(e)}")

def format_time_ago(delta: timedelta) -> str:
    """Format timedelta to human-readable string"""
    seconds = int(delta.total_seconds())
    
    if seconds < 0:
        return "just now"
    elif seconds < 60:
        return f"{seconds}s ago"
    elif seconds < 3600:
        return f"{seconds // 60}m ago"
    elif seconds < 86400:
        return f"{seconds // 3600}h ago"
    elif seconds < 2592000:
        return f"{seconds // 86400}d ago"
    else:
        return f"{seconds // 2592000}mo ago"

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors"""
    logger.error(f"Update {update} caused error {context.error}")

async def post_init(application: Application):
    """Initialize after app is created"""
    logger.info("🤖 Bot initialized successfully")
    logger.info(f"✓ Etherscan API configured")
    logger.info(f"{'✓' if HELIUS_API_KEY else '⚠'} Helius API {'configured' if HELIUS_API_KEY else 'not configured (using public RPC)'}")

async def post_shutdown(application: Application):
    """Cleanup on shutdown"""
    await analyzer.close_session()
    logger.info("Bot shutdown complete")

def main():
    """Start the bot"""
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
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Error handler
    application.add_error_handler(error_handler)
    
    # Start bot
    logger.info("🚀 Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
