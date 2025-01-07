# src/exchange/bitget/constants.py

class BitgetURLs:
    """Bitget API URLs"""
    REST_API_URL = 'https://api.bitget.com'
    WS_PUBLIC_URL = 'wss://ws.bitget.com/v2/ws/public'
    WS_PRIVATE_URL = 'wss://ws.bitget.com/v2/ws/private'

class BitgetHeaders:
    """Bitget API Headers"""
    CONTENT_TYPE = 'Content-Type'
    ACCESS_KEY = 'ACCESS-KEY'
    ACCESS_SIGN = 'ACCESS-SIGN'
    ACCESS_TIMESTAMP = 'ACCESS-TIMESTAMP'
    ACCESS_PASSPHRASE = 'ACCESS-PASSPHRASE'
    APPLICATION_JSON = 'application/json'

class BitgetConstants:
    """Bitget API Constants"""
    GET = "GET"
    POST = "POST"
    DELETE = "DELETE"
    
    LOCALE = 'locale'
    REQUEST_PATH = '/user/verify'
    
    # Sign type
    SIGN_SHA256 = "SHA256"
    SIGN_RSA = "RSA"
    DEFAULT_SIGN_TYPE = SIGN_SHA256

class WSChannelType:
    """WebSocket Channel Types"""
    TICKER = "ticker"
    TRADE = "trade"
    DEPTH = "depth"
    CANDLE = "candle"
    
    ACCOUNT = "account"
    POSITION = "position"
    ORDER = "order"