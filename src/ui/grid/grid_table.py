# src/ui/components/grid_table.py

import traceback
from typing import Dict, Optional, List, Any
from decimal import Decimal
from datetime import datetime
from qtpy.QtWidgets import (
    QTableWidget, QTableWidgetItem, QWidget, QHBoxLayout,
    QPushButton, QMenu, QHeaderView, QMessageBox
)
from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QColor
from src.strategy.grid.grid_core import GridData, GridDirection
from src.ui.grid.strategy_manager_wrapper import StrategyManagerWrapper

class GridTable(QTableWidget):
    """网格策略表格组件"""
    
    # 信号定义
    strategy_setting_requested = Signal(str)    # uid
    strategy_start_requested = Signal(str)      # uid  
    strategy_stop_requested = Signal(str)       # uid
    strategy_delete_requested = Signal(str)     # uid
    strategy_close_requested = Signal(str)      # uid
    strategy_refresh_requested = Signal(str)    # uid
    dialog_requested = Signal(str, str, str)
    
    # 表格列定义
    COLUMN_DEFINITIONS = [
        {"name": "交易对", "type": "text", "editable": False, "width": 100},
        {"name": "方向", "type": "text", "editable": False, "width": 80},
        {"name": "操作", "type": "switches", "editable": True, "width": 100},
        {"name": "运行状态", "type": "text", "editable": False, "width": 100},
        {"name": "当前层数", "type": "text", "editable": False, "width": 100},
        # {"name": "时间戳", "type": "text", "editable": False, "width": 120},
        {"name": "最后时间", "type": "text", "editable": False, "width": 100},
        {"name": "最后价格", "type": "text", "editable": False, "width": 100},
        {"name": "开仓触发价", "type": "text", "editable": False, "width": 110},
        {"name": "止盈触发价", "type": "text", "editable": False, "width": 110},
        # {"name": "尾单价格", "type": "text", "editable": False, "width": 100},
        {"name": "持仓均价", "type": "text", "editable": False, "width": 100},
        {"name": "持仓价值", "type": "text", "editable": False, "width": 100},
        {"name": "持仓盈亏", "type": "text", "editable": False, "width": 100},
        {"name": "实现盈亏", "type": "text", "editable": False, "width": 100},
        {"name": "总体止盈", "type": "text", "editable": False, "width": 100},
        {"name": "总体止损", "type": "text", "editable": False, "width": 100},
        {"name": "交易所", "type": "text", "editable": False, "width": 100},
        {"name": "标识符", "type": "text", "editable": False, "width": 100}
    ]

    def __init__(self, strategy_wrapper: StrategyManagerWrapper):
        super().__init__(0, len(self.COLUMN_DEFINITIONS))
        self.strategy_wrapper = strategy_wrapper  # 保存对StrategyManagerWrapper的引用
        self.setup_table()
        
    def setup_table(self):
        """设置表格基本属性"""
        # 设置列标题
        self.setHorizontalHeaderLabels([col["name"] for col in self.COLUMN_DEFINITIONS])
        
        # 设置列宽
        for i, col in enumerate(self.COLUMN_DEFINITIONS):
            self.setColumnWidth(i, col["width"])
            
        # 设置表格属性
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        
        # 设置样式
        self.setStyleSheet("""
            QTableWidget {
                gridline-color: #E5E5E5;
                background-color: white;
                border: 1px solid #D3D3D3;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QHeaderView::section {
                background-color: #F5F5F5;
                padding: 5px;
                border: none;
                border-right: 1px solid #D3D3D3;
                border-bottom: 1px solid #D3D3D3;
            }
        """)

    def add_strategy_row(self, grid_data: GridData):
        """添加策略行"""
        try:
            row_position = self.rowCount()
            print(f"[GridTable] 添加新行，当前行数: {row_position}")  # 添加此行
            self.insertRow(row_position)
            
            # 填充表格数据
            for i, col in enumerate(self.COLUMN_DEFINITIONS):
                if col["name"] == "操作":
                    # 获取操作状态
                    operation_status = grid_data.row_dict.get("操作", {"开仓": True, "平仓": True})
                    # print(f"[GridTable] 创建操作按钮，状态: {operation_status}")  # 添加此行
                    self._create_operation_buttons(row_position, grid_data.uid, operation_status)
                else:
                    # 填充其他列的数据
                    value = grid_data.row_dict.get(col["name"], "")
                    # print(f"[GridTable] 设置单元格 ({row_position}, {i}): {value}")  # 添加此行
                    item = QTableWidgetItem(str(value))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.setItem(row_position, i, item)

        except Exception as e:
            print(f"[GridTable] 添加策略行失败: {e}")
            print(f"[GridTable] 错误详情: {traceback.format_exc()}")

    def _create_operation_buttons(self, row: int, uid: str, status: Dict[str, bool]):
        """创建操作按钮组"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # 创建开平仓按钮
        open_button = QPushButton("开")
        close_button = QPushButton("平")

        # 设置按钮状态
        open_button.setCheckable(True)
        close_button.setCheckable(True)
        open_button.setChecked(status.get("开仓", True))
        close_button.setChecked(status.get("平仓", True))

        # 设置按钮样式
        button_style = """
            QPushButton {
                font-size: 14px;
                padding: 2px;
                background-color: #e0f7fa;
                border: 1px solid #00bcd4;
                border-radius: 5px;
                color: #333;
                min-width: 35px;
                max-width: 35px;
                height: 25px;
            }
            QPushButton:checked {
                background-color: #00bcd4;
                color: white;
                border: 1px solid #008c9e;
            }
            QPushButton:hover {
                background-color: #b2ebf2;
            }
            QPushButton:checked:hover {
                background-color: #00acc1;
            }
        """
        open_button.setStyleSheet(button_style)
        close_button.setStyleSheet(button_style)

        # 连接信号
        def create_toggle_handler(operation_type: str):
            def handler(checked: bool):
                self._handle_operation_toggled(uid, operation_type, checked)
            return handler

        open_button.toggled.connect(create_toggle_handler("开仓"))
        close_button.toggled.connect(create_toggle_handler("平仓"))

        # 将按钮添加到布局
        layout.addWidget(open_button)
        layout.addWidget(close_button)

        # 设置到表格
        self.setCellWidget(row, self.get_column_index("操作"), container)

    def _handle_operation_toggled(self, uid: str, operation_type: str, checked: bool):
        """处理操作状态切换"""
        grid_data = self.strategy_wrapper.get_strategy_data(uid)  # 通过StrategyManagerWrapper获取策略数据
        if grid_data:
            operation = grid_data.row_dict.get("操作", {})
            operation[operation_type] = checked
            grid_data.row_dict["操作"] = operation
            grid_data.data_updated.emit(uid)

    def update_strategy_row(self, uid: str, grid_data: GridData):
        """更新策略行数据"""
        try:
            print(f"\n[GridTable] === 开始更新策略行 === {uid}")
            print(f"[GridTable] 更新数据: {grid_data.row_dict}")
            
            # 查找对应行
            row = -1
            for i in range(self.rowCount()):
                uid_item = self.item(i, self.get_column_index("标识符"))
                if uid_item and uid_item.text() == uid:
                    row = i
                    break
                    
            if row == -1:
                print(f"[GridTable] 未找到策略行: {uid}")
                return
                
            print(f"[GridTable] 找到策略行: {row}")
            
            # 更新各列数据
            for col in self.COLUMN_DEFINITIONS:
                col_name = col["name"]
                if col_name == "操作":
                    continue
                    
                value = grid_data.row_dict.get(col_name)
                if value is not None:
                    print(f"[GridTable] 更新列 {col_name}: {value}")
                    item = QTableWidgetItem(str(value))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    
                    # 设置运行状态列的颜色
                    if col_name == "运行状态":
                        self._set_status_color(item, str(value))
                    # 设置浮点数精度
                    elif col_name in ["最后价格", "开仓触发价", "止盈触发价", "尾单价格", "持仓均价"]:
                        try:
                            value = float(value)
                            item.setText(f"{value:.4f}")
                        except (ValueError, TypeError):
                            pass
                    # 处理金额显示
                    elif col_name in ["持仓价值", "持仓盈亏", "实现盈亏"]:
                        try:
                            value = float(value)
                            item.setText(f"{value:.2f}")
                        except (ValueError, TypeError):
                            pass
                        
                    self.setItem(row, self.get_column_index(col_name), item)

            print(f"[GridTable] === 策略行更新完成 ===")

        except Exception as e:
            print(f"[GridTable] 更新策略行错误: {e}")
            print(f"[GridTable] 错误详情: {traceback.format_exc()}")

    def _set_status_color(self, item: QTableWidgetItem, status: str):
        """设置状态文本颜色"""
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
        item.setForeground(color)

    def show_context_menu(self, position):
        """显示右键菜单"""
        index = self.indexAt(position)
        if not index.isValid():
            return

        row = index.row()
        uid_item = self.item(row, self.get_column_index("标识符"))
        if not uid_item:
            return
        uid = uid_item.text()
        
        # 获取策略状态
        status = self.get_strategy_status(uid)
        if not status:
            return
            
        menu = QMenu(self)
        
        # 基础操作
        menu.addAction("设置网格", lambda: self.strategy_setting_requested.emit(uid))
        
        # 根据策略状态添加启动/停止选项
        if status == "运行中":
            menu.addAction("停止策略", lambda: self.strategy_stop_requested.emit(uid))
        else:
            menu.addAction("启动策略", lambda: self.strategy_start_requested.emit(uid))

        menu.addSeparator()
        
        # 只有在策略已停止时才允许平仓
        if status != "运行中":
            menu.addAction("平仓", lambda: self._handle_close_strategy(uid))
        
        # 添加刷新按钮
        menu.addSeparator()
        menu.addAction("刷新数据", lambda: self.strategy_refresh_requested.emit(uid))

        # 删除选项需要确认
        menu.addSeparator()
        menu.addAction("删除", lambda: self._handle_delete_strategy(uid, status))
        
        menu.exec(self.mapToGlobal(position))

    def _handle_delete_strategy(self, uid: str, status: str):
        """处理删除策略请求"""
        try:
            # 检查运行状态
            if status == "运行中":
                self.dialog_requested.emit("warning", "警告", "请先停止策略再删除！")
                return
                
            # 获取策略数据
            grid_data = self.strategy_wrapper.get_strategy_data(uid)
            if not grid_data:
                self.dialog_requested.emit("error", "错误", "策略数据不存在！")
                return
                
            # 检查是否有持仓
            position_value = grid_data.row_dict.get("持仓价值", "0")
            if position_value and float(position_value.replace(",", "")) > 0:
                self.dialog_requested.emit("warning", "警告", "策略仍有持仓，请先平仓后再删除！")
                return
                
            # 发送删除请求
            self.strategy_delete_requested.emit(uid)
        except Exception as e:
            self.dialog_requested.emit("error", "错误", f"删除策略失败: {str(e)}")

    def _handle_close_strategy(self, uid: str):
        """处理平仓请求"""
        status = self.get_strategy_status(uid)
        if status == "运行中":
            self.dialog_requested.emit("warning", "警告", "请先停止策略再进行平仓！")
            return
            
        self.strategy_close_requested.emit(uid)

    def get_strategy_uids(self) -> List[str]:
        """获取所有策略ID"""
        uids = []
        for row in range(self.rowCount()):
            uid_item = self.item(row, self.get_column_index("标识符"))
            if uid_item:
                uids.append(uid_item.text())
        return uids

    def get_column_index(self, column_name: str) -> int:
        """获取列索引"""
        return next(
            (i for i, col in enumerate(self.COLUMN_DEFINITIONS) 
            if col["name"] == column_name),
            -1
        )

    def remove_strategy(self, uid: str):
        """删除策略行"""
        for row in range(self.rowCount()):
            if self.item(row, self.get_column_index("标识符")).text() == uid:
                self.removeRow(row)
                break

    def clear_all(self):
        """清空表格"""
        self.setRowCount(0)

    def get_strategy_status(self, uid: str) -> Optional[str]:
        """获取策略状态"""
        for row in range(self.rowCount()):
            if self.item(row, self.get_column_index("标识符")).text() == uid:
                status_item = self.item(row, self.get_column_index("运行状态"))
                return status_item.text() if status_item else None
        return None

    def update_operation_status(self, uid: str, operation_type: str, enabled: bool):
        """更新操作状态"""
        for row in range(self.rowCount()):
            if self.item(row, self.get_column_index("标识符")).text() == uid:
                operation_widget = self.cellWidget(row, self.get_column_index("操作"))
                if operation_widget:
                    layout = operation_widget.layout()
                    button_index = 0 if operation_type == "开仓" else 1
                    button = layout.itemAt(button_index).widget()
                    if button:
                        button.setChecked(enabled)
                break

    def set_all_operation_status(self, operation_type: str, enabled: bool):
        """设置所有策略的操作状态"""
        for row in range(self.rowCount()):
            operation_widget = self.cellWidget(row, self.get_column_index("操作"))
            if operation_widget:
                layout = operation_widget.layout()
                button_index = 0 if operation_type == "开仓" else 1
                button = layout.itemAt(button_index).widget()
                if button:
                    button.setChecked(enabled)

    def disable_all_operations(self, uid: str):
        """禁用指定策略的所有操作"""
        self.update_operation_status(uid, "开仓", False)
        self.update_operation_status(uid, "平仓", False)

    def enable_all_operations(self, uid: str):
        """启用指定策略的所有操作"""
        self.update_operation_status(uid, "开仓", True)
        self.update_operation_status(uid, "平仓", True)