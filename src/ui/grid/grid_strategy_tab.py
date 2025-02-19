# src/ui/tabs/grid_strategy_tab.py

import os
import threading
import traceback
import uuid
from typing import Optional
from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QMessageBox, QDialog
)
from qtpy.QtCore import Qt, QTimer

from src.exchange.base_client import ExchangeType, BaseClient
from src.exchange.client_factory import ExchangeClientFactory
from src.ui.grid.api_config_manager import APIConfigManager
from src.ui.grid.grid_controls import GridControls
from src.ui.grid.grid_table import GridTable
from src.ui.grid.strategy_manager_wrapper import StrategyManagerWrapper
from src.ui.grid.grid_settings_aidlog import GridDialog


class GridStrategyTab(QWidget):
    """网格策略Tab页 - 重构后的主类实现"""
    
    def __init__(self, inst_type: str, client_factory: ExchangeClientFactory):
        super().__init__()
        # 基础配置
        self.inst_type = inst_type
        self.client_factory = client_factory
        self.tab_id = str(uuid.uuid4())
        self.exchange_client: Optional[BaseClient] = None
        
        # 创建子组件
        self.api_manager = APIConfigManager(
            self.tab_id,
            ExchangeType.SPOT if inst_type == "SPOT" else ExchangeType.FUTURES,
            client_factory
        )
        self.grid_controls = GridControls(inst_type)
        self.strategy_wrapper = StrategyManagerWrapper(inst_type, client_factory)
        self.grid_table = GridTable(self.strategy_wrapper)
        
        # 设置UI
        self.setup_ui()
        # 加载API配置
        self.api_manager.load_config()
        # 连接信号
        self._connect_signals()
        # 自动连接默认交易所
        QTimer.singleShot(500, self._auto_connect_exchange)
        # 加载策略数据
        self.strategy_wrapper.load_strategies()

    def setup_ui(self):
        """设置UI布局"""
        layout = QVBoxLayout(self)
        
        # 添加API配置区域
        layout.addWidget(self.api_manager.get_ui_container())
        
        # 添加网格控制区域
        layout.addWidget(self.grid_controls)
        
        # 添加策略表格
        layout.addWidget(self.grid_table)

        # self.grid_table = GridTable(self.strategy_wrapper)
        
        self.setLayout(layout)

    def _connect_signals(self):
        """连接所有组件信号"""
        # API配置管理器信号
        self.api_manager.config_error.connect(self.show_error_message)
        self.api_manager.config_updated.connect(self._handle_api_config_updated)
        self.api_manager.exchange_changed.connect(self._handle_exchange_changed)

        # 网格控制信号
        self.grid_controls.pair_added.connect(self._handle_pair_added)
        self.grid_controls.stop_all_requested.connect(self._handle_stop_all_requested)
        self.grid_controls.operation_toggled.connect(self._handle_operation_toggled)
        self.grid_controls.position_mode_changed.connect(self._handle_position_mode_changed)
        
        # 表格信号
        self.grid_table.strategy_setting_requested.connect(self._handle_strategy_setting)
        self.grid_table.strategy_start_requested.connect(self._handle_strategy_start)
        self.grid_table.strategy_stop_requested.connect(self._handle_strategy_stop)
        self.grid_table.strategy_delete_requested.connect(self._handle_strategy_delete)
        self.grid_table.strategy_close_requested.connect(self._handle_strategy_close)
        self.grid_table.strategy_refresh_requested.connect(self._handle_strategy_refresh)
        
        # 策略管理器信号
        self.strategy_wrapper.strategy_added.connect(self._handle_strategy_added)
        self.strategy_wrapper.strategy_deleted.connect(self._handle_strategy_deleted)
        self.strategy_wrapper.strategy_updated.connect(self._handle_strategy_updated)
        self.strategy_wrapper.strategy_error.connect(self._handle_strategy_error)
        self.strategy_wrapper.strategy_started.connect(self._handle_strategy_started)
        self.strategy_wrapper.strategy_stopped.connect(self._handle_strategy_stopped)
        
        # 添加客户端状态信号连接
        self.client_factory.client_status_changed.connect(self._handle_client_status_changed)
        self.client_factory.client_created.connect(self._handle_client_created)

    def _handle_client_status_changed(self, tab_id: str, status: str):
        """处理客户端状态变化"""
        if tab_id == self.tab_id:
            self.api_manager.update_connection_status(status)

    def _handle_client_created(self, client: BaseClient):
        """处理客户端创建完成"""
        if hasattr(client, 'ws_status_changed'):
            print(f"[GridStrategyTab] 连接WebSocket状态信号 - client: {client}")
            # 修改信号连接方式
            def handle_ws_status(is_public: bool, connected: bool):
                print(f"[GridStrategyTab] 收到WebSocket状态更新 - {'公有' if is_public else '私有'}: {'已连接' if connected else '未连接'}")
                self.api_manager.update_ws_status(is_public, connected)
            
            client.ws_status_changed.connect(handle_ws_status)

    def _handle_ws_status_changed(self, is_public: bool, connected: bool):
        """处理WebSocket状态变化"""
        print(f"[GridStrategyTab] WebSocket状态变化 - {'公有' if is_public else '私有'}: {'已连接' if connected else '未连接'}")
        self.api_manager.update_ws_status(is_public, connected)

    def _auto_connect_exchange(self):
        """自动连接默认交易所"""
        try:
            if self.exchange_client:  # 如果已经有客户端实例，直接返回
                return
                
            # 获取当前配置
            current_exchange = self.api_manager.exchange_combo.currentText().lower()
            config = self.api_manager.get_current_config()
            
            # 检查配置完整性
            if all([
                config.get('api_key'),
                config.get('api_secret'),
                config.get('passphrase')
            ]):
                # 创建客户端
                exchange_type = ExchangeType.SPOT if self.inst_type == "SPOT" else ExchangeType.FUTURES
                self.exchange_client = self.client_factory.create_client(
                    self.tab_id,
                    current_exchange,
                    config,
                    exchange_type
                )
        except Exception as e:
            print(f"[GridStrategyTab] 自动连接交易所失败: {e}")
            print(f"[GridStrategyTab] 错误详情: {traceback.format_exc()}")

    def _handle_api_config_updated(self, config: dict):
        """处理API配置更新"""
        try:
            # 如果有运行中的策略，先停止
            if self.strategy_wrapper.has_running_strategies():
                self._handle_stop_all_requested()

            # 断开现有客户端
            if self.exchange_client:
                self.exchange_client = None
                
            # 检查配置完整性
            if all([
                config.get('api_key'),
                config.get('api_secret'),
                config.get('passphrase')
            ]):
                # 创建新客户端
                exchange_type = ExchangeType.SPOT if self.inst_type == "SPOT" else ExchangeType.FUTURES
                self.exchange_client = self.client_factory.create_client(
                    self.tab_id,
                    self.api_manager.current_exchange.lower(),
                    config,
                    exchange_type
                )

        except Exception as e:
            self.show_error_message(f"更新API配置失败: {str(e)}")

    def _handle_exchange_changed(self, new_exchange: str):
        """处理交易所切换"""
        if self.strategy_wrapper.has_running_strategies():
            self.show_error_message("请先停止所有运行中的策略再切换交易所")
            return

        # 更新交易所客户端
        self._handle_api_config_updated(self.api_manager.get_current_config())

    def _handle_pair_added(self, symbol: str, base: str):
        """处理添加交易对请求"""
        # 检查客户端状态
        if not self.check_client_status():
            return
            
        # 构建交易对
        pair = f"{symbol}/{base}"
        
        # 创建策略
        is_long = self.grid_controls.get_position_mode()
        uid = self.strategy_wrapper.create_strategy(
            pair,
            self.api_manager.current_exchange.lower(),
            is_long
        )

        if uid:
            grid_data = self.strategy_wrapper.get_strategy_data(uid)
            print(f"[GridStrategyTab] 获取策略数据: {grid_data}")  # 添加此行
            if grid_data:
                self.show_message("添加成功", f"交易对 {pair} 添加成功！")

    def _handle_stop_all_requested(self):
        """处理停止所有策略请求"""
        if not self.check_client_status():
            return
            
        # 确认操作
        reply = QMessageBox.question(
            self,
            "确认停止",
            "确认停止所有运行中的策略？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            success_count, total = self.strategy_wrapper.stop_all_strategies(self.exchange_client)
            self.show_message("操作完成", f"成功停止 {success_count}/{total} 个策略")

    def _handle_operation_toggled(self, operation_type: str, enabled: bool):
        """处理开平仓操作状态切换"""
        # 更新表格中所有策略的操作状态
        self.grid_table.set_all_operation_status(operation_type, enabled)
        
        # 保存策略数据
        self.strategy_wrapper.save_strategies(show_message=False)

    def _handle_position_mode_changed(self, is_long: bool):
        """处理持仓模式切换"""
        pass
        # if self.strategy_wrapper.has_running_strategies():
        #     self.show_error_message("请先停止所有运行中的策略再切换持仓模式")
        #     self.grid_controls.reset_position_mode()
        #     return

    def _handle_strategy_setting(self, uid: str):
        """处理策略设置请求"""
        grid_data = self.strategy_wrapper.get_strategy_data(uid)
        if not grid_data:
            return
            
        dialog = GridDialog(grid_data)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.strategy_wrapper.save_strategies(show_message=False)

    def _handle_strategy_start(self, uid: str):
        """处理启动策略请求"""
        if not self.check_client_status():
            return
            
        if self.strategy_wrapper.start_strategy(uid, self.exchange_client):
            self.show_message("启动成功", "策略已启动！")

    def _handle_strategy_stop(self, uid: str):
        """处理停止策略请求"""
        if not self.check_client_status():
            return
            
        if self.strategy_wrapper.stop_strategy(uid, self.exchange_client):
            self.show_message("停止成功", "策略已停止！")

    def _handle_strategy_delete(self, uid: str):
        """处理删除策略请求"""
        reply = QMessageBox.question(
            self,
            "删除确认",
            "确认删除此策略？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if self.strategy_wrapper.delete_strategy(uid):
                self.grid_table.remove_strategy(uid)
                self.show_message("删除成功", "策略已删除！")

    def _handle_strategy_close(self, uid: str):
        """处理策略平仓请求"""
        if not self.check_client_status():
            return
            
        grid_data = self.strategy_wrapper.get_strategy_data(uid)
        if not grid_data:
            return
            
        # 确认平仓操作
        confirm_msg = (
            f"确认平仓 {grid_data.pair} ?\n"
            f"方向: {'多仓' if grid_data.is_long() else '空仓'}\n"
            f"当前层数: {grid_data.row_dict.get('当前层数')}"
        )
        
        reply = QMessageBox.question(
            self,
            "平仓确认",
            confirm_msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if self.strategy_wrapper.close_position(uid, self.exchange_client):
                self.show_message("平仓成功", "策略持仓已平仓！")

    def _handle_strategy_refresh(self, uid: str):
        """处理策略数据刷新请求"""
        grid_data = self.strategy_wrapper.get_strategy_data(uid)
        if not grid_data:
            self.show_error_message("未找到策略数据")
            return
            
        # 构建刷新信息
        info_text = (
            f"策略数据已刷新:\n"
            f"交易对: {grid_data.pair}\n"
            f"方向: {grid_data.direction.value}\n"
            f"当前层数: {grid_data.row_dict.get('当前层数', '未设置')}\n"
            f"最新价格: {grid_data.row_dict.get('最后价格', 'N/A')}\n"
            f"持仓均价: {grid_data.row_dict.get('持仓均价', 'N/A')}\n"
            f"持仓价值: {grid_data.row_dict.get('持仓价值', 'N/A')}\n"
            f"持仓盈亏: {grid_data.row_dict.get('持仓盈亏', 'N/A')}"
        )
        
        self.show_message("数据已刷新", info_text)

    def _handle_strategy_added(self, uid: str):
        """处理策略添加事件"""
        grid_data = self.strategy_wrapper.get_strategy_data(uid)
        if grid_data:
            self.grid_table.add_strategy_row(grid_data)

    def _handle_strategy_deleted(self, uid: str):
        """处理策略删除事件"""
        self.grid_table.remove_strategy(uid)

    def _handle_strategy_updated(self, uid: str):
        """处理策略更新事件"""
        grid_data = self.strategy_wrapper.get_strategy_data(uid)
        if grid_data:
            self.grid_table.update_strategy_row(uid, grid_data)

    def _handle_strategy_error(self, uid: str, error_msg: str):
        """处理策略错误事件"""
        self.show_error_message(error_msg)
        if uid:
            self.grid_table.update_strategy_row(
                uid, 
                self.strategy_wrapper.get_strategy_data(uid)
            )

    def _handle_strategy_started(self, uid: str):
        """处理策略启动事件"""
        grid_data = self.strategy_wrapper.get_strategy_data(uid)
        if grid_data:
            grid_data.row_dict["运行状态"] = "运行中"
            self.grid_table.update_strategy_row(uid, grid_data)

    def _handle_strategy_stopped(self, uid: str):
        """处理策略停止事件"""
        grid_data = self.strategy_wrapper.get_strategy_data(uid)
        if grid_data:
            grid_data.row_dict["运行状态"] = "已停止"
            self.grid_table.update_strategy_row(uid, grid_data)

    def check_client_status(self) -> bool:
        """检查交易所客户端状态"""
        if not self.exchange_client or not self.exchange_client.is_connected:
            self.show_error_message("交易所客户端未连接，请检查网络连接！")
            return False
            
        ws_status = self.exchange_client.get_ws_status()
        if not ws_status.get("public") or not ws_status.get("private"):
            self.show_error_message(
                "WebSocket连接不完整，请确保公共和私有WebSocket均已连接！"
            )
            return False
            
        return True

    def show_message(self, title: str, message: str):
        """显示信息对话框"""
        QMessageBox.information(self, title, message)

    def show_error_message(self, message: str):
        """显示错误对话框"""
        QMessageBox.critical(self, "错误", message)

    def closeEvent(self, event):
        """处理窗口关闭事件"""
        try:
            # 停止所有策略
            if self.strategy_wrapper.has_running_strategies():
                print("[GridStrategyTab] 停止所有运行中的策略")
                self.strategy_wrapper.stop_all_strategies(self.exchange_client)
            
            # 等待保存和加载线程完成
            if hasattr(self.strategy_wrapper, '_save_thread') and \
               self.strategy_wrapper._save_thread and \
               self.strategy_wrapper._save_thread.is_alive():
                print("[GridStrategyTab] 等待保存线程完成...")
                self.strategy_wrapper._save_thread.join(timeout=2)
                
            if hasattr(self.strategy_wrapper, '_load_thread') and \
               self.strategy_wrapper._load_thread and \
               self.strategy_wrapper._load_thread.is_alive():
                print("[GridStrategyTab] 等待加载线程完成...")
                self.strategy_wrapper._load_thread.join(timeout=2)
            
            # 异步保存数据
            def save_data():
                self.strategy_wrapper.save_strategies(show_message=False)
                
            threading.Thread(
                target=save_data,
                name=f"GridStrategy-FinalSave-{self.tab_id}",
                daemon=True
            ).start()

            # 清理客户端资源
            if self.exchange_client:
                print("[GridStrategyTab] 清理客户端资源")
                self.exchange_client = None
                self.api_manager.update_ws_status(False, False)
                
                def destroy_client():
                    self.client_factory.destroy_client(self.tab_id)
                
                threading.Thread(
                    target=destroy_client,
                    name=f"GridStrategy-Cleanup-{self.tab_id}",
                    daemon=True
                ).start()

            # 接受关闭事件
            event.accept()
            
        except Exception as e:
            print(f"[GridStrategyTab] 关闭窗口时发生错误: {e}")
            print(f"[GridStrategyTab] 错误详情: {traceback.format_exc()}")
            # 确保窗口能关闭
            event.accept()