from solana.rpc.async_api import AsyncClient
import asyncio
from typing import List, Dict
from termcolor import cprint
from .base import BaseClass
from .coin import Coin
from .constants import SYSTEM_PROGRAM, FEE_RECIPIENT, GLOBAL, TOKEN_PROGRAM, RENT, EVENT_AUTHORITY, PUMP_FUN_PROGRAM
from solders.keypair import Keypair #type: ignore
import struct
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price  # type: ignore
from solana.rpc.types import TokenAccountOpts, TxOpts
from .config import payer_keypair
import struct
from solana.transaction import AccountMeta
from spl.token.instructions import (
    CloseAccountParams,
    close_account,
    create_associated_token_account,
    get_associated_token_address,
)
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price  # type: ignore
from solders.instruction import Instruction  # type: ignore
from solders.message import MessageV0  # type: ignore
from solders.transaction import VersionedTransaction  # type: ignore







class TokenTrader(BaseClass):
    def __init__(self, rpc_url: str, coin_class: Coin):
        super().__init__(rpc_url)
        self.active_trades: Dict[str, asyncio.Task] = {}
        self.semaphore = asyncio.Semaphore(5)
        self.coin = coin_class
        self.payer_keypair = payer_keypair
      
    async def buy(self, mint_str: str, sol_in: float = 0.001, slippage: int = 5) -> bool:
        try:
            cprint(f"Starting buy transaction for mint: {mint_str}", "green")

            coin_data = await self.coin.get_coin_data(mint_str)
            
            if not coin_data:
                cprint("Failed to retrieve coin data.", "red")
                return False

            if coin_data.complete:
                cprint("Warning: This token has bonded and is only tradable on Raydium.", "red")
                return False

            MINT = coin_data.mint
            BONDING_CURVE = coin_data.bonding_curve
            ASSOCIATED_BONDING_CURVE = coin_data.associated_bonding_curve
            USER = self.payer_keypair.pubkey()

            cprint("Fetching or creating associated token account...", "green")
            try:
                ASSOCIATED_USER = self.client.get_token_accounts_by_owner(USER, TokenAccountOpts(MINT)).value[0].pubkey
                token_account_instruction = None
                cprint(f"Token account found: {ASSOCIATED_USER}", "green")
            except:
                ASSOCIATED_USER = get_associated_token_address(USER, MINT)
                token_account_instruction = create_associated_token_account(USER, USER, MINT)
                cprint(f"Creating token account : {ASSOCIATED_USER}", "green")

            cprint("Calculating transaction amounts...", "green")
            sol_dec = 1e9
            token_dec = 1e6
            virtual_sol_reserves = coin_data.virtual_sol_reserves / sol_dec
            virtual_token_reserves = coin_data.virtual_token_reserves / token_dec
            amount = sol_for_tokens(sol_in, virtual_sol_reserves, virtual_token_reserves)
            amount = int(amount * token_dec)
            
            slippage_adjustment = 1 + (slippage / 100)
            max_sol_cost = int((sol_in * slippage_adjustment) * sol_dec)
            cprint(f"Amount: {amount}, Max Sol Cost: {max_sol_cost}", "green")

            cprint("Creating swap instructions...", "green")
            keys = [
                AccountMeta(pubkey=GLOBAL, is_signer=False, is_writable=False),
                AccountMeta(pubkey=FEE_RECIPIENT, is_signer=False, is_writable=True),
                AccountMeta(pubkey=MINT, is_signer=False, is_writable=False),
                AccountMeta(pubkey=BONDING_CURVE, is_signer=False, is_writable=True),
                AccountMeta(pubkey=ASSOCIATED_BONDING_CURVE, is_signer=False, is_writable=True),
                AccountMeta(pubkey=ASSOCIATED_USER, is_signer=False, is_writable=True),
                AccountMeta(pubkey=USER, is_signer=True, is_writable=True),
                AccountMeta(pubkey=SYSTEM_PROGRAM, is_signer=False, is_writable=False),
                AccountMeta(pubkey=TOKEN_PROGRAM, is_signer=False, is_writable=False),
                AccountMeta(pubkey=RENT, is_signer=False, is_writable=False),
                AccountMeta(pubkey=EVENT_AUTHORITY, is_signer=False, is_writable=False),
                AccountMeta(pubkey=PUMP_FUN_PROGRAM, is_signer=False, is_writable=False)
            ]

            data = bytearray()
            data.extend(bytes.fromhex("66063d1201daebea"))
            data.extend(struct.pack('<Q', amount))
            data.extend(struct.pack('<Q', max_sol_cost))
            swap_instruction = Instruction(PUMP_FUN_PROGRAM, bytes(data), keys)

            instructions = [
                set_compute_unit_limit(UNIT_BUDGET),
                set_compute_unit_price(UNIT_PRICE),
            ]
            if token_account_instruction:
                instructions.append(token_account_instruction)
            instructions.append(swap_instruction)

            cprint("Compiling transaction message...", "green")
            compiled_message = MessageV0.try_compile(
                self.payer_keypair.pubkey(),
                instructions,
                [],
                self.client.get_latest_blockhash().value.blockhash,
            )

            cprint("Sending transaction...", "green")
            txn_sig = self.client.send_transaction(
                txn=VersionedTransaction(compiled_message, [self.payer_keypair]),
                opts=TxOpts(skip_preflight=True)
            ).value
            cprint(f"Transaction Signature: {txn_sig}", "green")

            cprint("Confirming transaction...", "green")
            confirmed = await self.confirm_txn(txn_sig)
            
            cprint(f"Transaction confirmed: {confirmed}", "green")
            return confirmed

        except Exception as e:
            cprint(f"Error occurred during transaction: {e}", "red")
            return False

    async def sell(self):
        pass

   
