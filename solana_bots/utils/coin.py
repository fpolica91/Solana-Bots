from dataclasses import dataclass
from typing import Optional
from construct import Flag, Int64ul, Padding, Struct
from solders.pubkey import  Pubkey  # type: ignore
from spl.token.instructions import get_associated_token_address
from .base_class import BaseClass
from termcolor import cprint
from .constants import PUMP_FUN_PROGRAM
from solana.rpc.types import TokenAccountOpts, TxOpts
from solana.rpc.commitment import Processed, Confirmed
from solders.keypair import Keypair #type: ignore

@dataclass
class CoinData:
    mint: Pubkey
    bonding_curve: Pubkey
    associated_bonding_curve: Pubkey
    virtual_token_reserves: int
    virtual_sol_reserves: int
    token_total_supply: int
    complete: bool
    
    
class Coin(BaseClass):
    def __init__(self, rpc_url: str):
      super().__init__(rpc_url)
    
    async def get_coin_data(self, mint_str: str) -> Optional[CoinData]:
        cprint(f"Mint: {mint_str}", "green")
        bonding_curve, associated_bonding_curve = await self.derive_bonding_curve_accounts(mint_str)
        if not all([bonding_curve, associated_bonding_curve]):
            return None

        virtual_reserves = await self.get_virtual_reserves(bonding_curve)
        if virtual_reserves is None:
            return None

        try:
            return CoinData(
                mint=Pubkey.from_string(mint_str),
                bonding_curve=bonding_curve,
                associated_bonding_curve=associated_bonding_curve,
                virtual_token_reserves=int(virtual_reserves.virtualTokenReserves),
                virtual_sol_reserves=int(virtual_reserves.virtualSolReserves),
                token_total_supply=int(virtual_reserves.tokenTotalSupply),
              complete=bool(virtual_reserves.complete),
        )
        except Exception as e:
            print(e)
            return None

    
    async def derive_bonding_curve_accounts(self, mint: str):
      try:
        mint = Pubkey.from_string(mint)
        bonding_curve, _ = Pubkey.find_program_address(
          ["bonding-curve".encode(), bytes(mint)],
          PUMP_FUN_PROGRAM
        )
        associated_bonding_curve = get_associated_token_address(bonding_curve, mint)
        return bonding_curve, associated_bonding_curve
      except Exception as e:
        cprint(f"Error getting coin data: {e}", "red")
        return None, None 
      
    async def get_virtual_reserves(self, bonding_curve: Pubkey):
      bonding_curve_struct = Struct(
        Padding(8),
        "virtualTokenReserves" / Int64ul,
        "virtualSolReserves" / Int64ul,
        "realTokenReserves" / Int64ul,
        "realSolReserves" / Int64ul,
        "tokenTotalSupply" / Int64ul,
        "complete" / Flag
      )
      try:
        account_info = await self.client.get_account_info(bonding_curve)
        
        if not account_info or not account_info.value:
            cprint(f"No account info found for bonding curve: {bonding_curve}", "red")
            return None
            
        data = account_info.value.data
        if not data:
            cprint(f"No data found in account info for bonding curve: {bonding_curve}", "red")
            return None
            
        parsed_data = bonding_curve_struct.parse(data)
        return parsed_data
      except Exception as e:
        cprint(f"Error deriving bonding curve accounts: {e}", "red")
        return None
    
    def sol_for_tokens(self, sol_spent: int, sol_reserves: int, token_reserves: int):
        new_sol_reserves = sol_reserves + sol_spent
        new_token_reserves = (sol_reserves * token_reserves) / new_sol_reserves
        token_received = token_reserves - new_token_reserves
        return token_received
     
    def tokens_for_sol(self,tokens_to_sell: int, sol_reserves: int, token_reserves: int):
        new_token_reserves = token_reserves + tokens_to_sell
        new_sol_reserves = (sol_reserves * token_reserves) / new_token_reserves
        sol_received = sol_reserves - new_sol_reserves
        return sol_received
    
    async def get_token_price(self, mint_str: str):
        coin_data = await self.get_coin_data(mint_str)
        if coin_data is None:
            return None
      
        sol_reserves = coin_data.virtual_sol_reserves / 1e9
        token_reserves = coin_data.virtual_token_reserves / 1e6
        
        try:
            price = sol_reserves / token_reserves
            return price
        except ZeroDivisionError:
            return None
        
    async def get_token_balance(self, mint_str: str, payer_keypair: Keypair) -> float | None:
        try:
            mint = Pubkey.from_string(mint_str)
            response = await self.client.get_token_accounts_by_owner_json_parsed(
                payer_keypair.pubkey(),
                TokenAccountOpts(mint=mint),
                commitment=Processed
            )
            
            accounts = response.value
            if accounts:
                token_amount = accounts[0].account.data.parsed['info']['tokenAmount']['uiAmount']
                return float(token_amount)

            return None
        except Exception as e:
            cprint(f"Error fetching token balance: {e}", "red")
            return None


