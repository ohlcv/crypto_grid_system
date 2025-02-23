# src/ui/tabs/grid_strategy_tab.py

import os
import threading
import traceback
import uuid
from typing import Optional
from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QApplication, QMessageBox, QDialog
)
from qtpy.QtCore import Qt, QTimer, Signal

from src.exchange.base_client import InstType, BaseClient
from src.exchange.client_factory import ExchangeClientFactory
from src.ui.grid.api_config_manager import APIConfigManager
from src.ui.grid.grid_controls import GridControls
from src.ui.grid.grid_table import GridTable
from src.ui.grid.strategy_manager_wrapper import StrategyManagerWrapper
from src.ui.grid.grid_settings_aidlog import GridDialog


def show_error_dialog(func):
    """装饰器: 捕获并显示函数执行期间的错误"""
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception as e:
            error_msg = f"操作出错: {str(e)}\n\n详细信息:\n{traceback.format_exc()}"
            print(f"[GridStrategyTab] {error_msg}")
            self.show_dialog("error", "错误", error_msg)
    return wrapper

class GridStrategyTab(QWidget):
    """网格策略Tab页 - 重构后的主类实现"""
    update_ui_signal = Signal(str)  # uid 参数

    def __init__(self, inst_type: InstType, client_factory: ExchangeClientFactory):
        super().__init__()
        self.inst_type = inst_type
        self.client_factory = client_factory
        self.tab_id = str(uuid.uuid4())
        self.exchange_client: Optional[BaseClient] = None
        
        self.api_manager = APIConfigManager(self.tab_id, self.inst_type, client_factory)
        self.grid_controls = GridControls(self.inst_type)
        self.strategy_wrapper = StrategyManagerWrapper(self.inst_type, client_factory)
        self.grid_table = GridTable(self.strategy_wrapper)
        
        self.setup_ui()
        self.api_manager.load_config()
        self._connect_signals()
        QTimer.singleShot(500, self._auto_connect_exchange)
        self.strategy_wrapper.load_strategies()
        self.update_ui_signal.connect(self._update_ui_in_main_thread)

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

    @show_error_dialog
    def _handle_strategy_added(self, uid: str):
        """处理策略添加事件"""
        print(f"[GridStrategyTab] 处理策略添加事件: {uid}")
        grid_data = self.strategy_wrapper.get_strategy_data(uid)
        if grid_data:
            print(f"[GridStrategyTab] 获取到策略数据: UID={grid_data.uid}, Pair={grid_data.symbol_config.pair}")
            grid_data.data_updated.connect(self._handle_strategy_updated)
            self.grid_table.add_strategy_row(grid_data)
            print(f"[GridStrategyTab] 已调用 add_strategy_row 添加策略: {uid}")
        else:
            print(f"[GridStrategyTab] 未找到策略数据: {uid}")
            self.show_error_message(f"未找到策略数据: UID={uid}")

    @show_error_dialog
    def _handle_strategy_started(self, uid: str):
        grid_data = self.strategy_wrapper.get_strategy_data(uid)
        if grid_data:
            grid_data.status = "运行中"
            self.grid_table.update_strategy_row(uid, grid_data)

    @show_error_dialog
    def _handle_strategy_stopped(self, uid: str):
        grid_data = self.strategy_wrapper.get_strategy_data(uid)
        if grid_data:
            grid_data.status = "已停止"
            self.grid_table.update_strategy_row(uid, grid_data)

    def _handle_strategy_refresh(self, uid: str):
        grid_data = self.strategy_wrapper.get_strategy_data(uid)
        if not grid_data:
            self.show_error_message("未找到策略数据")
            return
            
        position_metrics = grid_data.calculate_position_metrics()
        grid_status = grid_data.get_grid_status()
        
        info_text = (
            f"策略数据已刷新:\n"
            f"交易对: {grid_data.symbol_config.pair}\n"
            f"方向: {grid_data.direction.value}\n"
            f"状态: {grid_data.status}\n"
            f"当前层数: {grid_status['filled_levels']}/{grid_status['total_levels']}\n"
            f"最新价格: {grid_data.ticker_data.lastPr if grid_data.ticker_data else 'N/A'}\n"
            f"持仓均价: {position_metrics['avg_price']}\n"
            f"持仓价值: {position_metrics['total_value']}\n"
            f"持仓盈亏: {position_metrics['unrealized_pnl']}"
        )
        
        self.show_message("数据已刷新", info_text)

    def _handle_strategy_close(self, uid: str):
        if not self.check_client_status():
            return
            
        grid_data = self.strategy_wrapper.get_strategy_data(uid)
        if not grid_data:
            return
            
        grid_status = grid_data.get_grid_status()
        confirm_msg = (
            f"确认平仓 {grid_data.symbol_config.pair} ?\n"
            f"方向: {'多仓' if grid_data.is_long() else '空仓'}\n"
            f"当前层数: {grid_status['filled_levels']}/{grid_status['total_levels']}"
        )
        
        reply = QMessageBox.question(
            self,
            "平仓确认",
            confirm_msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            success, message = self.strategy_wrapper.close_position(uid, self.exchange_client)
            if success:
                if message == "无可平仓数量":
                    self.show_message("无需平仓", "当前币种无持仓，无需平仓！")
                elif message == "平仓成功":
                    self.show_message("平仓成功", "该币持仓已全平！")
                else:
                    self.show_message("操作完成", message)
            else:
                self._handle_strategy_error(uid, message)


    @show_error_dialog
    def _connect_signals(self):
        """连接所有组件信号"""
        try:
            print(f"[GridStrategyTab] === 开始连接信号 ===")
            
            # API配置管理器信号
            self.api_manager.config_error.connect(self.show_error_message)
            self.api_manager.config_updated.connect(self._handle_api_config_updated)
            self.api_manager.exchange_changed.connect(self._handle_exchange_changed)

            # 网格控制信号
            self.grid_controls.pair_added.connect(self._handle_pair_added)
            self.grid_controls.stop_all_requested.connect(self._handle_stop_all_requested)
            self.grid_controls.operation_toggled.connect(self._handle_operation_toggled)
            self.grid_controls.position_mode_changed.connect(self._handle_position_mode_changed)
            self.grid_controls.dialog_requested.connect(lambda type, title, msg: self.show_dialog(type, title, msg))
            
            # 表格信号
            self.grid_table.strategy_setting_requested.connect(self._handle_strategy_setting)
            self.grid_table.strategy_start_requested.connect(self._handle_strategy_start)
            self.grid_table.strategy_stop_requested.connect(self._handle_strategy_stop)
            self.grid_table.strategy_delete_requested.connect(self._handle_strategy_delete)
            self.grid_table.strategy_close_requested.connect(self._handle_strategy_close)
            self.grid_table.strategy_refresh_requested.connect(self._handle_strategy_refresh)
            self.grid_table.dialog_requested.connect(lambda type, title, msg: self.show_dialog(type, title, msg))
            
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
            
            # 连接所有已加载策略的数据更新信号
            print(f"[GridStrategyTab] 开始连接已加载策略的数据更新信号...")
            strategy_uids = self.strategy_wrapper.get_all_strategy_uids()
            for uid in strategy_uids:
                grid_data = self.strategy_wrapper.get_strategy_data(uid)
                if grid_data:
                    print(f"[GridStrategyTab] 连接策略 {uid} 的数据更新信号")
                    grid_data.data_updated.connect(
                        self._handle_strategy_updated
                    )
                    
            print(f"[GridStrategyTab] === 信号连接完成 ===")
            
        except Exception as e:
            print(f"[GridStrategyTab] 连接信号时发生错误: {e}")
            print(f"[GridStrategyTab] 错误详情: {traceback.format_exc()}")

    @show_error_dialog
    def _handle_client_status_changed(self, tab_id: str, status: str):
        """处理客户端状态变化"""
        if tab_id == self.tab_id:
            self.api_manager.update_connection_status(status)

    @show_error_dialog
    def _handle_client_created(self, source_tab_id: str, exchange_type: str, client: BaseClient):
        """处理客户端创建"""
        print(f"\n[GridStrategyTab] 收到客户端创建信号 | 来源tab: {source_tab_id} 类型: {exchange_type}")
        
        # 严格过滤条件
        if (source_tab_id != self.tab_id) or (exchange_type != self.inst_type.value):
            # print(f"└─ 忽略非本标签页或类型不匹配的客户端")
            return

        # print(f"├─ 客户端类型: {client.inst_type.name}")
        # print(f"└─ 本标签类型: {self.inst_type.name}")

        try:
            # 检查客户端类型是否匹配
            if client.inst_type != self.inst_type:
                print(f"忽略类型不匹配的客户端: {client.inst_type} vs {self.inst_type}")
                return

            # 检查是否是本标签页的客户端
            tab_client = self.client_factory.get_client(self.tab_id, client.inst_type)
            if client is not tab_client:
                print(f"[GridStrategyTab] 不是当前标签页的客户端")
                return
                
            self.exchange_client = client
            self.grid_controls.set_client(client)  # 设置grid_controls的客户端
            print(f"[GridStrategyTab] 客户端设置完成: {client.inst_type.name}")
            self._connect_client_signals(client)

            # 同步初始状态
            ws_status = client.get_ws_status()
            print(f"[GridStrategyTab] 初始 WebSocket 状态: {ws_status}")
            self.api_manager.update_ws_status(True, ws_status.get('public', False))
            self.api_manager.update_ws_status(False, ws_status.get('private', False))
            self.api_manager.update_connection_status("就绪" if client.is_connected else "未连接")

        except Exception as e:
            print(f"[GridStrategyTab] 客户端创建处理错误: {e}")
            print(f"[GridStrategyTab] 错误详情: {traceback.format_exc()}")
            self.show_error_message(f"客户端创建处理失败: {str(e)}")

    def _connect_client_signals(self, client: BaseClient):
        """连接客户端信号"""
        try:
            print(f"\n[GridStrategyTab] === 连接客户端信号 ===")
            print(f"当前标签页: {self.tab_id}")
            print(f"客户端类型: {client.inst_type.name}")

            # 断开现有连接
            try:
                client.tick_received.disconnect()
                client.error_occurred.disconnect()
            except TypeError:
                pass

            # 连接数据处理相关的信号
            client.tick_received.connect(self.strategy_wrapper.process_market_data)
            client.error_occurred.connect(self.show_error_message)

            # 让 APIConfigManager 连接状态相关的信号
            self.api_manager._connect_client_signals(client)

            print(f"[GridStrategyTab] 客户端信号连接完成: {client.inst_type.name}")

        except Exception as e:
            print(f"[GridStrategyTab] 连接客户端信号失败: {e}")
            print(f"[GridStrategyTab] 错误详情: {traceback.format_exc()}")
            self.show_error_message(f"连接客户端信号失败: {str(e)}")

    @show_error_dialog
    def _handle_ws_status_changed(self, is_public: bool, connected: bool):
        """处理WebSocket状态变化"""
        print(f"[GridStrategyTab] WebSocket状态变化 - {'公有' if is_public else '私有'}: {'已连接' if connected else '未连接'}")
        self.api_manager.update_ws_status(is_public, connected)

    @show_error_dialog
    def _auto_connect_exchange(self):
        try:
            if self.exchange_client:  # 如果已经有客户端实例，直接返回
                print(f"[GridStrategyTab] 客户端已存在，无需重复创建: {self.inst_type.value}")
                return

            # 检查工厂中是否已有该标签页的客户端
            existing_client = self.client_factory.get_client(self.tab_id, self.inst_type)
            if existing_client:
                print(f"[GridStrategyTab] 工厂中已存在客户端: {self.inst_type.value}")
                self.exchange_client = existing_client
                self._connect_client_signals(existing_client)
                return

            current_exchange = self.api_manager.exchange_combo.currentText().lower()
            config = self.api_manager.get_current_config()

            if all([config.get('api_key'), config.get('api_secret'), config.get('passphrase')]):
                self.exchange_client = self.client_factory.create_client(
                    self.tab_id,
                    current_exchange,
                    config,
                    self.inst_type
                )
                print(f"[GridStrategyTab] 新客户端创建成功: {self.inst_type.value}")
        except Exception as e:
            print(f"[GridStrategyTab] 自动连接交易所失败: {e}")
            print(f"[GridStrategyTab] 错误详情: {traceback.format_exc()}")

    @show_error_dialog
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
                exchange_type =self.inst_type
                self.exchange_client = self.client_factory.create_client(
                    self.tab_id,
                    self.api_manager.current_exchange.lower(),
                    config,
                    exchange_type
                )

        except Exception as e:
            self.show_error_message(f"更新API配置失败: {str(e)}")

    @show_error_dialog
    def _handle_exchange_changed(self, new_exchange: str):
        """处理交易所切换"""
        if self.strategy_wrapper.has_running_strategies():
            self.show_error_message("请先停止所有运行中的策略再切换交易所")
            return

        # 更新交易所客户端
        self._handle_api_config_updated(self.api_manager.get_current_config())

    @show_error_dialog
    def _handle_pair_added(self, base, quote, pair_config):
        """处理添加交易对请求"""
        if not self.check_client_status():
            return
            
        is_long = self.grid_controls.get_position_mode()
        uid = self.strategy_wrapper.create_strategy(
            pair_config,
            self.api_manager.current_exchange.lower(),
            is_long
        )

        if uid:
            grid_data = self.strategy_wrapper.get_strategy_data(uid)
            if grid_data:
                self.show_message("添加成功", f"交易对 {pair_config.pair} 添加成功！")

    @show_error_dialog
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

    @show_error_dialog
    def _handle_operation_toggled(self, operation_type: str, enabled: bool):
        """处理开平仓操作状态切换"""
        # 更新表格中所有策略的操作状态
        self.grid_table.set_all_operation_status(operation_type, enabled)
        
        # 保存策略数据
        self.strategy_wrapper.save_strategies(show_message=False)

    @show_error_dialog
    def _handle_position_mode_changed(self, is_long: bool):
        """处理持仓模式切换"""
        pass
        # if self.strategy_wrapper.has_running_strategies():
        #     self.show_error_message("请先停止所有运行中的策略再切换持仓模式")
        #     self.grid_controls.reset_position_mode()
        #     return

    @show_error_dialog
    def _handle_strategy_setting(self, uid: str):
        """处理策略设置请求"""
        grid_data = self.strategy_wrapper.get_strategy_data(uid)
        if not grid_data:
            return
            
        dialog = GridDialog(grid_data)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.strategy_wrapper.save_strategies(show_message=False)

    @show_error_dialog
    def _handle_strategy_start(self, uid: str):
        """处理启动策略请求"""
        if not self.check_client_status():
            return
            
        if self.strategy_wrapper.start_strategy(uid, self.exchange_client):
            self.show_message("启动成功", "策略已启动！")

    @show_error_dialog
    def _handle_strategy_stop(self, uid: str):
        """处理停止策略请求"""
        if not self.check_client_status():
            return
            
        if self.strategy_wrapper.stop_strategy(uid, self.exchange_client):
            self.show_message("停止成功", "策略已停止！")

    @show_error_dialog
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

    def _handle_strategy_error(self, uid: str, error_msg: str):
        """处理策略错误事件"""
        print(f"[GridStrategyTab] 处理策略错误 - UID: {uid}, 错误: {error_msg}")
        self.show_error_message(error_msg)
        if uid:
            grid_data = self.strategy_wrapper.get_strategy_data(uid)
            if grid_data:
                grid_data.status = "错误停止"
                self.grid_table.update_strategy_row(uid, grid_data)

    @show_error_dialog
    def _handle_strategy_deleted(self, uid: str):
        """处理策略删除事件"""
        self.grid_table.remove_strategy(uid)

    @show_error_dialog
    def _handle_strategy_updated(self, uid: str):
        """处理策略更新事件 - 可能在非主线程中调用"""
        # print(f"\n[GridStrategyTab] === 接收到策略更新事件 === {uid}")
        self.update_ui_signal.emit(uid)

    @show_error_dialog
    def _update_ui_in_main_thread(self, uid: str):
        """在主线程中更新UI"""
        try:
            # print(f"\n[GridStrategyTab] === 主线程处理策略更新 === {uid}")
            grid_data = self.strategy_wrapper.get_strategy_data(uid)
            if grid_data:
                # print(f"[GridStrategyTab] 获取到策略数据: {grid_data.uid}")
                # print(f"[GridStrategyTab] 开始更新表格...")
                self.grid_table.update_strategy_row(uid, grid_data)
                # print(f"[GridStrategyTab] 表格更新完成")
            else:
                print(f"[GridStrategyTab] 未找到策略数据: {uid}")
        except Exception as e:
            print(f"[GridStrategyTab] 更新UI失败: {e}")
            print(f"[GridStrategyTab] 错误详情: {traceback.format_exc()}")

    @show_error_dialog
    def check_client_status(self) -> bool:
        """检查交易所客户端状态"""
        if not self.exchange_client:
            self.show_error_message("交易所客户端未连接!")
            return False
            
        # 验证客户端类型
        expected_type = self.inst_type  # 直接使用枚举值
        if self.exchange_client.inst_type != expected_type:
            self.show_error_message(f"交易所客户端类型不匹配: 预期 {expected_type.value}, 实际 {self.exchange_client.inst_type.value}")
            return False
            
        # 验证是否是本标签页的客户端  
        tab_client = self.client_factory.get_client(self.tab_id, expected_type)
        if self.exchange_client is not tab_client:
            self.show_error_message("客户端实例不属于当前标签页!")
            return False

        if not self.exchange_client.is_connected:
            self.show_error_message("交易所客户端未连接，请检查网络连接！")
            return False
                
        ws_status = self.exchange_client.get_ws_status()
        if not ws_status.get("public") or not ws_status.get("private"):
            self.show_error_message(
                "WebSocket连接不完整，请确保公共和私有WebSocket均已连接！"
            )
            return False
                
        return True

    def show_error_message(self, message: str):
        """显示错误消息对话框"""
        return self.show_dialog("error", "错误", message)

    def show_message(self, title: str, message: str):
        """显示普通消息对话框"""
        return self.show_dialog("info", title, message)

    def show_dialog(self, dialog_type: str, title: str, message: str, 
                   buttons=QMessageBox.StandardButton.Ok,
                   default_button=QMessageBox.StandardButton.Ok) -> QMessageBox.StandardButton:
        """统一的对话框显示管理
        
        Args:
            dialog_type: 对话框类型 ("info", "warning", "error", "question")
            title: 标题
            message: 消息内容
            buttons: 按钮选项
            default_button: 默认按钮
            
        Returns:
            用户点击的按钮
        """
        print(f"[GridStrategyTab] 显示对话框: {dialog_type}, 标题: {title}, 消息: {message}")
        dialog_map = {
            "info": QMessageBox.information,
            "warning": QMessageBox.warning,
            "error": QMessageBox.critical,
            "question": QMessageBox.question
        }
        
        dialog_func = dialog_map.get(dialog_type, QMessageBox.information)
        return dialog_func(self, title, message, buttons, default_button)

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