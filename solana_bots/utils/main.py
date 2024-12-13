
from .streamer import Streamer
from .constants import *
from .config import *
import asyncio



async def main():
  streamer = Streamer(RPC)
  await streamer.stream_transactions()

if __name__ == "__main__":
    asyncio.run(main())