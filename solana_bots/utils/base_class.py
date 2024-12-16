from solana.rpc.async_api import AsyncClient
import asyncio
from sqlite3 import connect

class BaseClass:
    def __init__(self, rpc_url: str, max_concurrent: int = 5):
        self.rpc_url = rpc_url
        self.client = AsyncClient(rpc_url)
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.db = connect("trades.db")
        self.cursor = self.db.cursor()
        self.create_table_if_not_exists()
    def create_table_if_not_exists(self):
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                mint TEXT,
                bc_pk TEXT,
                take_profit_percentage FLOAT,
                user TEXT,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                status TEXT,
                current_price FLOAT,
                bought_price FLOAT,
                bought_amount FLOAT,
                sold_price FLOAT,
                profit_loss FLOAT
            )
            """
        )
        self.db.commit()