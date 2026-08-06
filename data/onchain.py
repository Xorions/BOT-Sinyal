"""Data on-chain dari DefiLlama (gratis, tanpa API key).

Sinyal yang dipakai: perubahan TVL harian chain terkait tiap koin.
Perubahan TVL naik/turun menunjukkan arus modal masuk/keluar (proxy on-chain).
"""

from typing import Any, Dict, List, Optional

import requests

from config import DEFILLAMA_BASE_URL, REQUEST_RETRIES, REQUEST_TIMEOUT

CHAIN_MAP: Dict[str, str] = {
    "bitcoin": "Bitcoin",
    "ethereum": "Ethereum",
    "binancecoin": "BSC",
    "solana": "Solana",
    "ripple": "XRP",
    "dogecoin": "Dogecoin",
    "cardano": "Cardano",
    "tron": "Tron",
    "litecoin": "Litecoin",
    "avalanche-2": "Avalanche",
    "polkadot": "Polkadot",
    "matic-network": "Polygon",
    "toncoin": "TON",
    "the-open-network": "TON",
    "near": "Near",
    "aptos": "Aptos",
    "arbitrum": "Arbitrum",
    "optimism": "OP Mainnet",
    "cosmos": "Cosmos",
    "sui": "Sui",
    "internet-computer": "Internet Computer",
    "stacks": "Stacks",
    "monero": "Monero",
    "injective": "Injective",
    "sei": "Sei",
    "algorand": "Algorand",
    "flow": "Flow",
    "vechain": "VeChain",
    "tezos": "Tezos",
    "elrond-erd-2": "MultiversX",
    "zilliqa": "Zilliqa",
    "hedera-hashgraph": "Hedera",
    "fantom": "Fantom",
    "kava": "Kava",
}


class OnChainDataError(Exception):
    """Gagal mengambil data dari DefiLlama."""


def _get(url: str) -> Any:
    last_error: Optional[Exception] = None
    for attempt in range(REQUEST_RETRIES):
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_error = exc
            if attempt < REQUEST_RETRIES - 1:
                import time
                time.sleep(2 * (attempt + 1))
    raise OnChainDataError(f"Gagal mengambil data {url}: {last_error}")


def _chain_for(coin_id: str) -> Optional[str]:
    return CHAIN_MAP.get(coin_id)


def get_tvl_change(coin_id: str) -> Optional[float]:
    """Perubahan TVL harian (dalam %) untuk chain milik koin.

    Mengembalikan None bila koin tidak punya chain atau data gagal.
    """
    chain = _chain_for(coin_id)
    if chain is None:
        return None
    try:
        data: List[Dict[str, Any]] = _get(
            f"{DEFILLAMA_BASE_URL}/v2/historicalChainTvl/{chain}"
        )
    except OnChainDataError:
        return None

    points = [d for d in data if d.get("tvl") is not None]
    if len(points) < 2:
        return None
    last, prev = points[-1]["tvl"], points[-2]["tvl"]
    if not prev:
        return None
    return (last - prev) / prev * 100.0
