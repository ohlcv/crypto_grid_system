# src/database/json_db.py

import os
import json
from datetime import datetime

class JsonDB:
    """使用JSON文件进行数据持久化的简单数据库"""

    def __init__(self, data_dir: str):
        """
        初始化JSON数据库
        
        Args:
            data_dir: 数据存储目录
        """
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

    def save_grid_data(self, data: dict) -> bool:
        """
        保存网格策略数据
        
        Args:
            data: 包含策略数据的字典，格式如:
                {
                    'inst_type': 'SPOT'/'FUTURES',
                    'strategies': {
                        'uid1': strategy_data1,
                        'uid2': strategy_data2,
                        ...
                    }
                }
        """
        try:
            inst_type = data.get('inst_type', 'SPOT').lower()
            filename = os.path.join(self.data_dir, f'grid_data_{inst_type}.json')
            
            # 添加保存时间
            data['last_save'] = datetime.now().isoformat()
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            print(f"[JsonDB] Data saved to {filename}")
            return True
            
        except Exception as e:
            print(f"[JsonDB] Error saving data: {e}")
            return False

    def load_grid_data(self, inst_type: str) -> dict:
        """
        加载网格策略数据
        
        Args:
            inst_type: 'SPOT' 或 'FUTURES'
            
        Returns:
            包含策略数据的字典，如果文件不存在则返回空字典
        """
        try:
            filename = os.path.join(self.data_dir, f'grid_data_{inst_type.lower()}.json')
            
            if not os.path.exists(filename):
                print(f"[JsonDB] Data file not found: {filename}")
                return {}
            
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"[JsonDB] Data loaded from {filename}")
                return data
                
        except Exception as e:
            print(f"[JsonDB] Error loading data: {e}")
            return {}