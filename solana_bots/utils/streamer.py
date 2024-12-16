from solana.rpc.async_api import AsyncClient
import asyncio
import websockets
from typing import List, Dict
from .constants import request
from .trader import TokenTrader
import json
from termcolor import cprint
from solders.pubkey import Pubkey #type: ignore
import base64
import os
from .base_class import BaseClass
from .coin import Coin
from sqlite3 import connect


        
class Streamer(BaseClass):
    def __init__(self, rpc_url: str):
        self.rpc_url = rpc_url
        self.coin = Coin(rpc_url)
        self.token_trader = TokenTrader(rpc_url, self.coin)
        self.active_trades: Dict[str, asyncio.Task] = {}
        super().__init__(rpc_url, max_concurrent=3)
        self.monitoring_task = asyncio.create_task(self.monitor_trades())
        
    async def monitor_trades(self):
        """
        Monitor trades and sell when profit target is met
        return: None
        """
        while True:
            try:
                cprint("Monitoring trades...", "blue")
                self.cursor.execute(
                    """
                    SELECT mint, bought_price, take_profit_percentage, bc_pk 
                    FROM trades 
                    WHERE status = 'active'
                    """
                )
                active_trades = self.cursor.fetchall() 
                cprint(f"Active trades: {len(active_trades)}", "blue")
                
                for trade in active_trades:
                    mint, bought_price, take_profit, bc_pk = trade
                    cprint(f"Mint: {mint}, Bought Price: {bought_price}, Take Profit: {take_profit}", "blue")
                    
                    # Get current coin data and price
                    coin_data = await self.coin.get_coin_data(mint)
                    if coin_data:   
                        current_price = await self.coin.get_token_price(mint)
                        cprint(f"the token was bought at {bought_price} and is now at {current_price}", "blue")
                        # Calculate profit percentage
                        profit_percentage = ((current_price - bought_price) / bought_price) * 100
                        cprint(f"the profit percentage is {profit_percentage}", "blue")
                        
                        # Update the current price and profit percentage in the database
                        self.cursor.execute(
                            """
                            UPDATE trades 
                            SET current_price = ?, profit_loss = ?
                            WHERE mint = ? AND status = 'active'
                            """,
                            (current_price, profit_percentage, mint)
                        )
                        self.db.commit()
                        
                        # If profit target met, initiate sell
                        if profit_percentage >= 10.0:
                            cprint(f"Take profit target met for {mint}! Current profit: {profit_percentage:.2f}%", "green")
                            # Create sell task
                            sell_task = asyncio.create_task(self.token_trader.sell(mint))
                            self.active_trades[mint] = sell_task
                            
                            # Wait for the sell task to complete
                            try:
                                sale_result = await sell_task
                                cprint(f"Sale result: {sale_result}", "green")
                                if sale_result:  # Assuming sell returns True on successful sale
                                    self.cursor.execute(
                                        """
                                        UPDATE trades 
                                        SET status = 'COMPLETED', sold_price = ?, sold_at = CURRENT_TIMESTAMP, profit_loss = ?
                                        WHERE mint = ? AND status = 'active'
                                        """,
                                        (current_price, profit_percentage, mint)
                                    )
                                    self.db.commit()
                                    cprint(f"Trade completed for {mint}", "green")
                                    # Remove from active trades
                                    del self.active_trades[mint]
                            except Exception as e:
                                cprint(f"Error during sale of {mint}: {e}", "red")
                        
                        # Log current profit/loss
                        cprint(f"Token {mint} current P/L: {profit_percentage:.2f}%", "yellow")
                    
            except Exception as e:
                cprint(f"Error monitoring trades: {e}", "red")
            
            await asyncio.sleep(10)
                
    
    def parse_log_data(self, log_data: str) -> tuple[str, str, str]:
        try:
            decoded = base64.b64decode(log_data.replace("Program data: ", ""))
            
            length = len(decoded)
            
            if length >= 180:
                # Extract addresses from the end of the decoded data
                user_bytes = decoded[length-32:length]
                bc_bytes = decoded[length-64:length-32]
                mint_bytes = decoded[length-96:length-64]
                
            # Convert to Solana public keys
                user = str(Pubkey(user_bytes))
                bc_pk = str(Pubkey(bc_bytes))
                mint = str(Pubkey(mint_bytes))
          
            # Only return if mint contains "pump"
                if "pump" in mint.lower():
                    return mint, bc_pk, user
                
        except Exception as e:
            print(f"Error parsing log data: {e}")
        return None, None, None
        
    def is_valid_stream(self, logs: List):
        has_init = False
        has_buy = False
        for msg in logs:
            if "InitializeMint2" in msg or "Create Metadata Accounts v3" in msg:
                has_init = True
            elif "Buy" in msg:
                has_buy = True
                break
        return has_init and has_buy
                

    async def stream_transactions(self):
        wss_url = os.getenv("WSS_HTTPS_URL")
        if not wss_url:
            raise ValueError("WSS_HTTPS_URL must be set in .env file")
        
        while True:
            try:
                async with websockets.connect(wss_url) as websocket:
                    cprint("WebSocket connected", "green")
                    cprint("👀 Monitoring for new tokens...", "green")
                    
                    await websocket.send(json.dumps(request))

                    async for message in websocket:
                        try:
                            if self.semaphore.locked():
                                cprint("Semaphore locked, skipping message", "red")
                                continue
                            parsed = json.loads(message)
                            logs = parsed.get("params", {}).get("result", {}).get("value", {}).get("logs", [])
                            
                            if not logs or not self.is_valid_stream(logs):
                                continue
                            
                            for log in logs:
                                if "Program data:" in log:
                                    mint, bc_pk, user = self.parse_log_data(log)
                                    cprint(f"Mint: {mint}, BC: {bc_pk}, User: {user}", "blue")
                                    if mint:
                                       asyncio.create_task(self.token_trader.buy(mint))
                                    
                        except json.JSONDecodeError:
                            cprint("Error decoding websocket message", "red")
                        except Exception as e:
                            cprint(f"Error processing message: {e}", "red")
                            
            except websockets.exceptions.ConnectionClosed:
                cprint("Connection closed, attempting to reconnect...", "red")
                await asyncio.sleep(5)
            except Exception as e:
                cprint(f"Error: {e}", "red")
                await asyncio.sleep(5)
            

