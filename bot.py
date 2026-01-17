import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from collections import defaultdict
import aiohttp
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
ETHERSCAN_API_KEY = os.environ.get('ETHERSCAN_API_KEY', '')
HELIUS_API_KEY = os.environ.get('HELIUS_API_KEY', '')
COINGECKO_API_KEY = os.environ.get('COINGECKO_API_KEY', '')

# Log what we loaded (without showing full keys)
logger.info(f"Loaded TELEGRAM_BOT_TOKEN: {'✓' if TELEGRAM_BOT_TOKEN else '✗'}")
logger.info(f"Loaded ETHERSCAN_API_KEY: {'✓' if ETHERSCAN_API_KEY else '✗'}")
logger.info(f"Loaded HELIUS_API_KEY: {'✓' if HELIUS_API_KEY else '✗'} (length: {len(HELIUS_API_KEY)})")
logger.info(f"Loaded COINGECKO_API_KEY: {'✓' if COINGECKO_API_KEY else '✗'}")

class WalletAnalyzer:
    def __init__(self):
        self.session = None
        self.price_cache = {}
        
    async def init_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def close_session(self):
        if self.session:
            await self.session.close()
    
    async def get_sol_price(self, timestamp: Optional[int] = None) -> float:
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
    
    async def get_eth_price(self, timestamp: Optional[int] = None) -> float:
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
    
    async def detect_chain(self, address: str) -> str:
        if len(address) == 42 and address.startswith('0x'):
            return 'ethereum'
        elif len(address) >= 32 and len(address) <= 44 and not address.startswith('0x'):
            return 'solana'
        else:
            return 'unknown'
    
    async def calculate_token_pnl(self, token_txs: List, address: str, days: Optional[int] = None) -> Dict:
        now = datetime.now()
        cutoff = now - timedelta(days=days) if days else datetime.fromtimestamp(0)
        
        token_positions = {}
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
            
            trades.append({
                'token': token_symbol,
                'type': 'BUY' if is_buy else 'SELL',
                'amount': value,
                'time': tx_time,
                'hash': tx['hash']
            })
        
        total_pnl = 0
        most_profitable = None
        max_profit = float('-inf')
        
        for token_addr, pos in token_positions.items():
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
    
    async def get_solana_token_metadata(self, mint_address: str) -> str:
        """Get token symbol from mint address using Helius or Jupiter"""
        await self.init_session()
        
        try:
            # Try Jupiter token list first (public, no auth needed)
            url = "https://tokens.jup.ag/token/" + mint_address
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    symbol = data.get('symbol')
                    if symbol:
                        return symbol
            
            # If Helius available, try DAS API
            if HELIUS_API_KEY:
                url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
                payload = {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "getAsset",
                    "params": {"id": mint_address}
                }
                async with self.session.post(url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        result = data.get('result', {})
                        content = result.get('content', {})
                        metadata = content.get('metadata', {})
                        symbol = metadata.get('symbol')
                        if symbol:
                            return symbol
            
            # Fallback to shortened mint address
            return mint_address[:6] + '...'
            
        except Exception as e:
            logger.error(f"Error getting token metadata: {e}")
            return mint_address[:6] + '...' if mint_address else 'UNKNOWN'
    
    async def analyze_solana_transactions_detailed(self, address: str, period_days: Optional[int] = None):
        await self.init_session()
        
        if not HELIUS_API_KEY:
            logger.warning("Helius API key not set - cannot get detailed Solana P&L")
            return None
        
        try:
            now = datetime.now()
            cutoff = now - timedelta(days=period_days) if period_days else datetime.fromtimestamp(0)
            
            # Use correct Helius endpoint with pagination
            url = f"https://api.helius.xyz/v0/addresses/{address}/transactions"
            params = {
                'api-key': HELIUS_API_KEY,
                'limit': 100,
                'type': 'SWAP'  # Focus on swap transactions
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    logger.error(f"Helius API error: {response.status}")
                    return None
                transactions = await response.json()
            
            if not transactions or not isinstance(transactions, list):
                logger.warning("No transactions returned from Helius")
                return None
            
            token_balances = defaultdict(lambda: {'in': 0, 'out': 0, 'first_time': None, 'last_time': None, 'symbol': 'UNKNOWN'})
            sol_in = 0
            sol_out = 0
            swap_count = 0
            most_profitable_token = None
            max_token_profit = float('-inf')
            
            for tx in transactions:
                timestamp = tx.get('timestamp', 0)
                tx_time = datetime.fromtimestamp(timestamp)
                
                # Apply time filter
                if tx_time < cutoff:
                    continue
                
                # Get token transfers
                token_transfers = tx.get('tokenTransfers', [])
                
                for transfer in token_transfers:
                    mint = transfer.get('mint', '')
                    amount = float(transfer.get('tokenAmount', 0))
                    from_addr = transfer.get('fromUserAccount', '')
                    to_addr = transfer.get('toUserAccount', '')
                    
                    # Try to get symbol from transfer data first
                    symbol = transfer.get('tokenSymbol') or transfer.get('symbol')
                    
                    if from_addr == address:
                        token_balances[mint]['out'] += amount
                        if symbol:
                            token_balances[mint]['symbol'] = symbol
                        token_balances[mint]['last_time'] = tx_time
                    elif to_addr == address:
                        token_balances[mint]['in'] += amount
                        if symbol:
                            token_balances[mint]['symbol'] = symbol
                        if not token_balances[mint]['first_time']:
                            token_balances[mint]['first_time'] = tx_time
                        token_balances[mint]['last_time'] = tx_time
                
                # Track SOL movements
                native_transfers = tx.get('nativeTransfers', [])
                for transfer in native_transfers:
                    amount = float(transfer.get('amount', 0)) / 1e9
                    from_addr = transfer.get('fromUserAccount', '')
                    to_addr = transfer.get('toUserAccount', '')
                    
                    if from_addr == address:
                        sol_out += amount
                    elif to_addr == address:
                        sol_in += amount
                
                # Count swaps
                tx_type = tx.get('type', '')
                if tx_type in ['SWAP', 'TRADE']:
                    swap_count += 1
            
            # Fetch token metadata for any unknown symbols
            unknown_tokens = [mint for mint, data in token_balances.items() 
                            if data['symbol'] == 'UNKNOWN' and mint]
            
            if unknown_tokens:
                logger.info(f"Fetching metadata for {len(unknown_tokens)} tokens...")
                for mint in unknown_tokens[:10]:  # Limit to 10 to avoid rate limits
                    symbol = await self.get_solana_token_metadata(mint)
                    token_balances[mint]['symbol'] = symbol
            
            # Calculate most profitable token
            for mint, balance in token_balances.items():
                profit = balance['in'] - balance['out']
                if profit > max_token_profit and balance['in'] > 0:
                    max_token_profit = profit
                    hold_days = 0
                    if balance['first_time'] and balance['last_time']:
                        hold_days = (balance['last_time'] - balance['first_time']).days
                    
                    most_profitable_token = {
                        'token': balance['symbol'],
                        'pnl': profit,
                        'hold_days': hold_days
                    }
            
            # Calculate SOL P&L in USD
            current_sol_price = await self.get_sol_price()
            sol_pnl = sol_in - sol_out
            sol_pnl_usd = sol_pnl * current_sol_price
            
            logger.info(f"Solana analysis complete: {swap_count} swaps, {len(token_balances)} tokens")
            
            return {
                'sol_pnl': sol_pnl,
                'sol_pnl_usd': sol_pnl_usd,
                'swap_count': swap_count,
                'most_profitable': most_profitable_token,
                'active_tokens': len([b for b in token_balances.values() if b['in'] > 0])
            }
            
        except Exception as e:
            logger.error(f"Error in detailed Solana analysis: {e}")
            return None
    
    async def analyze_ethereum_wallet(self, address: str, period_days: Optional[int] = None) -> Dict:
        await self.init_session()
        
        try:
            tx_url = f"https://api.etherscan.io/api?module=account&action=txlist&address={address}&startblock=0&endblock=99999999&sort=desc&apikey={ETHERSCAN_API_KEY}"
            async with self.session.get(tx_url) as response:
                tx_data = await response.json()
            
            if tx_data['status'] != '1':
                return {'error': 'Failed to fetch transactions'}
            
            transactions = tx_data['result']
            
            token_url = f"https://api.etherscan.io/api?module=account&action=tokentx&address={address}&startblock=0&endblock=99999999&sort=desc&apikey={ETHERSCAN_API_KEY}"
            async with self.session.get(token_url) as response:
                token_data = await response.json()
            
            token_txs = token_data['result'] if token_data['status'] == '1' else []
            
            balance_url = f"https://api.etherscan.io/api?module=account&action=balance&address={address}&tag=latest&apikey={ETHERSCAN_API_KEY}"
            async with self.session.get(balance_url) as response:
                balance_data = await response.json()
            
            eth_balance = int(balance_data['result']) / 1e18 if balance_data['status'] == '1' else 0
            
            now = datetime.now()
            cutoff = now - timedelta(days=period_days) if period_days else datetime.fromtimestamp(0)
            
            period_txs = [tx for tx in transactions if datetime.fromtimestamp(int(tx['timeStamp'])) > cutoff]
            period_token_txs = [tx for tx in token_txs if datetime.fromtimestamp(int(tx['timeStamp'])) > cutoff]
            
            eth_in = sum(int(tx['value']) for tx in period_txs if tx['to'].lower() == address.lower()) / 1e18
            eth_out = sum(int(tx['value']) for tx in period_txs if tx['from'].lower() == address.lower()) / 1e18
            
            current_eth_price = await self.get_eth_price()
            eth_pnl_usd = (eth_in - eth_out) * current_eth_price
            
            token_pnl_data = await self.calculate_token_pnl(period_token_txs, address, period_days)
            
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
        await self.init_session()
        
        try:
            if HELIUS_API_KEY:
                rpc_url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
            else:
                rpc_url = "https://api.mainnet-beta.solana.com"
            
            balance_payload = {"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [address]}
            
            async with self.session.post(rpc_url, json=balance_payload) as response:
                balance_data = await response.json()
            
            balance_lamports = balance_data.get('result', {}).get('value', 0)
            sol_balance = balance_lamports / 1e9
            
            sig_payload = {"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress", "params": [address, {"limit": 1000}]}
            
            async with self.session.post(rpc_url, json=sig_payload) as response:
                sig_data = await response.json()
            
            signatures = sig_data.get('result', [])
            
            now = datetime.now()
            cutoff = now - timedelta(days=period_days) if period_days else datetime.fromtimestamp(0)
            
            period_sigs = [sig for sig in signatures if datetime.fromtimestamp(sig.get('blockTime', 0)) > cutoff]
            
            current_sol_price = await self.get_sol_price()
            
            last_active = datetime.fromtimestamp(signatures[0].get('blockTime', 0)) if signatures else None
            
            detailed_pnl = await self.analyze_solana_transactions_detailed(address, period_days)
            
            result = {
                'chain': 'Solana',
                'address': address,
                'last_active': last_active,
                'current_balance': sol_balance,
                'current_balance_usd': sol_balance * current_sol_price,
                'total_transactions': len(period_sigs),
                'period_days': period_days or 'All Time',
            }
            
            if detailed_pnl:
                result.update({
                    'sol_pnl': detailed_pnl['sol_pnl'],
                    'sol_pnl_usd': detailed_pnl['sol_pnl_usd'],
                    'swap_count': detailed_pnl['swap_count'],
                    'most_profitable': detailed_pnl['most_profitable'],
                    'active_tokens': detailed_pnl['active_tokens']
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing Solana wallet: {e}")
            return {'error': str(e)}
    
    async def analyze_wallet(self, address: str, period_days: Optional[int] = None) -> Dict:
        chain = await self.detect_chain(address)
        
        if chain == 'ethereum':
            return await self.analyze_ethereum_wallet(address, period_days)
        elif chain == 'solana':
            return await self.analyze_solana_wallet(address, period_days)
        else:
            return {'error': 'Unknown chain or invalid address'}
    
    async def analyze_multiple_wallets(self, addresses: List[str], period_days: Optional[int] = None) -> List[Dict]:
        tasks = [self.analyze_wallet(addr, period_days) for addr in addresses]
        results = await asyncio.gather(*tasks)
        return results

analyzer = WalletAnalyzer()
user_contexts = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = """
🤖 *Wallet Analyzer Bot v2.0*

Advanced crypto wallet analysis with P&L tracking!

*Features:*
💰 Profit/Loss calculations
📊 Time-based analysis (7/30/60 days)
🏆 Most profitable trades
⏱️ Hold time tracking
💵 USD valuations
🔄 Swap & trade counting

*Commands:*
/analyze <addresses> - Full analysis with P&L
/help - Show detailed help

*Example:*
`/analyze 0x742d35Cc6634C0532925a3b844Bc454e4438f44e`

After analysis, click buttons to check different timeframes!

*Supports:* Ethereum & Solana 🔥
"""
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📚 *Wallet Analyzer Help*

*Usage:*
`/analyze <wallet_address>`

*Multiple Wallets:*
`/analyze addr1 addr2 addr3`

*What You Get:*
• 💰 Total P&L in USD
• 📈 Period analysis (7/30/60d)
• 🏆 Most profitable trades
• ⏱️ Hold time for winners
• 💵 Current portfolio value
• 🔄 Swap/trade counts

*Interactive Buttons:*
After analysis:
• 7D - Last week
• 30D - Last month
• 60D - Two months
• All - Complete history

*Chains:*
✅ Ethereum - Full P&L tracking
✅ Solana - Full P&L (with Helius)

*Note:* Helius API key recommended for detailed Solana P&L!
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "⚠️ Please provide wallet address(es)\n\n"
            "*Example:*\n"
            "`/analyze 0x742d35Cc6634C0532925a3b844Bc454e4438f44e`",
            parse_mode='Markdown'
        )
        return
    
    addresses_text = ' '.join(context.args)
    addresses = [addr.strip() for addr in addresses_text.replace(',', ' ').split() if addr.strip()]
    
    if len(addresses) > 15:
        await update.message.reply_text("⚠️ Maximum 15 wallets. Analyzing first 15...")
        addresses = addresses[:15]
    
    user_id = update.effective_user.id
    user_contexts[user_id] = {'addresses': addresses}
    
    processing_msg = await update.message.reply_text(
        f"🔍 Analyzing {len(addresses)} wallet(s)...\n"
        f"⏳ Fetching transactions, prices, and P&L data...\n"
        f"⚡ This may take 15-30 seconds..."
    )
    
    try:
        results = await analyzer.analyze_multiple_wallets(addresses)
        await send_analysis_results(update, results, addresses, None)
        await processing_msg.delete()
        
    except Exception as e:
        logger.error(f"Error in analyze_command: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")
        try:
            await processing_msg.delete()
        except:
            pass

async def send_analysis_results(update: Update, results: List[Dict], addresses: List[str], period_days: Optional[int]):
    period_label = f"{period_days}D" if period_days else "All Time"
    response = f"📊 *Wallet Analysis - {period_label}*\n\n"
    
    for i, result in enumerate(results, 1):
        if 'error' in result:
            response += f"❌ *Wallet {i}*\n`{addresses[i-1][:12]}...`\nError: {result['error']}\n\n"
            continue
        
        response += f"{'='*35}\n"
        response += f"✅ *Wallet {i}* - {result['chain']}\n"
        response += f"📍 `{result['address'][:8]}...{result['address'][-6:]}`\n\n"
        
        if result.get('last_active'):
            time_ago = datetime.now() - result['last_active']
            response += f"🕐 Last Active: {format_time_ago(time_ago)}\n"
        
        if result.get('last_trade'):
            trade_ago = datetime.now() - result['last_trade']
            response += f"💱 Last Trade: {format_time_ago(trade_ago)}\n"
        
        response += f"\n💰 *Current Holdings:*\n"
        currency = 'ETH' if result['chain'] == 'Ethereum' else 'SOL'
        response += f"   {result['current_balance']:.4f} {currency}\n"
        
        if 'current_balance_usd' in result:
            response += f"   ≈ ${result['current_balance_usd']:.2f} USD\n"
        
        if result['chain'] == 'Ethereum':
            response += f"\n📈 *P&L Analysis:*\n"
            
            eth_pnl = result.get('eth_pnl', 0)
            eth_pnl_usd = result.get('eth_pnl_usd', 0)
            pnl_emoji = "📈" if eth_pnl_usd > 0 else "📉" if eth_pnl_usd < 0 else "➖"
            
            response += f"   {pnl_emoji} ETH: {eth_pnl:+.4f} ETH (${eth_pnl_usd:+.2f})\n"
            
            token_pnl = result.get('token_pnl', {})
            if token_pnl.get('total_trades', 0) > 0:
                response += f"   📝 Token Trades: {token_pnl['total_trades']}\n"
                response += f"   🎯 Active Positions: {token_pnl['positions']}\n"
                
                if token_pnl.get('most_profitable'):
                    mp = token_pnl['most_profitable']
                    response += f"\n🏆 *Most Profitable:*\n"
                    response += f"   Token: {mp['token']}\n"
                    response += f"   P&L: {mp['pnl']:+.2f} tokens\n"
                    response += f"   Hold Time: {mp['hold_days']} days\n"
        
        elif result['chain'] == 'Solana':
            if 'sol_pnl' in result:
                response += f"\n📈 *P&L Analysis:*\n"
                sol_pnl = result.get('sol_pnl', 0)
                sol_pnl_usd = result.get('sol_pnl_usd', 0)
                pnl_emoji = "📈" if sol_pnl_usd > 0 else "📉" if sol_pnl_usd < 0 else "➖"
                
                response += f"   {pnl_emoji} SOL: {sol_pnl:+.4f} SOL (${sol_pnl_usd:+.2f})\n"
                
                if result.get('swap_count', 0) > 0:
                    response += f"   🔄 Swaps/Trades: {result['swap_count']}\n"
                    response += f"   🎯 Active Tokens: {result.get('active_tokens', 0)}\n"
                
                if result.get('most_profitable'):
                    mp = result['most_profitable']
                    response += f"\n🏆 *Most Profitable:*\n"
                    response += f"   Token: {mp['token']}\n"
                    response += f"   P&L: {mp['pnl']:+.4f} tokens\n"
                    response += f"   Hold Time: {mp['hold_days']} days\n"
            else:
                response += f"\n⚠️ *Note:* Detailed P&L requires Helius API key\n"
        
        response += f"\n📊 *Activity ({period_label}):*\n"
        response += f"   Total Txs: {result.get('total_transactions', 0)}\n"
        
        if result['chain'] == 'Ethereum':
            response += f"   Token Transfers: {result.get('total_token_transfers', 0)}\n"
        
        response += "\n"
    
    keyboard = [
        [
            InlineKeyboardButton("7D", callback_data="period_7"),
            InlineKeyboardButton("30D", callback_data="period_30"),
            InlineKeyboardButton("60D", callback_data="period_60"),
            InlineKeyboardButton("All Time", callback_data="period_all")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if len(response) > 4096:
        chunks = [response[i:i+4096] for i in range(0, len(response), 4096)]
        for chunk in chunks[:-1]:
            await update.effective_message.reply_text(chunk, parse_mode='Markdown')
        await update.effective_message.reply_text(chunks[-1], parse_mode='Markdown', reply_markup=reply_markup)
    else:
        await update.effective_message.reply_text(response, parse_mode='Markdown', reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in user_contexts:
        await query.edit_message_text("❌ Session expired. Please run /analyze again.")
        return
    
    period_map = {'period_7': 7, 'period_30': 30, 'period_60': 60, 'period_all': None}
    
    period_days = period_map.get(query.data)
    addresses = user_contexts[user_id]['addresses']
    
    period_label = query.data.split('_')[1].upper()
    await query.edit_message_text(f"🔍 Re-analyzing for {period_label} period...")
    
    try:
        results = await analyzer.analyze_multiple_wallets(addresses, period_days)
        await send_analysis_results(update, results, addresses, period_days)
        
    except Exception as e:
        logger.error(f"Error in button_callback: {e}")
        await query.edit_message_text(f"❌ Error: {str(e)}")

def format_time_ago(delta: timedelta) -> str:
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
    logger.error(f"Update {update} caused error {context.error}")

async def post_init(application: Application):
    logger.info("🤖 Bot initialized successfully")
    logger.info(f"✓ Etherscan API configured")
    logger.info(f"{'✓' if HELIUS_API_KEY else '⚠'} Helius API {'configured (FULL P&L ENABLED)' if HELIUS_API_KEY else 'not configured (limited Solana P&L)'}")
    logger.info(f"✓ CoinGecko API ready for price data")

async def post_shutdown(application: Application):
    await analyzer.close_session()
    logger.info("Bot shutdown complete")

def main():
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("analyze", analyze_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    application.add_error_handler(error_handler)
    
    logger.info("🚀 Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
