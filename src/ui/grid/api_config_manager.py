# src/ui/components/api_config_manager.py

import time
from typing import Dict, Optional
import os
import json
import threading
import traceback
from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, 
    QLabel, QComboBox, QMessageBox, QApplication
)
from qtpy.QtCore import Qt, QTimer, Signal, QObject
from src.exchange.base_client import InstType, BaseClient 
from src.exchange.client_factory import ExchangeClientFactory

class APIConfigManager(QObject):
    """API配置管理器"""
    # 信号定义
    config_saved = Signal(str)  # message
    config_loaded = Signal(str)  # message 
    config_error = Signal(str)  # error_message
    config_updated = Signal(dict)  # 新的配置数据
    exchange_changed = Signal(str)  # new_exchange
    
    def __init__(self, tab_id: str, inst_type: InstType, client_factory: ExchangeClientFactory):
        super().__init__()
        self.tab_id = tab_id
        self.inst_type = inst_type
        self.client_factory = client_factory
        self.client_factory.client_status_changed.connect(self._handle_client_status)
        self.config_path = os.path.join('./config/api_config', 'api_config.json')
        self.current_exchange = None
        self.config = self._create_default_config()
        
        # 创建用于控制API信息显示的定时器
        self.show_api_timer = QTimer(self)
        self.show_api_timer.timeout.connect(self._hide_api_info)
        
        # 创建UI组件
        self.setup_ui_components()

        self.connection_status = "未连接"
        self.public_ws_connected = False
        self.private_ws_connected = False

        # 添加状态检查定时器
        self.status_check_timer = QTimer(self)
        self.status_check_timer.timeout.connect(self._check_connection_status)
        self.status_check_timer.start(5000)  # 每5秒检查一次

    def update_connection_status(self, status: str):
        """更新连接状态"""
        self.connection_status = status
        self.connection_status_label.setText(f"连接状态：{status}")
        
        # 根据状态设置颜色
        if status == "就绪":
            self.connection_status_label.setStyleSheet("color: green")
        elif status in ["连接中", "验证中"]:
            self.connection_status_label.setStyleSheet("color: orange")
        else:
            self.connection_status_label.setStyleSheet("color: red")

    def setup_ui_components(self) -> QWidget:
        """创建API配置UI组件"""
        self.container = QWidget()
        layout = QVBoxLayout(self.container)
        
        # === 用户输入区域 ===
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
        
        layout.addLayout(user_input_layout)
        
        # === 操作区域 ===
        operation_layout = QHBoxLayout()
        
        # 交易所选择
        exchange_layout = QHBoxLayout()
        exchange_layout.addWidget(QLabel("交易所:"))
        self.exchange_combo = QComboBox()
        self.exchange_combo.currentTextChanged.connect(self.handle_exchange_changed)
        
        # 获取支持的交易所列表
        available_exchanges = self.client_factory.registry.get_available_exchanges(self.inst_type)
        
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
        self.save_api_button.clicked.connect(self.save_config)
        operation_layout.addWidget(self.save_api_button)
        
        self.load_api_button = QPushButton("加载配置")
        self.load_api_button.clicked.connect(self.load_config)
        operation_layout.addWidget(self.load_api_button)
        
        # self.test_connection_button = QPushButton("测试连接") 
        # self.test_connection_button.clicked.connect(self.test_connection)
        # operation_layout.addWidget(self.test_connection_button)
        
        # 连接状态标签
        self.connection_status_label = QLabel("连接状态：未连接")
        self.connection_status_label.setStyleSheet("color: red;")
        operation_layout.addWidget(self.connection_status_label)
        
        self.public_ws_label = QLabel("公有：✗")
        self.public_ws_label.setStyleSheet("color: red;")
        operation_layout.addWidget(self.public_ws_label)
        
        self.private_ws_label = QLabel("私有：✗")
        self.private_ws_label.setStyleSheet("color: red;")
        operation_layout.addWidget(self.private_ws_label)
        
        operation_layout.addStretch()
        layout.addLayout(operation_layout)
        
        return self.container

    def _handle_client_status(self, tab_id: str, status: str):
        """处理客户端状态变化"""
        if tab_id != self.tab_id:
            return
            
        # 更新状态显示
        self.connection_status_label.setText(f"连接状态：{status}")
        self.connection_status_label.setStyleSheet(
            "color: green" if status == "就绪" else
            "color: orange" if status in ["连接中", "验证中"] else
            "color: red"
        )
        
        # 获取最新的 WS 状态
        if status == "就绪":
            client = self.client_factory.get_client(self.tab_id)
            if client:
                ws_status = client.get_ws_status()
                # 分别更新公有和私有状态
                self.update_ws_status(True, ws_status.get('public', False))
                self.update_ws_status(False, ws_status.get('private', False))

    def _check_connection_status(self):
        """定期检查连接状态"""
        client = self.client_factory.get_client(self.tab_id)
        if client:
            ws_status = client.get_ws_status()
            if ws_status['public'] != self.public_ws_connected:
                self.update_ws_status(True, ws_status['public'])
            if ws_status['private'] != self.private_ws_connected:
                self.update_ws_status(False, ws_status['private'])
            
            # 如果都断开了，更新连接状态
            if not ws_status['public'] and not ws_status['private']:
                self.update_connection_status("未连接")

    def update_ws_status(self, is_public: bool, connected: bool):
        """更新WebSocket状态"""
        # print(f"\n=== WebSocket状态更新 ===")
        # print(f"[APIConfigManager] 收到更新: {'公有' if is_public else '私有'} - {'已连接' if connected else '未连接'}")
        
        # 添加断开连接的处理
        if not connected:
            if is_public and self.public_ws_connected:
                print("[APIConfigManager] 公共WebSocket断开连接")
            elif not is_public and self.private_ws_connected:
                print("[APIConfigManager] 私有WebSocket断开连接")

        # 更新状态
        if is_public:
            if self.public_ws_connected != connected:  # 只在状态变化时更新
                self.public_ws_connected = connected
                self.public_ws_label.setText(f"公有：{'✓' if connected else '✗'}")
                self.public_ws_label.setStyleSheet(f"color: {'green' if connected else 'red'}")
                # print(f"[APIConfigManager] 更新后公有状态: {self.public_ws_connected}")
        else:
            if self.private_ws_connected != connected:  # 只在状态变化时更新
                self.private_ws_connected = connected
                self.private_ws_label.setText(f"私有：{'✓' if connected else '✗'}")
                self.private_ws_label.setStyleSheet(f"color: {'green' if connected else 'red'}")
                # print(f"[APIConfigManager] 更新后私有状态: {self.private_ws_connected}")
            
        # 强制更新UI
        QApplication.processEvents()  # 处理所有待处理的事件
        # print(f"[APIConfigManager] 当前状态:")
        # print(f"- 公有连接状态: {self.public_ws_connected}")
        # print(f"- 私有连接状态: {self.private_ws_connected}")

    def _create_default_config(self) -> dict:
        """创建默认配置"""
        available_exchanges = self.client_factory.registry.get_available_exchanges(self.inst_type)
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

    def load_config(self):
            """加载API配置"""
            try:
                # 确保文件存在
                os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
                if os.path.exists(self.config_path):
                    with open(self.config_path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        # print(f"[APIConfigManager] 从文件加载的原始内容:\n{content}")
                        if not content:  # 空文件
                            self.config = self._create_default_config()
                            # print(f"[APIConfigManager] 文件为空，使用默认配置: {json.dumps(self.config, indent=2)}")
                        else:
                            self.config = json.loads(content)
                            # print(f"[APIConfigManager] 解析后的配置:\n{json.dumps(self.config, indent=2)}")
                else:
                    self.config = self._create_default_config()
                    # print(f"[APIConfigManager] 配置文件不存在，使用默认配置: {json.dumps(self.config, indent=2)}")
                
                # 设置当前交易所
                current_exchange = self.config.get('current', '').lower()
                if not current_exchange:
                    available_exchanges = self.client_factory.registry.get_available_exchanges(self.inst_type)
                    current_exchange = available_exchanges[0] if available_exchanges else "bitget"
                    self.config['current'] = current_exchange
                    # print(f"[APIConfigManager] 未指定当前交易所，设置为: {current_exchange}")

                # 获取当前交易所的API配置
                exchange_config = self.config.get(current_exchange, {})
                # print(f"[APIConfigManager] 当前交易所 {current_exchange} 的配置: {json.dumps(exchange_config, indent=2)}")
                
                # 更新UI
                self.current_exchange = current_exchange.capitalize()
                self.exchange_combo.blockSignals(True)
                self.exchange_combo.setCurrentText(self.current_exchange)
                self.exchange_combo.blockSignals(False)

                self.user_id_input.setText(exchange_config.get('user_id', ''))
                self.api_key_input.setText(exchange_config.get('api_key', ''))
                self.secret_key_input.setText(exchange_config.get('api_secret', ''))
                self.passphrase_input.setText(exchange_config.get('passphrase', ''))

                # 如果有完整的API配置，发送更新信号
                if all([
                    exchange_config.get('api_key'),
                    exchange_config.get('api_secret'),
                    exchange_config.get('passphrase')
                ]):
                    # print(f"[APIConfigManager] API 配置完整，发送 config_updated 信号")
                    self.config_updated.emit(exchange_config)

            except Exception as e:
                error_msg = f"加载配置失败: {str(e)}"
                print(f"[APIConfigManager] {error_msg}")
                print(f"[APIConfigManager] 错误详情: {traceback.format_exc()}")
                self.config_error.emit(error_msg)

    def save_config(self, auto_save: bool = False):
        """保存API配置"""
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
                self.config_saved.emit("API配置已保存")
                self.config_updated.emit(new_config)

        except Exception as e:
            error_msg = f"保存API配置失败: {str(e)}"
            print(f"[APIConfigManager] {error_msg}")
            print(f"[APIConfigManager] 错误详情: {traceback.format_exc()}")
            self.config_error.emit(error_msg)

    def handle_exchange_changed(self, new_exchange: str):
        """处理交易所切换"""
        new_exchange = new_exchange.lower()
        
        if not self.current_exchange:
            self.current_exchange = new_exchange
            return
            
        if new_exchange == self.current_exchange.lower():
            return

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
        
        # 发送交易所变更信号
        self.exchange_changed.emit(new_exchange)
        
        # 保存配置
        self.save_config(auto_save=True)

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

    def get_current_config(self) -> dict:
        """获取当前API配置"""
        return {
            'user_id': self.user_id_input.text().strip(),
            'api_key': self.api_key_input.text().strip(),
            'api_secret': self.secret_key_input.text().strip(),
            'passphrase': self.passphrase_input.text().strip(),
            'exchange': self.exchange_combo.currentText().lower()
        }

    def get_ui_container(self) -> QWidget:
        """获取UI容器组件"""
        return self.container