# src/utils/common.py

from decimal import Decimal, ROUND_HALF_UP
import sys
from typing import Union, Optional
import json
import os

def adjust_decimal_places(value: Union[str, float, Decimal], 
                         reference: Union[str, float, Decimal], 
                         round_mode: str = ROUND_HALF_UP) -> Decimal:
    """调整小数位数，与参考值保持一致"""
    if isinstance(value, (float, str)):
        value = Decimal(str(value))
    if isinstance(reference, (float, str)):
        reference = Decimal(str(reference))
        
    # 获取参考值的小数位数
    decimal_places = abs(reference.as_tuple().exponent)
    return value.quantize(Decimal('0.1') ** decimal_places, rounding=round_mode)

def save_json(data: dict, file_path: str):
    """保存JSON数据"""
    directory = os.path.dirname(file_path)
    if not os.path.exists(directory):
        os.makedirs(directory)
        
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(file_path: str) -> Optional[dict]:
    """加载JSON数据"""
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"加载JSON文件失败: {str(e)}")
    return None

def resource_path(relative_path):
    """获取资源文件的绝对路径
    
    Args:
        relative_path: 相对路径
        
    Returns:
        str: 资源文件的绝对路径
    """
    try:
        # PyInstaller创建的临时文件夹中的路径
        base_path = getattr(sys, '_MEIPASS', os.path.abspath("."))
        
        # 标准化路径（处理不同操作系统的路径分隔符）
        relative_path = os.path.normpath(relative_path)
        full_path = os.path.join(base_path, relative_path)
        
        # 验证文件是否存在
        if not os.path.exists(full_path):
            print(f"Warning: Resource not found at {full_path}")
            return None
            
        return full_path
    except Exception as e:
        print(f"Error in resource_path: {str(e)}")
        return None
    
def create_file_if_not_exists(file_path: str):
    """确保文件和文件夹存在，如果文件不存在，则创建空文件"""
    dir_path = os.path.dirname(file_path)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
    
    if not os.path.isfile(file_path):
        with open(file_path, 'w', encoding='utf-8') as f:
            pass  # 创建空文件
