import base64
import hmac
import time

from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5 as pk

from . import consts as c


def sign(message, secret_key):
    mac = hmac.new(bytes(secret_key, encoding='utf8'), bytes(message, encoding='utf-8'), digestmod='sha256')
    d = mac.digest()
    return str(base64.b64encode(d), 'utf8')

def signByRSA(message, secret_key):
    privatekey = RSA.importKey(secret_key)
    h = SHA256.new(message.encode('utf-8'))
    signer = pk.new(privatekey)
    sign = signer.sign(h)
    return str(base64.b64encode(sign), 'utf8')


# def pre_hash(timestamp, method, request_path, body = ""):
#     return str(timestamp) + str.upper(method) + request_path + body

def pre_hash(timestamp, method, request_path, body):
    print(f"\n[utils.pre_hash] === 开始执行 pre_hash ===")
    print(f"[utils.pre_hash] 参数 - timestamp: {timestamp} (类型: {type(timestamp)})")
    print(f"[utils.pre_hash] 参数 - method: {method} (类型: {type(method)})")
    print(f"[utils.pre_hash] 参数 - request_path: {request_path} (类型: {type(request_path)})")
    print(f"[utils.pre_hash] 参数 - body: {body} (类型: {type(body)})")

    # 如果 method 是 bytes 类型，先解码为字符串
    if isinstance(method, bytes):
        print(f"[utils.pre_hash] method 是 bytes 类型，尝试解码为字符串...")
        method = method.decode('utf-8')
        print(f"[utils.pre_hash] 解码后 method: {method} (类型: {type(method)})")
    elif not isinstance(method, str):
        print(f"[utils.pre_hash] 警告: method 不是字符串也不是 bytes 类型，无法处理！")
        raise ValueError(f"Method must be a string or bytes, got {type(method)}")

    # 执行拼接
    print(f"[utils.pre_hash] 开始拼接字符串...")
    result = str(timestamp) + method.upper() + request_path + body
    print(f"[utils.pre_hash] 拼接结果: {result}")
    print(f"[utils.pre_hash] === pre_hash 执行完成 ===\n")

    return result

def get_header(api_key, sign, timestamp, passphrase):
    header = dict()
    header[c.CONTENT_TYPE] = c.APPLICATION_JSON
    header[c.OK_ACCESS_KEY] = api_key
    header[c.OK_ACCESS_SIGN] = sign
    header[c.OK_ACCESS_TIMESTAMP] = str(timestamp)
    header[c.OK_ACCESS_PASSPHRASE] = passphrase
    header[c.LOCALE] = 'zh-CN'

    return header


def parse_params_to_str(params):
    params = [(key, val) for key, val in params.items()]
    params.sort(key=lambda x: x[0])
    # from urllib.parse import urlencode
    # url = '?' +urlencode(params);
    url = '?' +toQueryWithNoEncode(params);
    if url == '?':
        return ''
    return url
    # url = '?'
    # for key, value in params.items():
    #     url = url + str(key) + '=' + str(value) + '&'
    #
    # return url[0:-1]

def toQueryWithNoEncode(params):
    url = ''
    for key, value in params:
        url = url + str(key) + '=' + str(value) + '&'
    return url[0:-1]


def get_timestamp():
    return int(time.time() * 1000)


def signature(timestamp, method, request_path, body, secret_key):
    if str(body) == '{}' or str(body) == 'None':
        body = ''
    message = str(timestamp) + str.upper(method) + request_path + str(body)
    mac = hmac.new(bytes(secret_key, encoding='utf8'), bytes(message, encoding='utf-8'), digestmod='sha256')
    d = mac.digest()
    return base64.b64encode(d)

def check_none(value, msg=""):
    if not value:
        raise Exception(msg + " Invalid params!")