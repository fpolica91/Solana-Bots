from solana.rpc.async_api import AsyncClient
import asyncio

class BaseClass:
    def __init__(self, rpc_url: str, max_concurrent: int = 5):
        self.rpc_url = rpc_url
        self.client = AsyncClient(rpc_url)
        self.semaphore = asyncio.Semaphore(max_concurrent)
        