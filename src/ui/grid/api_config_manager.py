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
from src.utils.common.common import create_file_if_not_exists  # 假设这是你的工具函数


class APIConfigManager(QObject):
    """API配置管理器"""
    # 信号定义
    config_error = Signal(str)
    config_updated = Signal(dict, object)  # 修改为支持 config 和 client
    exchange_changed = Signal(str)
    save_config_signal = Signal(str)  # 修改为 save_config_signal
    load_config_signal = Signal(str)  # 修改为 load_config_signal
    check_status_signal = Signal()
    
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
        self.status_check_timer.start(60000)  # 每60秒检查一次

    def setup_ui_components(self) -> QWidget:
        """创建API配置UI组件，只显示 api_key, api_secret 和 passphrase 的输入框"""
        self.container = QWidget()
        layout = QVBoxLayout(self.container)
        
        # === 用户输入区域 ===
        user_input_layout = QHBoxLayout()
        
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
        
        self.reconnect_button = QPushButton("重新连接")
        self.reconnect_button.clicked.connect(self._handle_reconnect)
        operation_layout.addWidget(self.reconnect_button)
        
        self.check_status_button = QPushButton("检查状态")
        self.check_status_button.clicked.connect(self._handle_check_status)
        operation_layout.addWidget(self.check_status_button)
        
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

    def save_config(self):
        """仅保存配置到文件"""
        config = {
            'current': self.exchange_combo.currentText().lower(),
            self.exchange_combo.currentText().lower(): {
                'user_id': '',  # 保持数据结构完整，但留空
                'api_key': self.api_key_input.text(),
                'api_secret': self.secret_key_input.text(),
                'passphrase': self.passphrase_input.text()
            }
        }
        # 合并现有配置，避免覆盖其他交易所的数据
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r', encoding='utf-8') as f:
                existing_config = json.load(f)
            existing_config.update(config)
            config = existing_config
        
        try:
            create_file_if_not_exists(self.config_path)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
            print(f"[APIConfigManager] 配置已保存到 {self.config_path}")
            self.save_config_signal.emit("配置已保存")
        except Exception as e:
            self.config_error.emit(f"保存配置失败: {str(e)}")

    def _load_config_to_ui(self):
        """仅加载配置到输入框"""
        try:
            if not os.path.exists(self.config_path):
                print(f"[APIConfigManager] 配置文件不存在: {self.config_path}")
                return
                
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            current_exchange = config.get('current', 'bitget')
            exchange_config = config.get(current_exchange, {})
            
            self.exchange_combo.setCurrentText(current_exchange.capitalize())
            self.api_key_input.setText(exchange_config.get('api_key', ''))
            self.secret_key_input.setText(exchange_config.get('api_secret', ''))
            self.passphrase_input.setText(exchange_config.get('passphrase', ''))
            print(f"[APIConfigManager] 配置已加载到输入框")
            self.load_config_signal.emit("配置已加载")
            
        except Exception as e:
            self.config_error.emit(f"加载配置失败: {str(e)}")

    def _handle_reconnect(self):
        """处理重新连接"""
        if not self.client_factory:
            self.config_error.emit("客户端工厂未初始化")
            return
            
        config = self.get_current_config()
        if not all([config.get('api_key'), config.get('api_secret'), config.get('passphrase')]):
            self.config_error.emit("API配置不完整")
            return
            
        # 销毁现有客户端
        self.client_factory.destroy_client(self.tab_id, self.inst_type)
        
        # 创建并连接新客户端
        client = self.client_factory.create_client(
            self.tab_id,
            self.current_exchange,
            config,
            self.inst_type
        )
        if client:
            self.config_updated.emit(config, client)  # 保持两个参数
            print(f"[APIConfigManager] 客户端重新连接触发")
        else:
            self.config_error.emit("重新连接失败，无法创建客户端")

    def _handle_check_status(self):
        """检查并更新连接状态"""
        client = self.client_factory.get_client(self.tab_id, self.inst_type)
        if not client:
            self.update_connection_status("未连接")
            self.update_ws_status(True, False)
            self.update_ws_status(False, False)
            status_msg = "客户端状态检查:\n客户端未连接"
            QMessageBox.warning(None, "连接状态", status_msg)
            return
                
        ws_status = client.get_ws_status()
        self.update_ws_status(True, ws_status.get('public', False))
        self.update_ws_status(False, ws_status.get('private', False))
        self.update_connection_status("就绪" if client.is_connected else "未连接")
        print(f"[APIConfigManager] 连接状态已检查更新: {ws_status}")
        
        # 准备反馈消息
        status_msg = "客户端状态检查:\n"
        status_msg += f"客户端连接: {'已连接' if client.is_connected else '未连接'}\n"
        status_msg += f"公共WebSocket: {'已连接' if ws_status.get('public') else '未连接'}\n"
        status_msg += f"私有WebSocket: {'已连接' if ws_status.get('private') else '未连接'}"
        
        # 根据连接状态显示不同样式的弹窗
        if client.is_connected and all(ws_status.values()):
            QMessageBox.information(None, "连接状态", status_msg)
        else:
            QMessageBox.warning(None, "连接状态", status_msg)

    def load_config(self):
        """加载配置但不自动连接"""
        self._load_config_to_ui()

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
        client = self.client_factory.get_client(self.tab_id, self.inst_type)  # 修正参数
        if not client:
            self.update_connection_status("未连接")
            return
        ws_status = client.get_ws_status()
        self.update_ws_status(True, ws_status.get('public', False))
        self.update_ws_status(False, ws_status.get('private', False))
        if ws_status['public'] and ws_status['private']:
            self.update_connection_status("就绪")
        elif not ws_status['public'] and not ws_status['private']:
            self.update_connection_status("未连接")
        else:
            self.update_connection_status("部分连接")

    def _connect_client_signals(self, client: BaseClient):
        """连接客户端信号"""
        try:
            print(f"[APIConfigManager] === 连接客户端信号 ===")
            print(f"  客户端类型: {client.inst_type.name}")
            
            # 断开现有连接
            try:
                client.connection_status.disconnect()
                client.public_connected.disconnect()
                client.public_disconnected.disconnect()
                client.private_connected.disconnect()
                client.private_disconnected.disconnect()
            except TypeError:
                pass

            # 连接信号
            client.connection_status.connect(self.update_connection_status)
            client.public_connected.connect(lambda: self.update_ws_status(True, True))
            client.public_disconnected.connect(lambda: self.update_ws_status(True, False))
            client.private_connected.connect(lambda: self.update_ws_status(False, True))
            client.private_disconnected.connect(lambda: self.update_ws_status(False, False))

            # 初始状态同步
            ws_status = client.get_ws_status()
            self.update_ws_status(True, ws_status.get('public', False))
            self.update_ws_status(False, ws_status.get('private', False))

            print(f"[APIConfigManager] 客户端信号连接完成")
        except Exception as e:
            print(f"[APIConfigManager] 连接客户端信号失败: {e}")
            self.config_error.emit(f"连接客户端信号失败: {str(e)}")

    def update_ws_status(self, is_public: bool, connected: bool):
        """更新WebSocket状态
        Args:
            is_public (bool): 是否是公共WS
            connected (bool): 是否连接
        """
        # print(f"[APIConfigManager] 更新WebSocket状态 - {'公共' if is_public else '私有'}: {'已连接' if connected else '未连接'}")
        if is_public:
            self.public_ws_connected = connected
            self.public_ws_label.setText(f"公有：{'✓' if connected else '✗'}")
            self.public_ws_label.setStyleSheet(f"color: {'green' if connected else 'red'}")
        else:
            self.private_ws_connected = connected
            self.private_ws_label.setText(f"私有：{'✓' if connected else '✗'}")
            self.private_ws_label.setStyleSheet(f"color: {'green' if connected else 'red'}")
            
        QApplication.processEvents()  # 强制更新UI

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
        self.api_key_input.setText(exchange_config.get('api_key', ''))
        self.secret_key_input.setText(exchange_config.get('api_secret', ''))
        self.passphrase_input.setText(exchange_config.get('passphrase', ''))
        
        # 更新当前交易所
        self.current_exchange = new_exchange.capitalize()
        self.config['current'] = new_exchange
        
        # 发送交易所变更信号
        self.exchange_changed.emit(new_exchange)
        
        # 保存配置
        self.save_config()

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
            'user_id': '',  # 保持数据结构完整，但留空
            'api_key': self.api_key_input.text().strip(),
            'api_secret': self.secret_key_input.text().strip(),
            'passphrase': self.passphrase_input.text().strip(),
            'exchange': self.exchange_combo.currentText().lower()
        }

    def get_ui_container(self) -> QWidget:
        """获取UI容器组件"""
        return self.container