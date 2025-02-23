#!/usr/bin/env python
# -*- coding: utf-8 -*-

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Union


# def adjust_decimal_places(value: Union[str, float, Decimal], 
#                          reference: Union[str, float, Decimal], 
#                          round_mode: str = ROUND_HALF_UP) -> Decimal:
#     """调整小数位数，与参考值保持一致"""
#     if isinstance(value, (float, str)):
#         value = Decimal(str(value))
#     if isinstance(reference, (float, str)):
#         reference = Decimal(str(reference))
        
#     # 获取参考值的小数位数
#     decimal_places = abs(reference.as_tuple().exponent)
#     return value.quantize(Decimal('0.1') ** decimal_places, rounding=round_mode)


def adjust_decimal_places(value: Decimal, precision: int) -> Decimal:
    """调整小数位数到指定的整数精度，向下取整"""
    if not isinstance(precision, int):
        raise ValueError("Precision must be an integer")
    return value.quantize(Decimal(f'0.{"0" * precision}'), rounding=ROUND_DOWN)

def find_value(data, key):
    """递归查找嵌套数据结构中的指定键值对"""
    if isinstance(data, dict):
        # 如果是字典，直接查找
        if key in data:
            return data[key]
        # 如果字典中没有，递归查找
        for sub_key, sub_value in data.items():
            result = find_value(sub_value, key)
            if result is not None:
                return result
    elif isinstance(data, list):
        # 如果是列表，遍历每个元素
        for item in data:
            result = find_value(item, key)
            if result is not None:
                return result
    # 如果数据结构中没有找到该键，返回 None
    return None