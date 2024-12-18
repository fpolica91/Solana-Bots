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

        
class Streamer(BaseClass):
    def __init__(self, rpc_url: str):
        self.rpc_url = rpc_url
        self.coin = Coin(rpc_url)
        self.token_trader = TokenTrader(rpc_url, self.coin)
        self.active_trades: Dict[str, asyncio.Task] = {}
        super().__init__(rpc_url, max_concurrent=2)
        self.monitoring_task = asyncio.create_task(self.monitor_trades())
        
    async def monitor_trades(self):
        while True:
            try:
                current_time = asyncio.get_event_loop().time()
                for mint, task in list(self.active_trades.items()):
                    if not task.done() and (current_time - task.get_coro().cr_frame.f_locals.get('start_time', current_time)) > 300:
                        cprint(f"Trade {mint} has been active for more than 300 seconds, cancelling...", "red")
                        task.cancel()
                        del self.active_trades[mint]
            except Exception as e:
                cprint(f"Error monitoring trades: {e}", "red")
            await asyncio.sleep(60) 
                
    
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
        for msg in logs:
            if "InitializeMint2" in msg or "Create Metadata Accounts v3" in msg:
                has_init = True
                break
        return has_init
                
    async def handle_token_trade(self, mint: str):
        """Handle complete trade cycle for a token"""
        if mint in self.active_trades:
            cprint(f"Trade already active for {mint}", "red")
            return
        
        try:
            self.active_trades[mint] = asyncio.current_task()
            async with self.semaphore:
                
                buy_succes = await self.token_trader.buy(mint)
                if not buy_succes:
                    cprint(f"Failed to buy {mint}", "red")
                    return
                
                await asyncio.sleep(30)
                
                # Aggressive sell retry logic
                for attempt in range(10):
                    try:
                        sale_response = await self.token_trader.sell(mint)
                        if sale_response:
                            cprint(f"Successfully sold {mint} on attempt {attempt + 1}", "magenta")
                            break
                        
                        await asyncio.sleep(5)
                            
                    except Exception as e:
                        cprint(f"Sale attempt {attempt + 1} failed with error: {e}", "red")
                        if attempt == 9:
                            cprint(f"Failed to sell {mint} after 10 attempts", "red")
                        elif attempt < 9:
                            backoff = min(2 * (2 ** attempt), 10)
                            await asyncio.sleep(backoff)
        except Exception as e:
            cprint(f"Critical error trading {mint}: {e}", "red")
        finally:
            if mint in self.active_trades:
                del self.active_trades[mint]
       
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
                                       asyncio.create_task(self.handle_token_trade(mint))
                                    
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
            

