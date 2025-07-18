#!/usr/bin/env python3
"""
DustBuster — утилита для сбора «пустых» токенов (dust) с любого ERC-20 кошелька.
"""

import os
import time
import requests
from web3 import Web3
from eth_utils import to_checksum_address

ETH_RPC_URL      = os.getenv("ETH_RPC_URL")
ETHPLORER_API_KEY= os.getenv("ETHPLORER_API_KEY")
WALLET_ADDRESS   = os.getenv("WALLET_ADDRESS")
SINK_ADDRESS     = os.getenv("SINK_ADDRESS")
THRESHOLD_ETH    = float(os.getenv("THRESHOLD_ETH", "0.01"))  # порог в ETH
POLL_INTERVAL    = int(os.getenv("POLL_INTERVAL", "600"))    # в секундах

if not all([ETH_RPC_URL, ETHPLORER_API_KEY, WALLET_ADDRESS, SINK_ADDRESS]):
    print("Необходимо задать ETH_RPC_URL, ETHPLORER_API_KEY, WALLET_ADDRESS, SINK_ADDRESS")
    exit(1)

w3 = Web3(Web3.HTTPProvider(ETH_RPC_URL))
if not w3.is_connected():
    print("Ошибка: не удалось подключиться к RPC‑узлу.")
    exit(1)

WALLET_ADDRESS = to_checksum_address(WALLET_ADDRESS)
SINK_ADDRESS   = to_checksum_address(SINK_ADDRESS)

ERC20_ABI = [{
    "constant":False,"inputs":[{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],
    "name":"transfer","outputs":[{"name":"","type":"bool"}],"type":"function"
}]

def fetch_token_balances(address):
    url = f"https://api.ethplorer.io/getAddressInfo/{address}"
    resp = requests.get(url, params={"apiKey": ETHPLORER_API_KEY})
    resp.raise_for_status()
    data = resp.json()
    tokens = data.get("tokens", [])
    result = []
    for item in tokens:
        info = item["tokenInfo"]
        balance = int(item["balance"]) / 10**int(info["decimals"])
        price_usd = (info.get("price") or {}).get("rate", 0)
        eth_price = data.get("ETH", {}).get("price", {}).get("rate", 0)
        # примерное ETH-эквивалентное значение
        value_eth = balance * price_usd / eth_price if eth_price else 0
        result.append({
            "symbol": info["symbol"],
            "contract": info["address"],
            "balance": balance,
            "value_eth": value_eth
        })
    return result

def build_and_send(tx):
    signed = w3.eth.account.sign_transaction(tx, private_key=os.getenv("PRIVATE_KEY"))
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    print(f"Отправлено: {tx_hash.hex()}")

def main():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Запуск DustBuster. Порог: {THRESHOLD_ETH} ETH")
    while True:
        try:
            tokens = fetch_token_balances(WALLET_ADDRESS)
            dust = [t for t in tokens if t["value_eth"] < THRESHOLD_ETH and t["value_eth"] > 0]
            if not dust:
                print("Думаем... пыли нет.")
            else:
                print(f"Найдено {len(dust)} dust‑токенов:")
                nonce = w3.eth.get_transaction_count(WALLET_ADDRESS)
                for t in dust:
                    print(f" • {t['symbol']}: баланс={t['balance']}, ≈{t['value_eth']:.6f} ETH")
                    contract = w3.eth.contract(address=t["contract"], abi=ERC20_ABI)
                    tx = contract.functions.transfer(
                        SINK_ADDRESS,
                        int(t["balance"] * 10**18)  # перенести весь баланс
                    ).build_transaction({
                        "from": WALLET_ADDRESS,
                        "nonce": nonce,
                        "gas": 100_000,
                        "gasPrice": w3.to_wei("10", "gwei")
                    })
                    print(f"   > формирую транзакцию на отправку {t['symbol']} в {SINK_ADDRESS}")
                    # раскомментируйте следующую строку, чтобы отправлять реально:
                    # build_and_send(tx)
                    nonce += 1
            time.sleep(POLL_INTERVAL)
        except Exception as e:
            print(f"[Error] {e}")
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
