"""Token constants for arbitrage bot."""

# (Binance symbol on USDT pair, Solana mint, token decimals)
TOKENS = {
    "BONK":   ("BONKUSDT",   "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", 5),
    "ORCA":   ("ORCAUSDT",   "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",  6),
    "PYTH":   ("PYTHUSDT",   "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3", 6),
    "JTO":    ("JTOUSDT",    "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",  9),
    "RAY":    ("RAYUSDT",    "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R", 6),
    "WIF":    ("WIFUSDT",    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", 6),
    "SOL":    ("SOLUSDT",    "So11111111111111111111111111111111111111112",  9),
    "JUP":    ("JUPUSDT",    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",  6),
    "RENDER": ("RENDERUSDT", "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof",  8),
    "POPCAT": ("POPCATUSDT", "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr", 9),
    "MEW":    ("MEWUSDT",    "MEW1gQWJ3nEXg2qgERiKu7FAFj79PHvQVREQUzScPP5",  5),
    "IO":     ("IOUSDT",     "BZLbGTNCSFfoth2GYDtwr7e4imWzpR5jqcUuGEwr646K", 8),
}

USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDC_DECIMALS = 6

# Trading fees (rough estimates)
BINANCE_TAKER_FEE_PCT = 0.10  # 0.1% per trade
JUPITER_AVG_FEE_PCT = 0.25    # average swap fee + network impact

COIN_LIST = list(TOKENS.keys())
