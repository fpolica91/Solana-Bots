from dataclasses import dataclass
from typing import Optional
from construct import Flag, Int64ul, Padding, Struct
from solders.pubkey import  Pubkey  # type: ignore
from spl.token.instructions import get_associated_token_address
from .base_class import BaseClass
from termcolor import cprint
from .constants import PUMP_FUN_PROGRAM


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
        cprint("Getting coin data...", "green")
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
        cprint(f"Account info: {account_info}", "green")
        data = account_info.value.data
        parsed_data = bonding_curve_struct.parse(data)
        return parsed_data
      except Exception as e:
        cprint(f"Error deriving bonding curve accounts: {e}", "red")
    
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
    



