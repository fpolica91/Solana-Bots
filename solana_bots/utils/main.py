
from .streamer import Streamer
from .constants import *
from .config import *
import asyncio
from .coin import Coin


async def main():
  streamer = Streamer(RPC, Coin)
  await streamer.stream_transactions()

if __name__ == "__main__":
    asyncio.run(main())