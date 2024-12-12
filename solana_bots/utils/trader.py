from solana.rpc.async_api import AsyncClient
import asyncio
from typing import List, Dict
from termcolor import cprint
from .base import BaseClass





class TokenTrader(BaseClass):
    def __init__(self, rpc_url: str):
      super().__init__(rpc_url)
      self.active_trades: Dict[str, asyncio.Task] = {}
      self.semaphore = asyncio.Semaphore(5)
    
    
    

   
