# src/utils/storage/database.py

import sqlite3
import json
from typing import Optional, Dict, Any
from datetime import datetime
import os

class Database:
    """数据库管理类"""
    
    def __init__(self, db_path: str = './data/grid_trading.db'):
        self.db_path = db_path
        self._ensure_db_dir()
        self._init_db()

    def _ensure_db_dir(self):
        """确保数据库目录存在"""
        db_dir = os.path.dirname(self.db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)

    def _init_db(self):
        """初始化数据库表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # API配置表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS api_configs (
                    exchange TEXT PRIMARY KEY,
                    config TEXT NOT NULL,
                    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 网格数据表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS grid_data (
                    uid TEXT PRIMARY KEY,
                    exchange TEXT NOT NULL,
                    inst_type TEXT NOT NULL,
                    data TEXT NOT NULL,
                    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 订单记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    uid TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    inst_type TEXT NOT NULL,
                    order_data TEXT NOT NULL,
                    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(uid) REFERENCES grid_data(uid)
                )
            ''')
            
            conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        return sqlite3.connect(self.db_path)

    def save_api_config(self, exchange: str, config: dict):
        """保存API配置"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''
                INSERT OR REPLACE INTO api_configs (exchange, config, update_time)
                VALUES (?, ?, ?)
                ''',
                (exchange, json.dumps(config), datetime.now().isoformat())
            )
            conn.commit()

    def load_api_config(self) -> dict:
        """加载API配置"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT exchange, config FROM api_configs')
            rows = cursor.fetchall()
            
            return {
                row[0]: json.loads(row[1])
                for row in rows
            }

    def save_grid_data(self, uid: str, inst_type: str, data: dict):
        """保存网格数据"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''
                INSERT OR REPLACE INTO grid_data 
                (uid, exchange, inst_type, data, update_time)
                VALUES (?, ?, ?, ?, ?)
                ''',
                (
                    uid,
                    data.get('exchange', 'unknown'),
                    inst_type,
                    json.dumps(data),
                    datetime.now().isoformat()
                )
            )
            conn.commit()

    def load_grid_data(self, inst_type: str) -> Dict[str, dict]:
        """加载网格数据"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT uid, data FROM grid_data WHERE inst_type = ?',
                (inst_type,)
            )
            rows = cursor.fetchall()
            
            return {
                row[0]: json.loads(row[1])
                for row in rows
            }

    def save_order(self, order_data: dict):
        """保存订单记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''
                INSERT INTO orders 
                (order_id, uid, exchange, inst_type, order_data)
                VALUES (?, ?, ?, ?, ?)
                ''',
                (
                    order_data['order_id'],
                    order_data['uid'],
                    order_data['exchange'],
                    order_data['inst_type'],
                    json.dumps(order_data)
                )
            )
            conn.commit()

    def get_order_history(self, uid: str) -> list:
        """获取订单历史"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''
                SELECT order_data, create_time 
                FROM orders 
                WHERE uid = ?
                ORDER BY create_time DESC
                ''',
                (uid,)
            )
            return [
                {
                    **json.loads(row[0]),
                    'create_time': row[1]
                }
                for row in cursor.fetchall()
            ]