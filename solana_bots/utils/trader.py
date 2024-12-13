from solana.rpc.async_api import AsyncClient
import asyncio
from typing import List, Dict
from termcolor import cprint
from .base_class import BaseClass
from .coin import Coin
from .constants import SYSTEM_PROGRAM, FEE_RECIPIENT, GLOBAL, TOKEN_PROGRAM, RENT, EVENT_AUTHORITY, PUMP_FUN_PROGRAM,ASSOC_TOKEN_ACC_PROG
from solders.keypair import Keypair #type: ignore
import struct
from solana.transaction import Signature
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price  # type: ignore
from solana.rpc.types import TokenAccountOpts, TxOpts
from .config import payer_keypair, UNIT_BUDGET, UNIT_PRICE
import struct
from solana.rpc.commitment import Processed, Confirmed
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
from solders.pubkey import Pubkey #type: ignore
import json








class TokenTrader(BaseClass):
    def __init__(self, rpc_url: str, coin_class: Coin):
        super().__init__(rpc_url)
        self.active_trades: Dict[str, asyncio.Task] = {}
        self.coin = coin_class
        self.payer_keypair = payer_keypair
        
    async def get_token_balance(self, mint_str: str) -> float | None:
        try:
            mint = Pubkey.from_string(mint_str)
            response = await self.client.get_token_accounts_by_owner_json_parsed(
                payer_keypair.pubkey(),
                TokenAccountOpts(mint=mint),
                commitment=Processed
            )
            cprint(response.value, "green")
            accounts = response.value
            if accounts:
                token_amount = accounts[0].account.data.parsed['info']['tokenAmount']['uiAmount']
                return float(token_amount)

            return None
        except Exception as e:
            cprint(f"Error fetching token balance: {e}", "red")
            return None
          
    async def confirm_txn(self, txn_sig: Signature, max_retries: int = 7, retry_interval: int = 2, operation: str = "buy") -> bool:
        retries = 1
        color = "green" if operation == "buy" else "yellow"
        cprint(f"Confirming transaction for {operation} operation...", color)
        while retries < max_retries:
            try:
                txn_res = await self.client.get_transaction(txn_sig, encoding="json", commitment=Confirmed, max_supported_transaction_version=0)
                txn_json = json.loads(txn_res.value.transaction.meta.to_json())
                cprint(txn_json, color)
                if txn_json['err'] is None:
                    cprint(f"Transaction confirmed... try count: {retries}", color)
                    return True
                
                cprint("Error: Transaction not confirmed. Retrying...", color)
                if txn_json['err']:
                    cprint("Transaction failed.", color)
                    return False
            except Exception as e:
                cprint(f"Awaiting confirmation on txn {txn_sig}... try count: {retries}", "red")
                retries += 1 
                await asyncio.sleep(retry_interval)
        
        cprint("Max retries reached. Transaction confirmation failed.", "red")
        return None
      
    async def buy(self, mint_str: str, sol_in: float = 0.001, slippage: int = 5) -> bool:
        try:
            cprint(f"Starting buy transaction for mint: {mint_str}", "green")
            if not mint_str:
                cprint("Mint is required", "red")
                return False
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
                token_accounts = await self.client.get_token_accounts_by_owner(USER, TokenAccountOpts(MINT))
                ASSOCIATED_USER = token_accounts.value[0].pubkey
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
            amount = self.coin.sol_for_tokens(sol_in, virtual_sol_reserves, virtual_token_reserves)
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
            blockhash = await self.client.get_latest_blockhash()
            
            compiled_message = MessageV0.try_compile(
                self.payer_keypair.pubkey(),
                instructions,
                [],
               blockhash.value.blockhash,
            )

            cprint("Sending transaction...", "green")
            txn_sig = await self.client.send_transaction(
                txn=VersionedTransaction(compiled_message, [self.payer_keypair]),
                opts=TxOpts(skip_preflight=True)
            )
            txn_sig = txn_sig.value
            cprint(f"Transaction Signature: {txn_sig}", "green")

            cprint("Confirming transaction...", "green")
            confirmed = await self.confirm_txn(txn_sig, operation="buy")
            
            cprint(f"Transaction confirmed: {confirmed}", "green")
            return confirmed

        except Exception as e:
            cprint(f"Error occurred during transaction: {e}", "red")
            return False

    async def sell(self, mint_str: str, percentage: int = 100, slippage: int = 5, max_retries: int = 7) -> bool:
        try:
            cprint(f"Starting sell transaction for mint: {mint_str}", "green")

            if not (1 <= percentage <= 100):
                cprint("Percentage must be between 1 and 100.", "red")
                return False

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
            ASSOCIATED_USER = get_associated_token_address(USER, MINT)

            cprint("Retrieving token balance...", "green")
            token_balance = await self.get_token_balance(mint_str)
            if token_balance == 0 or token_balance is None:
                cprint("Token balance is zero. Nothing to sell.", "red")
                return False
            cprint(f"Token Balance: {token_balance}", "green")
            
            cprint("Calculating transaction amounts...", "green")
            sol_dec = 1e9
            token_dec = 1e6
            amount = int(token_balance * token_dec)
            
            virtual_sol_reserves = coin_data.virtual_sol_reserves / sol_dec
            virtual_token_reserves = coin_data.virtual_token_reserves / token_dec
            sol_out = self.coin.tokens_for_sol(token_balance, virtual_sol_reserves, virtual_token_reserves)
            
            slippage_adjustment = 1 - (slippage / 100)
            min_sol_output = int((sol_out * slippage_adjustment) * sol_dec)
            cprint(f"Amount: {amount}, Minimum Sol Out: {min_sol_output}", "green")

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
                AccountMeta(pubkey=ASSOC_TOKEN_ACC_PROG, is_signer=False, is_writable=False),
                AccountMeta(pubkey=TOKEN_PROGRAM, is_signer=False, is_writable=False),
                AccountMeta(pubkey=EVENT_AUTHORITY, is_signer=False, is_writable=False),
                AccountMeta(pubkey=PUMP_FUN_PROGRAM, is_signer=False, is_writable=False)
            ]

            data = bytearray()
            data.extend(bytes.fromhex("33e685a4017f83ad"))
            data.extend(struct.pack('<Q', amount))
            data.extend(struct.pack('<Q', min_sol_output))
            swap_instruction = Instruction(PUMP_FUN_PROGRAM, bytes(data), keys)

            instructions = [
                set_compute_unit_limit(UNIT_BUDGET),
                set_compute_unit_price(UNIT_PRICE),
                swap_instruction,
            ]

            if percentage == 100:
                cprint("Preparing to close token account after swap...", "green")
                close_account_instruction = close_account(CloseAccountParams(TOKEN_PROGRAM, ASSOCIATED_USER, USER, USER))
                instructions.append(close_account_instruction)
            blockhash = await self.client.get_latest_blockhash()
            cprint("Compiling transaction message...", "green")
            compiled_message = MessageV0.try_compile(
                self.payer_keypair.pubkey(),
                instructions,
                [],
                blockhash.value.blockhash,
            )

            cprint("Sending transaction...", "green")
            txn_sig = await self.client.send_transaction(
                txn=VersionedTransaction(compiled_message, [self.payer_keypair]),
                opts=TxOpts(skip_preflight=False)
            )
            txn_sig = txn_sig.value
            cprint(f"Transaction Signature: {txn_sig}", "green")

            cprint("Confirming transaction...", "green")
            confirmed = await self.confirm_txn(txn_sig, max_retries=max_retries, operation="sell" )
            
            cprint(f"Transaction confirmed: {confirmed}", "green")
            return confirmed

        except Exception as e:
            cprint(f"Error occurred during transaction: {e}", "red")
            return False

   
