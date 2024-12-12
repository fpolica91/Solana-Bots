
from solders.keypair import Keypair #type: ignore
import os
PRIV_KEY = os.getenv("KEY_PAIR")
RPC = os.getenv("RPC_HTTPS_URL")
UNIT_BUDGET =  100_000
UNIT_PRICE =  100_000
payer_keypair =  Keypair.from_base58_string(os.getenv("KEY_PAIR"))
# payer_keypair = Keypair.from_base58_string(PRIV_KEY)