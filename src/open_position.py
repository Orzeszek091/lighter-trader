import os
import asyncio
import argparse
import time
from decimal import Decimal
from dotenv import load_dotenv

# Официальный SDK: https://github.com/elliottech/lighter-python
# Документация (SignerClient, типы ордеров/TIF): https://apidocs.lighter.xyz
import lighter

DEFAULT_BASE_URL = "https://mainnet.zklighter.elliot.ai"
ORDER_TYPE_MARKET = "ORDER_TYPE_MARKET"
ORDER_TYPE_LIMIT = "ORDER_TYPE_LIMIT"
TIF_IOC = "ORDER_TIME_IN_FORCE_IMMEDIATE_OR_CANCEL"
TIF_POST_ONLY = "ORDER_TIME_IN_FORCE_POST_ONLY"
TIF_GTT = "ORDER_TIME_IN_FORCE_GOOD_TILL_TIME"

async def resolve_market_id(order_api: lighter.OrderApi, symbol: str) -> int:
    obs = await order_api.order_books()
    markets = getattr(obs, "order_books", None) or getattr(obs, "markets", None) or obs
    if not markets:
        raise RuntimeError("Не удалось получить список рынков (order_books).")
    symbol_u = symbol.upper()
    for m in markets:
        mid = getattr(m, "market_index", None) or getattr(m, "marketId", None) or getattr(m, "id", None)
        t_obj = getattr(m, "ticker", None)
        tick = None
        if isinstance(t_obj, str):
            tick = t_obj.upper()
        elif t_obj is not None:
            tick = (getattr(t_obj, "symbol", None) or getattr(t_obj, "name", None) or getattr(t_obj, "ticker", None))
            if tick: tick = str(tick).upper()
        if mid is not None and tick == symbol_u:
            return int(mid)
    raise ValueError(f"Маркет с тикером '{symbol}' не найден. Укажи --market-id вручную.")

async def fetch_base_decimals(order_api: lighter.OrderApi, market_id: int, fallback_decimals: int = 18) -> int:
    details = await order_api.order_book_details(market_id=market_id)
    t = getattr(details, "ticker", None) or getattr(details, "market", None)
    for attr in ("baseDecimals", "base_decimals", "quantityDecimals", "quantity_decimals"):
        val = getattr(t, attr, None) if t is not None else None
        if isinstance(val, int): return val
        if isinstance(val, str) and val.isdigit(): return int(val)
    return fallback_decimals

def human_to_base(amount: Decimal, base_decimals: int) -> int:
    scale = Decimal(10) ** base_decimals
    return int((amount * scale).to_integral_value(rounding="ROUND_DOWN"))

async def place_market_order(
    base_url: str,
    account_index: int,
    api_key_index: int,
    api_key_private_key: str,
    market_id: int,
    side: str,
    qty: Decimal,
    base_decimals_hint: int = None,
):
    client = lighter.ApiClient(base_url=base_url)
    order_api = lighter.OrderApi(client)
    base_decimals = base_decimals_hint or await fetch_base_decimals(order_api, market_id)
    base_amount_int = human_to_base(qty, base_decimals)

    signer = lighter.SignerClient(
        url=base_url,
        private_key=api_key_private_key,
        account_index=account_index,
        api_key_index=api_key_index,
    )

    tx_result = signer.create_market_order(
        market_index=market_id,
        side=side.lower(),
        base_amount=base_amount_int,
        time_in_force=TIF_IOC,
    )
    print("Market order result:", tx_result)

async def place_limit_order_post_only(
    base_url: str,
    account_index: int,
    api_key_index: int,
    api_key_private_key: str,
    market_id: int,
    side: str,
    qty: Decimal,
    price: Decimal,
    base_decimals_hint: int = None,
    price_exponent_hint: int = 6,
):
    client = lighter.ApiClient(base_url=base_url)
    order_api = lighter.OrderApi(client)
    tx_api = lighter.TransactionApi(client)

    base_decimals = base_decimals_hint or await fetch_base_decimals(order_api, market_id)
    base_amount_int = human_to_base(qty, base_decimals)
    price_int = int((price * (Decimal(10) ** price_exponent_hint)).to_integral_value(rounding="ROUND_HALF_UP"))

    signer = lighter.SignerClient(
        url=base_url,
        private_key=api_key_private_key,
        account_index=account_index,
        api_key_index=api_key_index,
    )

    try:
        tx_result = signer.create_order(
            market_index=market_id,
            side=side.lower(),
            base_amount=base_amount_int,
            price=price_int,
            order_type=ORDER_TYPE_LIMIT,
            time_in_force=TIF_POST_ONLY,
        )
        print("Limit order (post-only) result:", tx_result)
        return
    except AttributeError:
        next_nonce = await tx_api.next_nonce(account_index=account_index, api_key_index=api_key_index)
        signed = signer.sign_create_order(
            market_index=market_id,
            side=side.lower(),
            base_amount=base_amount_int,
            price=price_int,
            order_type=ORDER_TYPE_LIMIT,
            time_in_force=TIF_POST_ONLY,
            nonce=int(getattr(next_nonce, "nonce", getattr(next_nonce, "next", 0))) or int(time.time()),
        )
        sent = await tx_api.send_tx(tx=signed)
        print("Limit order (post-only) sent:", sent)

async def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Open position on Lighter (market/limit)")
    parser.add_argument("--base-url", default=os.getenv("LIGHTER_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--account-index", type=int, default=int(os.getenv("LIGHTER_ACCOUNT_INDEX", "0")))
    parser.add_argument("--api-key-index", type=int, default=int(os.getenv("LIGHTER_API_KEY_INDEX", "2")))
    parser.add_argument("--api-key-private-key", default=os.getenv("LIGHTER_API_KEY_PRIVATE_KEY"))
    parser.add_argument("--eth-private-key", default=os.getenv("ETH_PRIVATE_KEY"))
    parser.add_argument("--market-id", type=int, help="Напр. ETH=0 (если знаешь). Иначе используй --symbol.")
    parser.add_argument("--symbol", help="ETH/BTC/... Если нет market-id, попытаемся найти.")
    parser.add_argument("--side", required=True, choices=["buy", "sell"])
    parser.add_argument("--qty", required=True, type=Decimal)
    parser.add_argument("--type", choices=["market", "limit"], default="market")
    parser.add_argument("--price", type=Decimal, help="для лимитного ордера")
    parser.add_argument("--price-exp-hint", type=int, default=6)
    args = parser.parse_args()

    client = lighter.ApiClient(base_url=args.base_url)
    order_api = lighter.OrderApi(client)

    market_id = args.market_id
    if market_id is None:
        if not args.symbol:
            raise SystemExit("Укажи --market-id или --symbol (например, --symbol ETH).")
        market_id = await resolve_market_id(order_api, args.symbol)

    if args.type == "market":
        await place_market_order(
            base_url=args.base_url,
            account_index=args.account_index,
            api_key_index=args.api_key_index,
            api_key_private_key=args.api_key_private_key,
            market_id=market_id,
            side=args.side,
            qty=args.qty,
        )
    else:
        if args.price is None:
            raise SystemExit("Для лимитного — нужен --price.")
        await place_limit_order_post_only(
            base_url=args.base_url,
            account_index=args.account_index,
            api_key_index=args.api_key_index,
            api_key_private_key=args.api_key_private_key,
            market_id=market_id,
            side=args.side,
            qty=args.qty,
            price=args.price,
            price_exponent_hint=args.price_exp_hint,
        )

if __name__ == "__main__":
    asyncio.run(main())
