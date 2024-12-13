
from .streamer import Streamer
from .constants import *
from .config import *
import asyncio
import signal
from termcolor import cprint
from typing import Set

async def shutdown(signal, loop, active_trades: Set[asyncio.Task]):
    cprint(f"Received exit signal {signal.name}...", "yellow")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    cprint(f"Cancelling {len(tasks)} outstanding tasks", "yellow")
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()
    
    
async def main():
    loop = asyncio.get_running_loop()
    
    # Handle graceful shutdown
    signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
    for s in signals:
        loop.add_signal_handler(
            s, lambda s=s: asyncio.create_task(shutdown(s, loop, streamer.active_trades))
        )
    
    streamer = Streamer(RPC)
    try:
        await streamer.stream_transactions()
    finally:
        await streamer.client.close()  # Clean up client connection

if __name__ == "__main__":
    asyncio.run(main())