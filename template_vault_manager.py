import asyncio
import logging
import os
import time
import requests
import traceback
import argparse
import pandas as pd
from decimal import Decimal
from shared.api_config import ApiConfig
from shared.paradex_api_utils import Order, OrderSide, OrderType
from shared.api_client import get_jwt_token, get_paradex_config, post_order_payload, sign_order,cancel_all_orders_payload,fetch_positions,get_usdc_balance

from utils import (
    generate_paradex_account,
    get_l1_eth_account,
)


def build_order(config: ApiConfig, order_type: OrderType, order_side: OrderSide,order_price:Decimal, size: Decimal, market, client_id: str) -> Order:
    order = Order(
        market=market,
        order_type=order_type,
        order_side=order_side,
        limit_price=order_price,
        size=size,
        client_id=client_id,
        signature_timestamp=int(time.time()*1000),
        instruction="POST_ONLY"
    )
    sig = sign_order(config, order)
    order.signature = sig
    return order


async def main(config: ApiConfig,target_btc_expo:Decimal) -> None:
    # Initialize Ethereum account
    #This private key is your ETH wallet private key : 
    #That private key can be exported from your ETH coinbase wallet (L1)
    _, eth_account = get_l1_eth_account("YOUR_ETH_L1_PRIVATE_KEY")

    #When connected on your paradex account and logged in the UI
    #You can click your account icon on the top right corner
    #This should offer you 3 buttons :  "wallet", "switch account", "signout"
    #When you click on wallet, you'll get a popup on the paradex ui showing you 
    #1) the public key of the vault manager account (Paradex L2 account)
    #2) an icon to copy past the private key of this account (Paradex L2 account)
    config.paradex_account, config.paradex_account_private_key = "YOUR_VAULT_L2_ACCOUNT_PUBLIC_KEY","YOUR_PARADEX_L2_PRIVATE_KEY"
    

    # Get a JWT token to interact with private endpoints
    logging.info("Getting JWT...")
    paradex_jwt = await get_jwt_token(
        config.paradex_config,
        config.paradex_http_url,
        config.paradex_account,
        config.paradex_account_private_key,
    )

    #Get the vault position
    position=await fetch_positions(config.paradex_http_url, paradex_jwt)
    #This vault only trades BTC-USD-PERP so i dont have to do more filtering
    current_position=float(position[0]["size"])
    #Get vault current balance
    response = requests.get(
    "https://api.prod.paradex.trade/v1/vaults/summary?address=YOUR_VAULT_PUBLIC_KEY",
    )
    data = response.json()
    current_balance=float(data["results"][0]["vtoken_supply"])*float(data["results"][0]["vtoken_price"])
    #Get bid ask
    response = requests.get(
    "https://api.prod.paradex.trade/v1/bbo/BTC-USD-PERP",
    )
    data = response.json()
    bidd=Decimal(data["bid"])
    askk=Decimal(data["ask"])
    #Calculate expected position in BTC
    expected_position=current_balance*float(target_btc_expo)*50/float(data["bid"])
    amount=int((expected_position-current_position)*100)/100
    if abs(amount)<0.002:
        amount=0
        
    amount=Decimal(str(amount))
    # Cancel all orders
    await cancel_all_orders_payload(config.paradex_http_url, paradex_jwt)
    # Create a POST ONLY limit order
    if abs(amount)>0:
        if (amount<0):

            order = build_order(config, OrderType.Limit, OrderSide.Sell, askk, abs(amount), "BTC-USD-PERP", "mock")
            await post_order_payload(config.paradex_http_url, paradex_jwt, order.dump_to_dict())

        else:

            order = build_order(config, OrderType.Limit, OrderSide.Buy, bidd, amount, "BTC-USD-PERP", "mock")
            await post_order_payload(config.paradex_http_url, paradex_jwt, order.dump_to_dict())
        time.sleep(10)
    

if __name__ == "__main__":


    while True:
        try:
            bias_data = pd.read_csv("YOUR_SIGNAL_API_URL").values.tolist()
            target_btc_expo = Decimal(bias_data[-1][1])


            # Load environment variables
            config = ApiConfig()
            config.paradex_http_url = "https://api.prod.paradex.trade/v1"

            try:
                loop = asyncio.get_event_loop()
                # Load paradex config
                config.paradex_config = loop.run_until_complete(get_paradex_config(config.paradex_http_url))
                loop.run_until_complete(main(config,target_btc_expo))
            except Exception as e:
                logging.error("Local Main Error")
                logging.error(e)
                traceback.print_exc()
        except:
            print("Error general loop")
            time.sleep(5)
