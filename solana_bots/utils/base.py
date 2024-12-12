from solana.rpc.async_api import AsyncClient
import asyncio
import websockets
from typing import List
from .constants import request
import json
from termcolor import cprint
from solders.pubkey import Pubkey #type: ignore
import base64
import os
class BaseClass:
    def __init__(self, rpc_url: str, max_concurrent: int = 5):
        self.rpc_url = rpc_url
        self.client = AsyncClient(rpc_url)
        self.semaphore = asyncio.Semaphore(max_concurrent)
        
        
class Streamer(BaseClass):
    def __init__(self, rpc_url: str):
        self.rpc_url = rpc_url
        super().__init__(rpc_url, max_concurrent=5)
       
    
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
        
    async def stream_transactions(self):
        if not self.rpc_url:
            raise ValueError("WSS_HTTPS_URL must be set in .env file")
    
        while True:
            try:
                async with websockets.connect(self.rpc_url) as websocket:
                    cprint("WebSocket connected", "green")
                    cprint("👀 Monitoring for new tokens...", "green")
                    
                    await websocket.send(json.dumps(request))

                    async for message in websocket:
                        try:
                            if self.semaphore.locked():
                                cprint("Semaphore locked, skipping message", "yellow")
                                continue
                            parsed = json.loads(message)
                            logs = parsed.get("params", {}).get("result", {}).get("value", {}).get("logs", [])
                            
                            if not logs or not self.is_valid_stream(logs):
                                continue
                            
                            for log in logs:
                                if "Program data:" in log:
                                    mint, bc_pk, user = self.parse_log_data(log)
                                    cprint(f"Mint: {mint}, BC: {bc_pk}, User: {user}", "green")
                                    
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
            
            
async def main():
    streamer = Streamer(os.getenv("WSS_HTTPS_URL"))
    await streamer.stream_transactions()
    # base = BaseClass("https://api.mainnet-beta.solana.com")
    # tasks = [base.test(i) for i in range(100)]
    # await asyncio.gather(*tasks)
    
if __name__ == "__main__":
    asyncio.run(main())
