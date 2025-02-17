# src/ui/tabs/grid_strategy_tab.py

import sys
import threading
import time
import traceback
import uuid
import json
import os
from decimal import Decimal
from typing import Any, Dict, Optional
from datetime import datetime
from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QLineEdit, QPushButton, QHBoxLayout,
    QMessageBox, QLabel, QHeaderView, QTableWidgetItem, QMenu, QSizePolicy,
    QComboBox, QDialog, QApplication
)
from qtpy.QtCore import Qt, QTimer, QRegularExpression, Signal
from qtpy.QtGui import QRegularExpressionValidator, QColor
from src.exchange.base_client import BaseClient, ExchangeType
from src.exchange.bitget.exceptions import BitgetAPIException
from src.exchange.client_factory import ExchangeClientFactory
from src.strategy.grid.grid_core import GridData, GridDirection
from src.strategy.grid.grid_strategy_manager import GridStrategyManager
from src.ui.dialogs.grid_settings_aidlog import GridDialog
from src.utils.common.common import create_file_if_not_exists
from src.utils.logger.log_helper import ui_logger


class GridStrategyTab(QWidget):
    """网格策略Tab页"""
    save_completed = Signal(str)  # 保存成功信号
    save_failed = Signal(str)     # 保存失败信号
    load_completed = Signal(str)  # 加载完成信号
    load_failed = Signal(str)     # 加载失败信号
    # 添加用于线程安全的信号
    add_row_signal = Signal(str)  # uid
    show_message_signal = Signal(str, str)  # title, message
    show_error_signal = Signal(str)  # error message
    # 表格列定义
    COLUMN_DEFINITIONS = [
        {"name": "交易对", "type": "text", "editable": False, "width": 100},
        {"name": "方向", "type": "text", "editable": False, "width": 80},
        {"name": "操作", "type": "switches", "editable": True, "width": 100},
        {"name": "运行状态", "type": "text", "editable": False, "width": 100},
        {"name": "当前层数", "type": "text", "editable": False, "width": 100},
        {"name": "最后时间", "type": "text", "editable": False, "width": 100},
        {"name": "时间戳", "type": "text", "editable": False, "width": 110},
        {"name": "最后价格", "type": "text", "editable": False, "width": 100},
        {"name": "开仓触发价", "type": "text", "editable": False, "width": 110},
        {"name": "止盈触发价", "type": "text", "editable": False, "width": 110},
        {"name": "尾单价格", "type": "text", "editable": False, "width": 100},
        {"name": "持仓均价", "type": "text", "editable": False, "width": 100},
        {"name": "持仓价值", "type": "text", "editable": False, "width": 100},
        {"name": "持仓盈亏", "type": "text", "editable": False, "width": 100},
        {"name": "实现盈亏", "type": "text", "editable": False, "width": 100},
        {"name": "总体止盈", "type": "text", "editable": False, "width": 100},
        {"name": "总体止损", "type": "text", "editable": False, "width": 100},
        {"name": "交易所", "type": "text", "editable": False, "width": 100},
        {"name": "标识符", "type": "text", "editable": False, "width": 100}
    ]

    def __init__(self, inst_type: str, client_factory: ExchangeClientFactory):
        super().__init__()
        self.logger = ui_logger
        self.inst_type = inst_type
        self.client_factory = client_factory
        self.strategy_manager = GridStrategyManager()
        
        self.tab_id = str(uuid.uuid4())  # 生成唯一的标签页ID
        self.current_exchange = None    # 当前选中的交易所
        self.exchange_client: Optional[BaseClient] = None
        self.config_path = os.path.join('./config/api_config', f'api_config.json')
        self.data_path = os.path.join('./data', 'grid_strategy', f'{inst_type.lower()}_strategies.json')
        # 创建自动保存定时器
        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.timeout.connect(lambda: self.save_data(show_message=False))
        self.auto_save_timer.start(300000)  # 每5分钟自动保存一次
        # 确保程序关闭时保存数据
        self._save_thread = None
        self._load_thread = None
        self.destroyed.connect(lambda: self.save_data(show_message=False))
        self.save_completed.connect(lambda msg: self.show_message("成功", msg))
        self.save_failed.connect(lambda msg: self.show_error_message(msg))
        self.load_completed.connect(lambda msg: self.show_message("成功", msg))
        self.load_failed.connect(lambda msg: self.show_error_message(msg))
        # 连接信号到对应的槽函数
        self.add_row_signal.connect(self._add_row_slot)
        self.show_message_signal.connect(self._show_message_slot)
        self.show_error_signal.connect(self._show_error_slot)
        # 创建用于控制API信息显示的定时器
        self.show_api_timer = QTimer(self)
        self.show_api_timer.timeout.connect(self._hide_api_info)
        self.setup_ui()
        self.load_api_config()
        self._connect_factory_signals()
        self.load_data()

    def _connect_factory_signals(self):
        """连接工厂和策略管理器信号"""
        # 客户端工厂信号
        self.client_factory.client_created.connect(self._handle_client_created)
        self.client_factory.client_error.connect(self._handle_client_error)
        self.client_factory.validation_failed.connect(self._handle_validation_failed)
        self.client_factory.client_status_changed.connect(self._handle_client_status)

        # 策略管理器信号
        self.strategy_manager.strategy_started.connect(self._handle_strategy_started)
        self.strategy_manager.strategy_stopped.connect(self._handle_strategy_stopped)
        self.strategy_manager.strategy_error.connect(self._handle_strategy_error)
        self.strategy_manager.strategy_status_changed.connect(self._handle_strategy_status_changed)
        # print("[GridStrategyTab] 工厂和策略管理器信号已连接")

    def _handle_client_status(self, tab_id: str, status: str):
        if tab_id != self.tab_id:
            return
            
        self.connection_status_label.setText(f"连接状态：{status}")
        
        if status == "就绪":
            self.connection_status_label.setStyleSheet("color: green")
        elif status in ["连接中", "验证中"]:
            self.connection_status_label.setStyleSheet("color: orange") 
        else:
            self.connection_status_label.setStyleSheet("color: red")
            
        # 处理失败状态
        if status == "失败":
            self._reset_api_inputs()
            self._disconnect_client()

    def _connect_client_signals(self, client: BaseClient):
        """连接客户端信号"""
        try:
            # 先检查信号是否已连接
            if hasattr(self, '_signals_connected') and self._signals_connected:
                client.tick_received.disconnect(self._handle_market_data)
                client.connection_status.disconnect(self.update_exchange_status)
                client.error_occurred.disconnect(self._handle_client_error)
                # 移除私有WS连接信号，因为验证已经由工厂处理
                self._signals_connected = False
                
            # 连接新信号
            client.tick_received.connect(self._handle_market_data)
            client.connection_status.connect(self.update_exchange_status)
            client.error_occurred.connect(self._handle_client_error)
            self._signals_connected = True
            
        except Exception as e:
            print(f"[GridStrategyTab] 连接信号失败: {e}")
            print(f"[GridStrategyTab] 错误详情: {traceback.format_exc()}")

    def test_connection(self):
        """测试API连接"""
        if not self.exchange_client:
            self.show_error_message("客户端未初始化，请先保存API配置。")
            return
            
        try:
            # 检查连接状态
            ws_status = self.exchange_client.get_ws_status()
            if not ws_status['public'] or not ws_status['private']:
                error_msg = "WebSocket连接失败: " + (
                    "公共WS未连接" if not ws_status['public'] else ""
                ) + (
                    " 私有WS未连接" if not ws_status['private'] else ""
                )
                raise ConnectionError(error_msg)

            self.show_message("连接测试", "API连接测试成功!")

        except Exception as e:
            error_msg = f"连接测试失败: {str(e)}"
            print(f"[GridStrategyTab] {error_msg}")
            print(f"[GridStrategyTab] 错误详情: {traceback.format_exc()}")
            self.show_error_message(error_msg)
            self._reset_api_inputs()
            self._disconnect_client()

    def _update_ws_status(self, public_connected: bool, private_connected: bool):
        """更新WebSocket状态显示"""
        self.public_ws_label.setText(f"公有：{'✓' if public_connected else '✗'}")
        self.public_ws_label.setStyleSheet(f"color: {'green' if public_connected else 'red'};")
        self.private_ws_label.setText(f"私有：{'✓' if private_connected else '✗'}")
        self.private_ws_label.setStyleSheet(f"color: {'green' if private_connected else 'red'};")
        
        all_connected = public_connected and private_connected
        self.connection_status_label.setText(f"连接状态：{all_connected}")
        self.connection_status_label.setStyleSheet(f"color: {'green' if all_connected else 'red'};")

    def update_exchange_status(self, is_connected: bool = None):
        """更新交易所连接状态显示"""
        # print(f"\n[GridStrategyTab] >>> 更新交易所状态")
        # print(f"[GridStrategyTab] 传入的连接状态: {is_connected}")
        if not self.exchange_client:
            # print("[GridStrategyTab] 客户端不存在，显示未连接状态")
            self._update_ws_status(False, False)
            return
        # 获取详细状态
        ws_status = self.exchange_client.get_ws_status()
        # print(f"[GridStrategyTab] 获取到的WS状态: {ws_status}")
        # 更新UI显示
        self._update_ws_status(
            ws_status.get('public', False),
            ws_status.get('private', False)
        )
        print(f"[GridStrategyTab] >>> 更新交易所状态 - 连接状态: {is_connected}")

    def get_ws_status(self) -> Dict[str, Any]:
        """获取WebSocket状态和详细信息"""
        public_status = {
            "connected": self._public_ws.is_connected if self._public_ws else False
        }
        private_status = {
            "connected": self._private_ws.is_connected if self._private_ws else False,
            "login_status": getattr(self._private_ws, '_login_status', False)
        }
        print("[BitgetClient] WebSocket状态检查:")
        print(f"  公共WS: {public_status}")
        print(f"  私有WS: {private_status}")
        return {
            "public": public_status,
            "private": private_status
        }

    def _reset_api_inputs(self):
        """清空所有API输入框"""
        self.api_key_input.clear()
        self.secret_key_input.clear()
        self.passphrase_input.clear()
        self.user_id_input.clear()

    def _disconnect_client(self):
        """断开客户端连接"""
        if self.exchange_client:
            print("[GridStrategyTab] 断开客户端连接")
            old_client = self.exchange_client
            self.exchange_client = None
            self._update_ws_status(False, False)
            
            def destroy_client():
                self.client_factory.destroy_client(self.tab_id)
                print("[GridStrategyTab] 客户端已销毁")
                
            threading.Thread(target=destroy_client, daemon=True).start()

    def _handle_validation_failed(self, error_msg: str):
        """处理验证失败，确保只显示一次错误消息"""
        if not hasattr(self, '_validation_error_shown'):
            self._validation_error_shown = True
            self.show_error_message(error_msg)
            self._reset_api_inputs()
            self._disconnect_client()

    def _handle_client_created(self, client: BaseClient):
        """处理客户端创建"""
        print("\n[GridStrategyTab] === Client Created ===")
        try:
            if self.exchange_client is client:  # 直接比较对象引用
                print("[GridStrategyTab] 客户端实例匹配，重新连接信号")
                self._connect_client_signals(client)
                self.update_exchange_status(client.is_connected)
        except Exception as e:
            print(f"[GridStrategyTab] 客户端创建处理错误: {e}")
            print(f"[GridStrategyTab] 错误详情: {traceback.format_exc()}")
            self.show_error_message(f"客户端创建处理失败: {str(e)}")

    def check_client_status(self) -> bool:
        """检查交易所客户端的连接状态"""
        if not self.exchange_client or not self.exchange_client.is_connected:
            self.show_error_message("交易所客户端未连接，请检查网络连接！")
            return False
        ws_status = self.exchange_client.get_ws_status()
        if not ws_status.get("public") or not ws_status.get("private"):
            self.show_error_message("WebSocket连接不完整，请确保公共和私有WebSocket均已连接！")
            return False
        return True

    def _reset_and_create_client(self, config: dict, exchange_type: ExchangeType):
        """重置客户端并创建新客户端"""
        try:
            current_exchange = self.config.get('current', '').lower()
            if not current_exchange:
                raise ValueError("未指定当前交易所")
                
            # 构建传递给工厂的配置
            client_config = {
                'exchange': current_exchange,  # 添加交易所名称
                'user_id': config.get('user_id', ''),
                'api_key': config.get('api_key', ''),
                'api_secret': config.get('api_secret', ''),
                'passphrase': config.get('passphrase', '')
            }

            # 重置旧客户端
            if self.exchange_client:
                old_client = self.exchange_client
                self.exchange_client = None
                self._update_ws_status(False, False)
                print(f"[GridStrategyTab] 已重置旧客户端: {old_client}")
                def destroy_old_client():
                    self.client_factory.destroy_client(self.tab_id)
                    print("[GridStrategyTab] 旧客户端已销毁")
                threading.Thread(target=destroy_old_client, daemon=True).start()

            # 创建新客户端
            new_client = self.client_factory.create_client(
                self.tab_id, 
                current_exchange,  # 使用当前选中的交易所
                client_config, 
                exchange_type
            )
            
            if new_client:
                self.exchange_client = new_client
                print(f"[GridStrategyTab] 新客户端已创建: {new_client}")
                self._connect_client_signals(self.exchange_client)
                self.update_exchange_status(self.exchange_client.is_connected)
            else:
                print("[GridStrategyTab] 客户端创建失败")
                
        except Exception as e:
            print(f"[GridStrategyTab] 创建客户端失败: {e}")
            print(f"[GridStrategyTab] 错误详情: {traceback.format_exc()}")
            self.show_error_message(f"创建客户端失败: {str(e)}")

    def _handle_client_error(self, error_msg: str):
        """处理客户端错误"""
        print(f"[GridStrategyTab] Client error: {error_msg}")
        self.show_error_message(error_msg)
        
        if "API验证失败" in error_msg:
            print("[GridStrategyTab] API验证失败，重置客户端")
            exchange_type = ExchangeType.SPOT if self.inst_type == "SPOT" else ExchangeType.FUTURES
            self._reset_and_create_client(self.config, exchange_type)
            self.update_exchange_status(False)

    def _handle_market_data(self, symbol: str, market_data: dict):
        """处理市场数据"""
        # 检查是否有运行中的策略在使用这个交易对
        normalized_pair = symbol.replace('/', '')
        has_running_strategy = False
        
        for uid, grid in self.strategy_manager._data.items():
            if (grid.pair.replace('/', '') == normalized_pair and 
                grid.row_dict.get("运行状态") == "运行中"):
                has_running_strategy = True
                break
        
        if not has_running_strategy:
            # 如果没有运行中的策略，取消订阅
            print(f"[GridStrategyManager] 没有运行中的策略使用交易对 {symbol}，取消订阅")
            self.exchange_client.unsubscribe_pair(symbol, ["ticker"], grid.uid)
            return
                
        # 有运行中的策略，继续处理行情数据
        self.strategy_manager.process_market_data(symbol, market_data)

    def setup_ui(self):
        """设置UI界面"""
        layout = QVBoxLayout()
        # API 配置区域
        api_layout = self._setup_api_layout()
        layout.addLayout(api_layout)
        # 交易对输入区域
        input_layout = self._setup_input_layout()
        layout.addLayout(input_layout)
        # 策略表格
        self.table = self._setup_table()
        layout.addWidget(self.table)
        # 底部按钮布局
        button_layout = self._setup_button_layout()
        layout.addLayout(button_layout)
        self.setLayout(layout)

    def on_exchange_changed(self, new_exchange: str):
        """处理交易所切换"""
        new_exchange = new_exchange.lower()
        
        if not self.current_exchange:
            self.current_exchange = new_exchange
            return
            
        if new_exchange == self.current_exchange.lower():
            return

        # 检查是否有运行中的策略
        if self.strategy_manager.has_running_strategies():
            self.show_error_message("请先停止所有运行中的策略再切换交易所")
            self.exchange_combo.blockSignals(True)
            self.exchange_combo.setCurrentText(self.current_exchange)
            self.exchange_combo.blockSignals(False)
            return

        # 确认切换
        reply = QMessageBox.question(
            self,
            "切换交易所",
            f"确定要切换到 {new_exchange.capitalize()} 交易所吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # 获取新交易所的配置
            exchange_config = self.config.get(new_exchange, {})
            
            # 更新UI显示
            self.user_id_input.setText(exchange_config.get('user_id', ''))
            self.api_key_input.setText(exchange_config.get('api_key', ''))
            self.secret_key_input.setText(exchange_config.get('api_secret', ''))
            self.passphrase_input.setText(exchange_config.get('passphrase', ''))
            
            # 更新当前交易所
            self.current_exchange = new_exchange.capitalize()
            self.config['current'] = new_exchange
            
            # 断开现有客户端连接
            self._disconnect_client()
            
            # 如果有完整的API配置，创建新客户端
            if all([exchange_config.get('api_key'), exchange_config.get('api_secret'), exchange_config.get('passphrase')]):
                exchange_type = ExchangeType.SPOT if self.inst_type == "SPOT" else ExchangeType.FUTURES
                self._reset_and_create_client(exchange_config, exchange_type)
                
            # 保存配置
            self.save_api_config(auto_save=True)
        else:
            # 取消切换，恢复选择
            self.exchange_combo.blockSignals(True)
            self.exchange_combo.setCurrentText(self.current_exchange)
            self.exchange_combo.blockSignals(False)

    def _setup_api_layout(self) -> QVBoxLayout:
        """设置API配置区域"""
        api_layout = QVBoxLayout()

        # 用户输入部分
        user_input_layout = QHBoxLayout()

        # User ID
        user_input_layout.addWidget(QLabel("User ID:"))
        self.user_id_input = QLineEdit()
        self.user_id_input.setPlaceholderText("请输入 User ID")
        user_input_layout.addWidget(self.user_id_input, stretch=2)  

        # API Key
        user_input_layout.addWidget(QLabel("API Key:"))
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("请输入 API Key")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        user_input_layout.addWidget(self.api_key_input, stretch=4)

        # Secret Key
        user_input_layout.addWidget(QLabel("Secret Key:"))
        self.secret_key_input = QLineEdit()
        self.secret_key_input.setPlaceholderText("请输入 Secret Key")
        self.secret_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        user_input_layout.addWidget(self.secret_key_input, stretch=5)

        # Passphrase
        user_input_layout.addWidget(QLabel("Passphrase:"))
        self.passphrase_input = QLineEdit()
        self.passphrase_input.setPlaceholderText("请输入 Passphrase")
        self.passphrase_input.setEchoMode(QLineEdit.EchoMode.Password)
        user_input_layout.addWidget(self.passphrase_input, stretch=2)

        # 显示/隐藏按钮
        self.show_api_button = QPushButton("显示")
        self.show_api_button.clicked.connect(self._toggle_api_visibility)
        user_input_layout.addWidget(self.show_api_button, stretch=1)

        api_layout.addLayout(user_input_layout)

        # 操作按钮布局
        operation_layout = QHBoxLayout()

        # 交易所选择
        exchange_layout = QHBoxLayout()
        exchange_layout.addWidget(QLabel("交易所:"))
        self.exchange_combo = QComboBox()
        self.exchange_combo.currentTextChanged.connect(self.on_exchange_changed)
        
        # 获取支持当前交易类型的交易所列表
        exchange_type = ExchangeType.SPOT if self.inst_type == "SPOT" else ExchangeType.FUTURES
        available_exchanges = self.client_factory.registry.get_available_exchanges(exchange_type)
        
        # 设置交易所选项
        for exchange in self.client_factory.registry.get_all_exchanges():
            is_supported = exchange in available_exchanges
            self.exchange_combo.addItem(exchange.capitalize(), exchange)
            if not is_supported:
                # 禁用不支持的交易所
                index = self.exchange_combo.count() - 1
                self.exchange_combo.model().item(index).setEnabled(False)

        exchange_layout.addWidget(self.exchange_combo)
        operation_layout.addLayout(exchange_layout)

        # API配置按钮
        self.save_api_button = QPushButton("保存配置")
        self.save_api_button.clicked.connect(self.save_api_config)
        operation_layout.addWidget(self.save_api_button)

        self.load_api_button = QPushButton("加载配置")
        self.load_api_button.clicked.connect(self.load_api_config)
        operation_layout.addWidget(self.load_api_button)

        self.test_connection_button = QPushButton("测试连接")
        self.test_connection_button.clicked.connect(self.test_connection)
        operation_layout.addWidget(self.test_connection_button)

        # 连接状态标签组
        self.connection_status_label = QLabel("连接状态：False")
        self.connection_status_label.setStyleSheet("color: red;")
        operation_layout.addWidget(self.connection_status_label)

        self.public_ws_label = QLabel("公有：✗")
        self.public_ws_label.setStyleSheet("color: red;")
        operation_layout.addWidget(self.public_ws_label)

        self.private_ws_label = QLabel("私有：✗")
        self.private_ws_label.setStyleSheet("color: red;")
        operation_layout.addWidget(self.private_ws_label)

        # 添加线程信息标签
        self.thread_info_label = QLabel()
        self.update_thread_info_label()
        operation_layout.addWidget(self.thread_info_label)
        operation_layout.addStretch()
        api_layout.addLayout(operation_layout)

        return api_layout

    def load_api_config(self):
        """加载API配置"""
        if self.strategy_manager.has_running_strategies():
            self.show_error_message("请先删除所有策略")
            return

        # 确保文件存在
        create_file_if_not_exists(self.config_path)

        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:  # 空文件
                        config = self._create_default_config()
                    else:
                        config = json.loads(content)
            else:
                config = self._create_default_config()

            # 设置当前交易所
            current_exchange = config.get('current', '').lower()
            if not current_exchange:
                exchange_type = ExchangeType.SPOT if self.inst_type == "SPOT" else ExchangeType.FUTURES
                available_exchanges = self.client_factory.registry.get_available_exchanges(exchange_type)
                current_exchange = available_exchanges[0] if available_exchanges else "bitget"
                config['current'] = current_exchange

            # 获取当前交易所的API配置
            exchange_config = config.get(current_exchange, {})
            
            # 更新UI
            self.current_exchange = current_exchange.capitalize()
            self.exchange_combo.blockSignals(True)
            self.exchange_combo.setCurrentText(self.current_exchange)
            self.exchange_combo.blockSignals(False)

            self.user_id_input.setText(exchange_config.get('user_id', ''))
            self.api_key_input.setText(exchange_config.get('api_key', ''))
            self.secret_key_input.setText(exchange_config.get('api_secret', ''))
            self.passphrase_input.setText(exchange_config.get('passphrase', ''))

            self.config = config  # 保存整个配置

            if all([exchange_config.get('api_key'), exchange_config.get('api_secret'), exchange_config.get('passphrase')]):
                exchange_type = ExchangeType.SPOT if self.inst_type == "SPOT" else ExchangeType.FUTURES
                self._reset_and_create_client(exchange_config, exchange_type)

        except Exception as e:
            self.show_error_message(f"加载配置失败: {str(e)}")

    def save_api_config(self, auto_save: bool = False):
        """保存API配置"""
        if not auto_save and self.strategy_manager.has_running_strategies():
            self.show_error_message("请先删除所有策略")
            return

        current_exchange = self.exchange_combo.currentText().lower()
        
        # 获取当前输入的API信息
        new_config = {
            'user_id': self.user_id_input.text().strip(),
            'api_key': self.api_key_input.text().strip(),
            'api_secret': self.secret_key_input.text().strip(),
            'passphrase': self.passphrase_input.text().strip()
        }

        # 更新配置
        if not hasattr(self, 'config'):
            self.config = self._create_default_config()
        
        self.config[current_exchange] = new_config
        self.config['current'] = current_exchange

        try:
            # 保存配置
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=4)

            if not auto_save:
                exchange_type = ExchangeType.SPOT if self.inst_type == "SPOT" else ExchangeType.FUTURES
                self._reset_and_create_client(new_config, exchange_type)

        except Exception as e:
            self.show_error_message(f"保存API配置失败: {str(e)}")

    def _create_default_config(self) -> dict:
        """创建默认配置"""
        exchange_type = ExchangeType.SPOT if self.inst_type == "SPOT" else ExchangeType.FUTURES
        available_exchanges = self.client_factory.registry.get_available_exchanges(exchange_type)
        default_exchange = available_exchanges[0] if available_exchanges else "bitget"
        
        return {
            'current': default_exchange,
            default_exchange: {
                'user_id': '',
                'api_key': '',
                'api_secret': '',
                'passphrase': ''
            }
        }

    def _setup_input_layout(self) -> QHBoxLayout:
        """设置输入区域"""
        input_layout = QHBoxLayout()
        
        # 交易对输入
        self.input_symbol = QLineEdit()
        self.input_symbol.setPlaceholderText("请输入交易对 (如BTC)")
        validator = QRegularExpressionValidator(QRegularExpression("^[A-Za-z0-9]*$"))
        self.input_symbol.setValidator(validator)

        self.input_base = QLineEdit("USDT")
        self.input_base.setValidator(validator)
        
        # 添加按钮
        add_button = QPushButton("添加交易对")
        add_button.clicked.connect(self.add_trade_pair)
        
        # 批量操作按钮
        stop_all_button = QPushButton("停止全部")
        stop_all_button.clicked.connect(self.stop_all_strategies)

        # 开仓控制按钮
        self.toggle_all_open_button = QPushButton("开仓开关")
        self.toggle_all_open_button.setCheckable(True)
        self.toggle_all_open_button.setChecked(True)
        self.toggle_all_open_button.clicked.connect(lambda: self.toggle_all_operations("开仓"))

        # 平仓控制按钮
        self.toggle_all_close_button = QPushButton("平仓开关")
        self.toggle_all_close_button.setCheckable(True)
        self.toggle_all_close_button.setChecked(True)
        self.toggle_all_close_button.clicked.connect(lambda: self.toggle_all_operations("平仓"))

        # 多空切换按钮 - 仅在合约模式显示
        self.position_mode_button = QPushButton("做多")
        self.position_mode_button.setCheckable(True)
        self.position_mode_button.setChecked(False)  # 默认做多
        self.position_mode_button.clicked.connect(self.toggle_position_mode)
        self.update_position_mode_button_style()
        # 现货模式下隐藏多空切换按钮
        if self.inst_type == "SPOT":
            self.position_mode_button.hide()

        # 布局
        input_layout.addWidget(QLabel("交易对:"))
        input_layout.addWidget(self.input_symbol)
        input_layout.addWidget(QLabel("基础货币:"))
        input_layout.addWidget(self.input_base)
        input_layout.addWidget(add_button)
        input_layout.addWidget(self.position_mode_button)
        input_layout.addWidget(stop_all_button)
        input_layout.addWidget(self.toggle_all_open_button)
        input_layout.addWidget(self.toggle_all_close_button)
        input_layout.addStretch()

        return input_layout

    def update_thread_info_label(self):
        """更新线程信息显示"""
        all_threads = threading.enumerate()
        
        thread_stats = {
            'exchange': [],    # 交易所客户端线程
            'strategy': [],    # 策略运行线程
            'websocket': [],   # WebSocket连接线程
            'data': [],       # 数据保存加载线程
            'other': []       # 其他线程
        }
        
        for t in all_threads:
            thread_name = t.name.lower()
            if t.name == 'MainThread':
                continue
            elif 'exchange' in thread_name:
                thread_stats['exchange'].append(t)
            elif 'gridtrader' in thread_name:
                thread_stats['strategy'].append(t)
            elif 'websocket' in thread_name:
                thread_stats['websocket'].append(t)
            elif any(x in thread_name for x in ['save', 'load', 'data']):
                thread_stats['data'].append(t)
            else:
                thread_stats['other'].append(t)
        
        # 更新标签文本
        text = (f"[交易所: {len(thread_stats['exchange'])} | "
                f"策略: {len(thread_stats['strategy'])} | "
                f"WS: {len(thread_stats['websocket'])} | "
                f"数据: {len(thread_stats['data'])} | "
                f"其他: {len(thread_stats['other'])}]")
        self.thread_info_label.setText(text)
        # 打印详细信息
        # print("\n=== 线程详细信息 ===")
        # print("主线程: MainThread")
        for category, threads in thread_stats.items():
            if threads:
                # print(f"\n{category.capitalize()}线程:")
                pass
                for t in threads:
                    # print(f"- {t.name} | 活跃: {t.is_alive()}")
                    pass

    def update_position_mode_button_style(self):
        """更新多空切换按钮样式"""
        is_short = self.position_mode_button.isChecked()
        self.position_mode_button.setText("做空" if is_short else "做多")
        if is_short:
            self.position_mode_button.setStyleSheet(
                "QPushButton { background-color: #dc3545; color: white; }"
                "QPushButton:hover { background-color: #c82333; }"
            )
        else:
            self.position_mode_button.setStyleSheet(
                "QPushButton { background-color: #28a745; color: white; }"
                "QPushButton:hover { background-color: #218838; }"
            )

    def toggle_position_mode(self):
        """切换多空模式"""
        # 现货模式下禁止切换到做空
        if self.inst_type == "SPOT" and self.position_mode_button.isChecked():
            self.position_mode_button.setChecked(False)
            self.show_error_message("现货模式不支持做空")
            return
        
        self.update_position_mode_button_style()

    def _setup_table(self) -> QTableWidget:
        """设置策略表格"""
        table = QTableWidget(0, len(self.COLUMN_DEFINITIONS))
        table.setHorizontalHeaderLabels([col["name"] for col in self.COLUMN_DEFINITIONS])
        
        # 设置列宽
        for i, col in enumerate(self.COLUMN_DEFINITIONS):
            table.setColumnWidth(i, col["width"])
        
        # 设置表格属性
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self.show_context_menu)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        
        return table

    def _setup_button_layout(self) -> QHBoxLayout:
        """设置底部按钮布局"""
        button_layout = QHBoxLayout()
        
        # 左侧按钮
        save_button = QPushButton("保存数据")
        save_button.clicked.connect(lambda: self.save_data())
        
        load_button = QPushButton("加载数据")
        load_button.clicked.connect(self.load_data)
        
        button_layout.addWidget(save_button)
        button_layout.addWidget(load_button)
        
        # 添加弹性空间,把联系我们推到最右边
        button_layout.addStretch()
        
        # 添加联系我们标签
        contact_label = QLabel('联系我们: <a href="https://t.me/BingX01">@BingX01</a>')
        contact_label.setOpenExternalLinks(True)  # 允许打开外部链接
        button_layout.addWidget(contact_label)

        invite_label = QLabel('邀请链接: <a href="https://partner.bitget.cloud/bg/5BFPY0">https://partner.bitget.cloud/bg/5BFPY0</a>')
        # invite_label = QLabel('邀请链接: <a href="https://bingx.com/invite/JG8CYX/">https://bingx.com/invite/JG8CYX/</a>')
        invite_label.setOpenExternalLinks(True)  # 允许打开外部链接
        button_layout.addWidget(invite_label)

        return button_layout

    def _toggle_api_visibility(self):
        """切换API信息显示状态"""
        current_mode = self.api_key_input.echoMode()
        if current_mode == QLineEdit.EchoMode.Password:
            # 显示API信息
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.secret_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.passphrase_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.show_api_button.setText("隐藏")
            
            # 启动30秒定时器
            self.show_api_timer.start(30000)
        else:
            self._hide_api_info()

    def _hide_api_info(self):
        """隐藏API信息"""
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.secret_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.passphrase_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.show_api_button.setText("显示")
        self.show_api_timer.stop()

    def show_context_menu(self, position):
        """显示右键菜单"""
        index = self.table.indexAt(position)
        if not index.isValid():
            return

        row = index.row()
        uid_item = self.table.item(row, self.get_column_index("标识符"))
        if not uid_item:
            return
        uid = uid_item.text()
        
        menu = QMenu(self)

        # 根据客户端状态决定菜单项
        if self.check_client_status_for_actions():
            # 基础操作
            menu.addAction("设置网格", lambda: self.open_grid_setting(uid))
            
            # 根据策略状态添加启动/停止选项
            if self.strategy_manager.is_strategy_running(uid):
                menu.addAction("停止策略", lambda: self.stop_strategy(uid))
            else:
                menu.addAction("启动策略", lambda: self.start_strategy(uid))

            menu.addSeparator()
            menu.addAction("平仓", lambda: self.close_position(uid))
        else:
            # 仅允许设置和删除
            menu.addAction("设置网格", lambda: self.open_grid_setting(uid))

        # 添加刷新按钮
        menu.addSeparator()
        menu.addAction("刷新数据", lambda: self.refresh_strategy_data(uid))

        # 删除选项始终可用
        menu.addSeparator()
        menu.addAction("删除", lambda: self.delete_strategy(uid))
        
        menu.exec(self.table.mapToGlobal(position))

    def add_trade_pair(self):
        """添加新的交易对"""
        symbol = self.input_symbol.text().strip().upper()
        base = self.input_base.text().strip().upper()
        if not symbol or not base:
            self.show_error_message("交易对和基础货币不能为空！")
            return
        pair = f"{symbol}/{base}"
        exchange = self.exchange_combo.currentData()
        
        # 检查客户端状态
        if not self.check_client_status():
            self.show_error_message("交易所客户端未连接，请检查网络或配置！")
            return
            
        try:
            # 1. 验证交易对是否存在
            symbol_normalized = pair.replace('/', '')
            is_spot = self.inst_type == "SPOT"
            pair_info = self.exchange_client.rest_api.get_pairs(symbol=symbol_normalized)
            
            if pair_info.get('code') != '00000':
                raise ValueError(f"获取交易对信息失败: {pair_info.get('msg')}")
                
            # 验证交易对是否在返回结果中
            pair_exists = False
            pair_data = None
            for p in pair_info.get('data', []):
                if p['symbol'] == symbol_normalized:
                    pair_exists = True
                    pair_data = p
                    break

            if not pair_exists:
                raise ValueError(f"交易对 {pair} 不存在")

            # 2. 缓存交易对参数
            if pair_data: 
                # 提取参数
                if is_spot:
                    quantity_precision = int(pair_data.get('quantityPrecision', 4))
                    price_precision = int(pair_data.get('pricePrecision', 2))
                    min_trade_amount = Decimal(str(pair_data.get('minTradeAmount', '0')))
                    min_trade_value = Decimal(str(pair_data.get('minTradeUSDT', '5')))
                else:
                    quantity_precision = int(pair_data.get('volumePlace', 4))
                    price_precision = int(pair_data.get('pricePlace', 2))
                    min_trade_amount = Decimal(str(pair_data.get('minTradeNum', '0')))
                    min_trade_value = Decimal(str(pair_data.get('minTradeUSDT', '5')))

            # 3. 创建策略
            uid = str(uuid.uuid4())[:8]
            grid_data = self.create_strategy(uid, pair, exchange, self.inst_type)
            if not grid_data:
                raise ValueError("创建策略失败")

            # 4. 设置参数
            grid_data.quantity_precision = quantity_precision  
            grid_data.price_precision = price_precision
            grid_data.min_trade_amount = min_trade_amount
            grid_data.min_trade_value = min_trade_value
                
            # 5. 设置方向
            is_long = not self.position_mode_button.isChecked()
            grid_data.set_direction(is_long)
            
            # 6. 添加到表格
            self.add_strategy_to_table(uid)
            # 清空输入
            self.input_symbol.clear()
            # 更新线程信息显示
            self.update_thread_info_label()
            
        except Exception as e:
            self.show_error_message(f"添加交易对失败: {str(e)}")

    def add_strategy_to_table(self, uid: str):
        """添加策略到表格"""
        grid_data = self.strategy_manager.get_strategy_data(uid)
        if not grid_data:
            return

        row_position = self.table.rowCount()
        self.table.insertRow(row_position)
        
        # 填充表格数据
        for i, col in enumerate(self.COLUMN_DEFINITIONS):
            if col["name"] == "操作":
                # 获取操作状态
                operation_status = grid_data.row_dict.get("操作", {"开仓": True, "平仓": True})
                # print(f"[GridStrategyTab] 操作状态: {operation_status}")
                
                # 创建操作按钮组
                container = QWidget()
                layout = QHBoxLayout(container)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(5)

                # 创建按钮
                open_button = QPushButton("开")
                close_button = QPushButton("平")

                # 设置按钮状态
                open_button.setCheckable(True)
                close_button.setCheckable(True)
                open_button.setChecked(operation_status.get("开仓", True))
                close_button.setChecked(operation_status.get("平仓", True))

                # 设置按钮样式
                for btn in (open_button, close_button):
                    btn.setFixedWidth(35)
                    btn.setFixedHeight(25)
                    btn.setStyleSheet("""
                        QPushButton {
                            font-size: 14px;
                            padding: 2px;
                            background-color: #e0f7fa;  /* 背景颜色 */
                            border: 1px solid #00bcd4;  /* 边框颜色 */
                            border-radius: 5px;
                            color: #333;
                        }
                        QPushButton:checked {
                            background-color: #00bcd4;  /* 选中状态背景 */
                            color: white;
                            border: 1px solid #008c9e;  /* 选中状态边框 */
                        }
                        QPushButton:hover {
                            background-color: #b2ebf2;
                        }
                        QPushButton:checked:hover {
                            background-color: #00acc1;
                        }
                    """)

                # 连接信号
                def create_toggled_handler(btn_type):
                    def handler(checked):
                        operation = grid_data.row_dict.get("操作", {})
                        operation[btn_type] = checked
                        grid_data.row_dict["操作"] = operation
                        print(f"[GridStrategyTab] 更新操作状态 - {uid}: {operation}")
                        grid_data.data_updated.emit(uid)
                    return handler

                open_button.toggled.connect(create_toggled_handler("开仓"))
                close_button.toggled.connect(create_toggled_handler("平仓"))

                # 将按钮添加到布局
                layout.addWidget(open_button)
                layout.addWidget(close_button)

                # 设置到表格
                self.table.setCellWidget(row_position, i, container)
            else:
                # 填充其他列的数据
                value = grid_data.row_dict.get(col["name"], "")
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_position, i, item)
        print(f"[GridStrategyTab] === 添加 {grid_data.pair} 策略 {uid} 到表格 === ")

    def create_operation_widget(self, row: int) -> QWidget:
        """创建操作按钮组"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        open_button = QPushButton("开")
        close_button = QPushButton("平")

        # 获取策略ID
        uid_item = self.table.item(row, self.get_column_index("标识符"))
        if uid_item:
            uid = uid_item.text()
            
            def on_button_toggled():
                operation = {
                    "开仓": open_button.isChecked(),
                    "平仓": close_button.isChecked()
                }
                grid_data = self.strategy_manager.get_strategy_data(uid)
                if grid_data:
                    print(f"[GridStrategyTab] 更新策略 {uid} 操作状态: {operation}")
                    grid_data.row_dict["操作"] = operation
                    # 发送数据更新信号
                    grid_data.data_updated.emit(uid)

            # 连接信号
            open_button.toggled.connect(on_button_toggled)
            close_button.toggled.connect(on_button_toggled)

        # 设置按钮属性
        for btn in (open_button, close_button):
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setFixedWidth(30)
            btn.setFixedHeight(25)
            btn.setStyleSheet("""
                QPushButton {
                    font-size: 12px;
                    padding: 2px;
                    background-color: #f0f0f0;
                    border: 1px solid #ccc;
                    border-radius: 2px;
                }
                QPushButton:checked {
                    background-color: #4CAF50;
                    color: white;
                    border: 1px solid #45a049;
                }
                QPushButton:hover {
                    background-color: #e0e0e0;
                }
                QPushButton:checked:hover {
                    background-color: #45a049;
                }
            """)

        layout.addWidget(open_button)
        layout.addWidget(close_button)
        return container

    def _update_table_row(self, uid: str):
        """更新表格行数据"""
        try:
            # print(f"\n[GridStrategyTab] === 更新表格行 === {uid}")
            grid_data = self.strategy_manager.get_strategy_data(uid)
            if not grid_data:
                print(f"[GridStrategyTab] 未找到策略数据: {uid}")
                return
            # 查找对应行
            row_found = False
            for row in range(self.table.rowCount()):
                uid_item = self.table.item(row, self.get_column_index("标识符"))
                if uid_item and uid_item.text() == uid:
                    row_found = True
                    # print(f"[GridStrategyTab] 找到策略行: {row}")
                    # 更新各列数据
                    for col in self.COLUMN_DEFINITIONS:
                        col_name = col["name"]
                        if col_name == "操作":
                            continue
                        value = grid_data.row_dict.get(col_name)
                        # print(f"[GridStrategyTab] 更新列 {col_name}: {value}")
                        if value is not None:
                            item = QTableWidgetItem(str(value))
                            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                            self.table.setItem(row, self.get_column_index(col_name), item)
                    break
            if not row_found:
                print(f"[GridStrategyTab] 未找到策略行: {uid}")
        except Exception as e:
            print(f"[GridStrategyTab] 更新表格行错误: {str(e)}")
            print(f"[GridStrategyTab] 错误详情: {traceback.format_exc()}")

    def open_grid_setting(self, uid: str):
        """打开网格设置对话框"""       
        grid_data = self.strategy_manager.get_strategy_data(uid)
        if not grid_data:
            return
        dialog = GridDialog(grid_data)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.save_data(show_message=False)

    def start_strategy(self, uid: str):
        """启动策略"""
        # 检查客户端状态
        if not self.check_client_status():
            self.show_error_message("客户端未连接，请检查网络或配置！")
            return
            
        grid_data = self.strategy_manager.get_strategy_data(uid)
        if not grid_data or not grid_data.grid_levels:
            self.show_error_message("请先设置网格参数！")
            return
            
        try:
            # 订阅交易数据
            success = self.exchange_client.subscribe_pair(grid_data.pair, ["ticker"], uid)
            if not success:
                raise ValueError("订阅交易数据失败")
                
            # 启动策略
            success = self.strategy_manager.start_strategy(uid, self.exchange_client)
            if not success:
                # 如果启动失败，取消订阅
                self.exchange_client.unsubscribe_pair(grid_data.pair, ["ticker"], uid)
                raise ValueError("启动策略失败")
                
            # 更新运行状态，但保留实现盈亏值
            grid_data.row_dict["运行状态"] = "运行中"
            grid_data.data_updated.emit(uid)
                
            # 异步保存数据
            self.save_data(show_message=False)
            self.show_message("启动策略", f"策略 {grid_data.pair} 已成功启动！")
            self.update_thread_info_label()
            
        except Exception as e:
            self.show_error_message(f"启动策略失败: {str(e)}")
            # 确保取消订阅
            self.exchange_client.unsubscribe_pair(grid_data.pair, ["ticker"], uid)

    def stop_strategy(self, uid: str):
        """停止策略"""
        grid_data = self.strategy_manager.get_strategy_data(uid)
        if not grid_data:
            self.show_error_message("策略数据不存在！")
            return
        if not self.strategy_manager.is_strategy_running(uid):
            self.show_message("停止策略", f"策略 {grid_data.pair} 已经停止！")
            return
        try:
            # 先取消订阅
            self.exchange_client.unsubscribe_pair(grid_data.pair, ["ticker"], uid)
            # 停止策略
            success = self.strategy_manager.stop_strategy(uid)
            if not success:
                raise ValueError("停止策略失败")
            self.update_thread_info_label()
            self.show_message("停止策略", f"策略 {grid_data.pair} 已成功停止！")
        
        except Exception as e:
            self.show_error_message(f"停止策略失败: {str(e)}")

    def stop_all_strategies(self):
        """停止所有运行中的策略"""
        try:
            # 获取所有运行中的策略
            running_strategies = [
                uid for uid in self.strategy_manager._data.keys()
                if self.strategy_manager.is_strategy_running(uid)
            ]
            
            if not running_strategies:
                self.show_message("提示", "没有正在运行的策略")
                return
                
            # 确认操作
            response = QMessageBox.question(
                self,
                "确认停止",
                f"确认停止所有运行中的策略（{len(running_strategies)}个）？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if response == QMessageBox.StandardButton.Yes:
                success_count = 0
                for uid in running_strategies:
                    if self.strategy_manager.stop_strategy(uid):
                        success_count += 1
                        
                self.show_message("操作完成", f"成功停止 {success_count}/{len(running_strategies)} 个策略")
                
        except Exception as e:
            self.show_error_message(f"停止策略失败: {str(e)}")

    def toggle_all_operations(self, operation_type: str):
        """切换所有策略的操作状态"""
        try:
            # 获取按钮状态
            button = self.toggle_all_open_button if operation_type == "开仓" else self.toggle_all_close_button
            is_enabled = button.isChecked()
            
            # 更新表格中所有策略的操作按钮状态
            for row in range(self.table.rowCount()):
                # 获取操作按钮容器
                container = self.table.cellWidget(row, self.get_column_index("操作"))
                if container:
                    layout = container.layout()
                    if layout:
                        # 获取对应的按钮（第一个是开仓，第二个是平仓）
                        button_index = 0 if operation_type == "开仓" else 1
                        button = layout.itemAt(button_index).widget()
                        if button:
                            button.setChecked(is_enabled)

                # 同时更新数据模型
                uid_item = self.table.item(row, self.get_column_index("标识符"))
                if uid_item:
                    uid = uid_item.text()
                    grid_data = self.strategy_manager.get_strategy_data(uid)
                    if grid_data:
                        operations = grid_data.row_dict.get("操作", {})
                        operations[operation_type] = is_enabled
                        grid_data.row_dict["操作"] = operations
                        grid_data.update_operation_status(operations)
            
            print(f"[GridStrategyTab] 已{operation_type}设置为: {'启用' if is_enabled else '禁用'}")
            self.save_data(show_message=False)
            
        except Exception as e:
            self.show_error_message(f"切换{operation_type}状态失败: {str(e)}")
            # 恢复按钮状态
            button.setChecked(not is_enabled)

    def close_position(self, uid: str):
        """平仓操作"""
        # 检查客户端状态
        if not self.check_client_status():
            self.show_error_message("客户端未连接，请检查网络或配置！")
            return
            
        grid_data = self.strategy_manager.get_strategy_data(uid)
        if not grid_data:
            self.show_error_message("策略数据不存在！")
            return

        # 检查策略运行状态
        if self.strategy_manager.is_strategy_running(uid):
            self.show_error_message("请先停止策略再进行平仓操作！")
            return

        # 确认平仓操作
        confirm_msg = (f"确认平仓 {grid_data.pair} ?\n"
                    f"方向: {'多仓' if grid_data.is_long() else '空仓'}\n"
                    f"当前层数: {grid_data.row_dict.get('当前层数')}\n")
        
        response = QMessageBox.question(
            self, 
            "平仓确认", 
            confirm_msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if response == QMessageBox.StandardButton.Yes:
            try:
                # 调用策略管理器的平仓方法
                success = self.strategy_manager.close_positions(uid, self.exchange_client)
                if success:
                    self.show_message("平仓结果", "平仓成功")
                    self.save_data(show_message=False)
                else:
                    self.show_error_message("平仓失败，请查看错误日志")
            except Exception as e:
                error_msg = f"平仓失败: {str(e)}"
                print(f"[GridStrategyTab] {error_msg}")
                print(f"[GridStrategyTab] 错误详情: {traceback.format_exc()}")
                self.show_error_message(error_msg)

    def delete_strategy(self, uid: str):
        """删除策略"""
        grid_data = self.strategy_manager.get_strategy_data(uid)
        if not grid_data:
            return

        # 检查是否有持仓
        has_position = False
        for level_config in grid_data.grid_levels.values():
            if level_config.is_filled:
                has_position = True
                break

        if has_position:
            self.show_error_message("策略有持仓，请先平仓后再删除！")
            return

        # 确认删除
        response = QMessageBox.question(
            self, 
            "删除确认", 
            f"确认删除 {grid_data.pair} 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if response == QMessageBox.StandardButton.Yes:
            try:
                print(f"\n[GridStrategyTab] === 删除策略 === {uid}")
                # 取消订阅
                if self.exchange_client:
                    self.exchange_client.unsubscribe_pair(grid_data.pair, ["ticker"], uid)

                # 从表格中移除
                for row in range(self.table.rowCount()):
                    if self.table.item(row, self.get_column_index("标识符")).text() == uid:
                        self.table.removeRow(row)
                        break

                # 从管理器中删除
                self.strategy_manager.delete_strategy(uid)
                self.update_thread_info_label()
                print(f"[GridStrategyTab] 策略已删除: {uid}")
                
                self.save_data(show_message=False)

            except Exception as e:
                self.show_error_message(f"删除失败: {str(e)}")

    def get_column_index(self, column_name: str) -> int:
        """获取列索引"""
        return next(
            (i for i, col in enumerate(self.COLUMN_DEFINITIONS) 
            if col["name"] == column_name),
            -1
        )

    def create_strategy(self, uid: str, pair: str, exchange: str, inst_type: str) -> Optional[GridData]:
        grid_data = self.strategy_manager.create_strategy(uid, pair, exchange, inst_type)
        if grid_data:
            # 设置方向
            is_long = not self.position_mode_button.isChecked()
            grid_data.direction = (
                GridDirection.LONG if self.inst_type == "SPOT" or is_long
                else GridDirection.SHORT
            )
            grid_data.row_dict["方向"] = grid_data.direction.value
            # 初始化操作状态
            grid_data.row_dict["操作"] = {"开仓": True, "平仓": True}
            print(f"[GridStrategyTab] 连接策略 {uid} 的数据更新信号")
            grid_data.data_updated.connect(self._update_table_row)  # 确保这行代码执行
            print(f"[GridStrategyTab] data_updated 信号连接完成")
        return grid_data

    def _handle_strategy_started(self, uid: str):
        """处理策略启动"""
        self._update_strategy_status(uid, "运行中")

    def _handle_strategy_stopped(self, uid: str):
        """处理策略停止"""
        self._update_strategy_status(uid, "已停止")

    def _handle_strategy_status_changed(self, uid: str, status: str):
        """处理策略状态变化"""
        print(f"[GridStrategyTab] Strategy status changed - {uid}: {status}")
        
        # 更新数据模型
        grid_data = self.strategy_manager.get_strategy_data(uid)
        if grid_data:
            grid_data.row_dict["运行状态"] = status
        
        # 更新表格显示
        self._update_strategy_status(uid, status)

    def _update_strategy_status(self, uid: str, status: str):
        """更新策略状态显示"""
        for row in range(self.table.rowCount()):
            uid_item = self.table.item(row, self.get_column_index("标识符"))
            if uid_item and uid_item.text() == uid:
                status_item = QTableWidgetItem(status)
                status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # 根据状态设置颜色
                if status == "运行中":
                    color = QColor("green")
                elif status == "已停止":
                    color = QColor("red")
                elif status == "已平仓":
                    color = QColor("gray")
                elif status == "已添加":
                    color = QColor("blue")
                else:
                    color = QColor("black")
                
                status_item.setForeground(color)
                self.table.setItem(row, self.get_column_index("运行状态"), status_item)
                break

    def _handle_strategy_error(self, uid: str, error_msg: str):
        """处理策略错误"""
        print(f"[GridStrategyTab] Strategy error - {uid}: {error_msg}")
        
        # 查找对应的行
        error_shown = False
        for row in range(self.table.rowCount()):
            uid_item = self.table.item(row, self.get_column_index("标识符"))
            if uid_item and uid_item.text() == uid:
                # 更新状态显示
                status_item = QTableWidgetItem("错误停止")
                status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                status_item.setForeground(QColor("red"))
                self.table.setItem(row, self.get_column_index("运行状态"), status_item)
                error_shown = True
                break
        
        # 只有在该网格确实存在且尚未显示错误时才显示错误消息
        if error_shown:
            self.show_error_message(error_msg)
            # 确保策略已停止
            self.strategy_manager.stop_strategy(uid)

    def pair_to_instId(self, pair: str) -> str:
        """转换交易对格式"""
        try:
            symbol, base = pair.split('/')
            pair_id = f"{symbol}{base}"
            print(f"[GridStrategyTab] 交易对转换: {pair} -> {pair_id}")
            return pair_id
        except ValueError:
            print(f"[GridStrategyTab] 交易对转换失败: {pair}")
            return ""

    def check_client_status_for_actions(self) -> bool:
        """检查交易所客户端的连接状态（用于右键菜单）"""
        return bool(self.exchange_client and self.exchange_client.is_connected)

    def show_message(self, title: str, message: str):
        """显示信息对话框"""
        QMessageBox.information(self, title, message)

    def show_error_message(self, message: str, title: str = "错误"):
        """显示错误对话框"""
        QMessageBox.critical(self, title, message)
        print(f"[GridStrategyTab] Error: {message}")

    def closeEvent(self, event):
        """关闭窗口前确保所有操作完成"""
        print("[GridStrategyTab] === 窗口关闭事件触发 ===")
        try:
            # 停止所有策略，设置较短的超时时间
            print("[GridStrategyTab] 停止所有策略")
            threading.Thread(target=self.strategy_manager.stop_all_strategies, daemon=True).start()
            
            # 等待保存和加载线程完成，但设置较短的超时时间
            if self._save_thread and self._save_thread.is_alive():
                print("[GridStrategyTab] 等待保存线程完成...")
                self._save_thread.join(timeout=2)  # 缩短超时时间
                
            if self._load_thread and self._load_thread.is_alive():
                print("[GridStrategyTab] 等待加载线程完成...")
                self._load_thread.join(timeout=2)  # 缩短超时时间
            
            # 在后台线程中保存数据
            threading.Thread(
                target=lambda: self.save_data(show_message=False), 
                daemon=True
            ).start()

            # 清理客户端资源
            if self.exchange_client:
                print("[GridStrategyTab] 销毁客户端")
                self.exchange_client = None
                self._update_ws_status(False, False)
                threading.Thread(
                    target=lambda: self.client_factory.destroy_client(self.tab_id),
                    daemon=True
                ).start()

            # 直接接受关闭事件
            event.accept()
            
        except Exception as e:
            print(f"[GridStrategyTab] 关闭窗口时发生错误: {e}")
            print(f"[GridStrategyTab] 错误详情: {traceback.format_exc()}")
            # 确保窗口能关闭
            event.accept()

    def save_data(self, show_message: bool = True):
        """保存策略数据"""
        def _save():
            try:
                # print("[GridStrategyTab] 开始保存数据...")
                data = {
                    'inst_type': self.inst_type,
                    'strategies': {},
                    'running_strategies': []
                }
                
                for uid in list(self.strategy_manager._data.keys()):
                    grid_data = self.strategy_manager.get_strategy_data(uid)
                    if grid_data:
                        # 临时更新运行状态
                        original_status = grid_data.row_dict.get("运行状态", "")
                        grid_data.row_dict["运行状态"] = "已保存"
                        
                        data['strategies'][uid] = grid_data.to_dict()
                        
                        # 恢复原始运行状态
                        grid_data.row_dict["运行状态"] = original_status
                        
                        if self.strategy_manager.is_strategy_running(uid):
                            data['running_strategies'].append(uid)

                # 保存到JSON文件
                create_file_if_not_exists(self.data_path)
                with open(self.data_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                
                # print("[GridStrategyTab] 数据保存成功")
                if show_message:
                    self.save_completed.emit("数据已成功保存！")

            except Exception as e:
                error_msg = f"保存数据失败: {str(e)}"
                print(f"[GridStrategyTab] {error_msg}")
                print(f"[GridStrategyTab] 错误详情: {traceback.format_exc()}")
                if show_message:
                    self.save_failed.emit(error_msg)
            finally:
                self._save_thread = None

        # 如果已有保存线程在运行，等待其完成
        if self._save_thread and self._save_thread.is_alive():
            print("[GridStrategyTab] 已有保存操作在进行中...")
            return
        self._save_thread = threading.Thread(name=f"GridStrategy-Save-{self.tab_id}", target=_save, daemon=True)
        self._save_thread.start()

    def _add_row_slot(self, uid: str):
        """在主线程中添加行"""
        try:
            self.add_strategy_to_table(uid)
        except Exception as e:
            print(f"[GridStrategyTab] 添加行失败: {e}")
            print(f"[GridStrategyTab] 错误详情: {traceback.format_exc()}")

    def _show_message_slot(self, title: str, message: str):
        """在主线程中显示消息框"""
        QMessageBox.information(self, title, message)

    def _show_error_slot(self, message: str):
        """在主线程中显示错误框"""
        QMessageBox.critical(self, "错误", message)

    def load_data(self, delayed: bool = False):
        """加载策略数据"""
        def _load():
            try:
                if delayed:
                    print("[GridStrategyTab] 延迟加载模式，等待5秒...")
                    time.sleep(5)
                print("[GridStrategyTab] 开始加载数据...")
                create_file_if_not_exists(self.data_path)
                # 读取数据文件
                with open(self.data_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()  # 读取内容并去除多余的空白
                    if not content:  # 文件为空
                        print(f"[GridStrategyTab] 文件为空，使用默认数据")
                        data = {"inst_type": self.inst_type, "strategies": {}, "running_strategies": []}
                    else:
                        data = json.loads(content)  # 尝试加载 JSON 数据

                if not isinstance(data, dict) or 'strategies' not in data:
                    raise ValueError("无效的数据格式")

                # 加载之前，停止所有运行中的策略
                self.strategy_manager.stop_all_strategies()
                
                # 清空当前数据和表格
                self.strategy_manager._data.clear()
                self.table.setRowCount(0)
                
                # 恢复所有策略数据
                loaded_count = 0
                for uid, strategy_data in data['strategies'].items():
                    try:
                        print(f"\n[GridStrategyTab] === 加载策略 {uid} ===")
                        print(f"  交易对: {strategy_data['pair']}")
                        print(f"  交易所: {strategy_data['exchange']}")
                        
                        # 创建策略
                        grid_data = self.strategy_manager.create_strategy(
                            uid,
                            strategy_data["pair"],
                            strategy_data["exchange"],
                            strategy_data["inst_type"]
                        ) 
                        if grid_data:
                            # 设置方向
                            grid_data.direction = GridDirection(strategy_data["direction"])
                            
                            # 首先恢复实现盈亏值
                            original_profit = Decimal(str(strategy_data.get('total_realized_profit', '0')))
                            grid_data.total_realized_profit = original_profit
                            print(f"[GridStrategyTab] 恢复策略 {uid} 实现盈亏: {original_profit}")
                            
                            # 恢复网格配置
                            for level_str, config in strategy_data.get("grid_levels", {}).items():
                                level = int(level_str)
                                config_data = {
                                    "间隔%": config["间隔%"],
                                    "开仓反弹%": config["开仓反弹%"],
                                    "平仓反弹%": config["平仓反弹%"],
                                    "止盈%": config["止盈%"],
                                    "成交额": config["成交额"]
                                }
                                if config["已开仓"]:
                                    filled_data = {
                                        "filled_amount": config["成交量"],
                                        "filled_price": config["开仓价"],
                                        "filled_time": datetime.fromisoformat(config["开仓时间"]) if config["开仓时间"] else None,
                                        "is_filled": config["已开仓"],
                                        "order_id": config["order_id"]
                                    }
                                    config_data.update(filled_data)
                                grid_data.update_level(level, config_data)
                                
                            # 恢复UI显示数据
                            grid_data.row_dict.update(strategy_data["row_dict"])
                            # 确保实现盈亏正确显示
                            grid_data.row_dict["实现盈亏"] = str(original_profit)
                            
                            # 检查并设置正确的运行状态
                            grid_status = grid_data.get_grid_status()
                            filled_levels = sum(1 for config in grid_data.grid_levels.values() 
                                            if config.is_filled)
                            # 设置初始状态
                            initial_status = "已添加"  # 默认状态
                            # 如果有持仓，根据持仓情况设置状态
                            if filled_levels > 0:
                                # 检查是否有持仓价值
                                position_value = grid_data.row_dict.get("持仓价值")
                                if position_value and float(position_value.replace(",", "")) > 0:
                                    initial_status = "已停止"  # 有持仓但策略未运行
                                else:
                                    initial_status = "已平仓"  # 无持仓
                            grid_data.row_dict["运行状态"] = initial_status
                            
                            # 在主线程中添加到表格
                            self.add_row_signal.emit(uid)
                            grid_data.data_updated.connect(self._update_table_row)
                            print(f"[GridStrategyTab] 策略 {uid} 加载完成，状态: {initial_status}")
                            print(f"[GridStrategyTab] 当前实现盈亏: {grid_data.total_realized_profit}")
                            
                        loaded_count += 1
                    except Exception as e:
                        print(f"[GridStrategyTab] 加载策略 {uid} 失败: {e}")
                        print(f"[GridStrategyTab] 错误详情: {traceback.format_exc()}")
                        continue
                        
                print("[GridStrategyTab] 数据加载完成")
                if not delayed:
                    if loaded_count > 0:
                        self.load_completed.emit(f"成功加载 {loaded_count} 个策略！")
                        
            except Exception as e:
                error_msg = f"加载数据失败: {str(e)}"
                print(f"[GridStrategyTab] {error_msg}")
                print(f"[GridStrategyTab] 错误详情: {traceback.format_exc()}")
                
            finally:
                self._load_thread = None
                
        # 如果已有加载线程在运行，等待其完成
        if self._load_thread and self._load_thread.is_alive():
            print("[GridStrategyTab] 已有加载操作在进行中...")
            return
            
        # 创建新的加载线程
        self._load_thread = threading.Thread(
            name=f"GridStrategy-Load-{self.tab_id}",
            target=_load,
            daemon=True
        )
        self._load_thread.start()

    def refresh_strategy_data(self, uid: str):
        """手动刷新策略行数据"""
        print(f"[GridStrategyTab] === 手动刷新策略数据 === {uid}")
        try:
            grid_data = self.strategy_manager.get_strategy_data(uid)
            if not grid_data:
                self.show_error_signal.emit("未找到策略数据")
                return
                    
            # 重新计算网格状态
            grid_status = grid_data.get_grid_status()
            
            # 如果没有网格配置，重置显示数据
            if not grid_status["is_configured"]:
                grid_data.row_dict.update({
                    "当前层数": "未设置",
                    "持仓价值": "",
                    "持仓盈亏": "",
                    "持仓均价": "",
                    "最后价格": "",
                    "尾单价格": "",
                    "开仓触发价": "",
                    "止盈触发价": "",
                    "最后时间": ""
                })
            else:
                # 更新层数显示
                current_level = (f"{grid_status['total_levels']}/{grid_status['total_levels']}"
                            if grid_status["is_full"]
                            else f"{grid_status['filled_levels']}/{grid_status['total_levels']}")
                grid_data.row_dict["当前层数"] = current_level

            grid_data.data_updated.emit(uid)

            # 构建刷新信息
            info_text = f"""
            策略数据已刷新:
            交易对: {grid_data.pair}
            方向: {grid_data.direction.value}
            当前层数: {grid_data.row_dict.get('当前层数', '未设置')}
            最新价格: {grid_data.row_dict.get('最后价格', 'N/A')}
            持仓均价: {grid_data.row_dict.get('持仓均价', 'N/A')}
            持仓价值: {grid_data.row_dict.get('持仓价值', 'N/A')}
            持仓盈亏: {grid_data.row_dict.get('持仓盈亏', 'N/A')}
            """
            self.show_message_signal.emit("数据已刷新", info_text)

        except Exception as e:
            print(f"[GridStrategyTab] 刷新数据失败: {e}")
            print(f"[GridStrategyTab] 错误详情: {traceback.format_exc()}")
            self.show_error_signal.emit(f"刷新数据失败: {str(e)}")