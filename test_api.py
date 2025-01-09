from src.exchange.bitget.v2.bg_v2_api import BitgetMixAPI, BitgetSpotAPI


# 示例用法
if __name__ == "__main__":
    # 替换为实际的 API 密钥、秘密密钥和密码短语
    # API_KEY = 'bg_6490a66edf0d67bd2ab005b40c3db9da'
    # API_SECRET_KEY = '547bbef648d12191ccdf4ff0e59e4e25753dc04371c565d512b9dced3c2fa42a'
    # PASSPHRASE = '13579246810'
    
    API_KEY = 'bg_922b0240aa4a62375b9fdef5b297e9af'
    API_SECRET_KEY = '6a28a9c6c7703b1e871dcfef07e4e67f0bec87b6eec1e9e916c2e4557783d7f8'
    PASSPHRASE = 'SKYxjp19932259'

    # 创建交易实例
    future = BitgetMixAPI(API_KEY, API_SECRET_KEY, PASSPHRASE)
    
    # 下现货订单（市价单）
    # future.place_order(symbol="DOGEUSDT", side="buy", size="5")
    
    # 平仓操作
    # future.close_positions(symbol="DOGEUSDT", hold_side="long")

    response = future.get_account_info()
    if response.get('code') == '00000' or response.get('msg') == 'success':
        # 从返回的data中提取需要的信息
        user_id = response['data'].get('userId')
        inviter_id = response['data'].get('inviterId')
        parent_id = response['data'].get('parentId')
        trader_type = response['data'].get('traderType')

        # 打印这些信息
        print(f"User ID: {user_id}")
        print(f"Inviter ID: {inviter_id}")
        print(f"Parent ID: {parent_id}")
        print(f"Trader Type: {trader_type}")
    else:
        print("Failed to retrieve account info:", response)

    # future_fills = future.get_fills("AI16ZUSDT", "1259889912803090433")
    # if future_fills.get('code') == '00000' or future_fills.get('msg') == 'success':
    #     fill_list = future_fills['data']['fillList']
    #     print(fill_list)
        
    #     total_quote_volume = 0
    #     total_profit = 0
    #     total_price = 0
    #     total_trades = len(fill_list)  # 记录成交的次数
        
    #     # 遍历 fillList 列表
    #     for fill in fill_list:
    #         orderId = fill.get('orderId')  # 从每个字典中提取 orderId
    #         price = float(fill.get('price'))  # 从每个字典中提取 price
    #         quoteVolume = float(fill.get('quoteVolume'))  # 从每个字典中提取 quoteVolume
    #         profit = float(fill.get('profit'))  # 从每个字典中提取 profit

    #         # 累加 quoteVolume 和 profit
    #         total_quote_volume += quoteVolume
    #         total_profit += profit
    #         total_price += price * quoteVolume  # 用成交量加权计算总的成交价格

    #         # print(f"orderId: {orderId}")
    #         # print(f"price: {price}")
    #         # print(f"quoteVolume: {quoteVolume}")
    #         # print(f"profit: {profit}")

    #     # 计算平均成交价格
    #     average_price = total_price / total_quote_volume if total_quote_volume != 0 else 0

    #     # 打印总的quoteVolume、profit和平均成交价格
    #     print(f"Total quoteVolume: {total_quote_volume}")
    #     print(f"Total profit: {total_profit}")
    #     print(f"Average price: {average_price}")
    # else:
    #     print("Failed to get fills or error in response.")

            
