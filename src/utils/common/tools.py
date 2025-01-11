#!/usr/bin/env python
# -*- coding: utf-8 -*-

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