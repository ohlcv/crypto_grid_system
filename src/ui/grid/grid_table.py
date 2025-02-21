# src/ui/components/grid_table.py

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum, auto
import traceback
from typing import Dict, Optional, List, Any, Set, Union
from decimal import Decimal
from datetime import datetime
from qtpy.QtWidgets import (
    QTableWidget, QTableWidgetItem, QWidget, QHBoxLayout,
    QPushButton, QMenu, QHeaderView, QMessageBox
)
from qtpy.QtCore import Qt, Signal, QObject
from qtpy.QtGui import QColor
from src.strategy.grid.grid_core import GridData
from src.ui.grid.strategy_manager_wrapper import StrategyManagerWrapper

class GridColumn(Enum):
    """网格表格列定义"""
    PAIR = auto()           # 交易对
    DIRECTION = auto()      # 方向
    OPERATIONS = auto()     # 操作
    STATUS = auto()         # 运行状态
    GRID_LEVEL = auto()     # 当前层数
    LAST_TIME = auto()      # 最后时间
    LAST_PRICE = auto()     # 最后价格
    AVG_PRICE = auto()      # 持仓均价
    OPEN_TRIGGER = auto()   # 开仓触发价
    TP_TRIGGER = auto()     # 止盈触发价
    ATP_TRIGGER = auto()    # 均价止盈触发价
    ASL_TRIGGER = auto()    # 均价止损触发价
    AVG_TP = auto()        # 均价止盈
    AVG_SL = auto()        # 均价止损
    TOTAL_TP = auto()      # 总体止盈
    TOTAL_SL = auto()      # 总体止损
    POS_VALUE = auto()     # 持仓价值
    POS_PNL = auto()       # 持仓盈亏
    REALIZED_PNL = auto()  # 实现盈亏
    EXCHANGE = auto()      # 交易所
    UID = auto()           # 标识符

@dataclass
class GridColumnConfig:
    """列配置"""
    name: str              # 显示名称
    width: int            # 列宽
    editable: bool = False  # 是否可编辑
    visible: bool = True   # 是否可见

class GridColumnManager:
    """列管理器"""
    COLUMN_CONFIGS = {
        GridColumn.PAIR: GridColumnConfig("交易对", 100),
        GridColumn.DIRECTION: GridColumnConfig("方向", 80),
        GridColumn.OPERATIONS: GridColumnConfig("操作", 100, editable=True),
        GridColumn.STATUS: GridColumnConfig("运行状态", 100),
        GridColumn.GRID_LEVEL: GridColumnConfig("当前层数", 100),
        GridColumn.LAST_TIME: GridColumnConfig("最后时间", 100),
        GridColumn.LAST_PRICE: GridColumnConfig("最后价格", 100),
        GridColumn.AVG_PRICE: GridColumnConfig("持仓均价", 100),
        GridColumn.OPEN_TRIGGER: GridColumnConfig("开仓触发价", 110),
        GridColumn.TP_TRIGGER: GridColumnConfig("止盈触发价", 110),
        GridColumn.ATP_TRIGGER: GridColumnConfig("均价止盈触发价", 100),
        GridColumn.ASL_TRIGGER: GridColumnConfig("均价止损触发价", 100),
        GridColumn.AVG_TP: GridColumnConfig("均价止盈", 100),
        GridColumn.AVG_SL: GridColumnConfig("均价止损", 100),
        GridColumn.TOTAL_TP: GridColumnConfig("总体止盈", 100),
        GridColumn.TOTAL_SL: GridColumnConfig("总体止损", 100),
        GridColumn.POS_VALUE: GridColumnConfig("持仓价值", 100),
        GridColumn.POS_PNL: GridColumnConfig("持仓盈亏", 100),
        GridColumn.REALIZED_PNL: GridColumnConfig("实现盈亏", 100),
        GridColumn.EXCHANGE: GridColumnConfig("交易所", 100),
        GridColumn.UID: GridColumnConfig("标识符", 100)
    }

    @classmethod
    def get_visible_columns(cls) -> list:
        """获取可见列"""
        return [col for col, cfg in cls.COLUMN_CONFIGS.items() if cfg.visible]
    
    @classmethod
    def get_column_index(cls, column: GridColumn) -> int:
        """获取列索引"""
        visible_columns = cls.get_visible_columns()
        try:
            return visible_columns.index(column)
        except ValueError:
            return -1

    @classmethod
    def get_column_name(cls, column: GridColumn) -> str:
        """获取列显示名称"""
        return cls.COLUMN_CONFIGS[column].name

    @classmethod
    def get_column_width(cls, column: GridColumn) -> int:
        """获取列宽"""
        return cls.COLUMN_CONFIGS[column].width

class GridDisplayModel:
    """网格显示模型"""
    def __init__(self):
        self._data: Dict[GridColumn, Any] = {}
        
    def update(self, grid_data) -> None:
        """从GridData更新显示数据"""
        position_metrics = grid_data.calculate_position_metrics()
        grid_status = grid_data.get_grid_status()
        tp_sl_prices = grid_data.calculate_avg_price_tp_sl_prices()
        
        updates = {
            GridColumn.PAIR: grid_data.pair,
            GridColumn.DIRECTION: grid_data.direction.value,
            GridColumn.STATUS: grid_data.row_dict.get("运行状态", ""),
            GridColumn.GRID_LEVEL: f"{grid_status['filled_levels']}/{grid_status['total_levels']}",
            GridColumn.LAST_PRICE: str(grid_data.last_price) if grid_data.last_price else "-",
            GridColumn.LAST_TIME: grid_data.last_update_time.strftime("%H:%M:%S") if grid_data.last_update_time else "-",
            GridColumn.AVG_PRICE: str(position_metrics['avg_price']),
            GridColumn.POS_VALUE: str(position_metrics['total_value']),
            GridColumn.POS_PNL: str(position_metrics['unrealized_pnl']),
            GridColumn.REALIZED_PNL: str(grid_data.total_realized_profit),
            GridColumn.EXCHANGE: grid_data.exchange,
            GridColumn.UID: grid_data.uid,
            # ... 其他列的更新
        }
        
        if tp_sl_prices['avg_tp_price']:
            updates[GridColumn.ATP_TRIGGER] = str(tp_sl_prices['avg_tp_price'])
        if tp_sl_prices['avg_sl_price']:
            updates[GridColumn.ASL_TRIGGER] = str(tp_sl_prices['avg_sl_price'])
            
        self._data.update(updates)
        
    def get_value(self, column: GridColumn) -> Any:
        """获取列值"""
        return self._data.get(column)

    def get_all_values(self) -> Dict[GridColumn, Any]:
        """获取所有值"""
        return self._data.copy()

class GridUpdater(QObject):
    """UI更新管理器
    
    Signals:
        batch_update (str, dict): 批量更新信号
            - str: 策略ID
            - dict: {GridColumn: str} 格式的更新数据
    """
    batch_update = Signal(str, dict)
    
    def __init__(self):
        super().__init__()
        self._pending_updates: Dict[str, Set[GridColumn]] = defaultdict(set)
        self._display_models: Dict[str, GridDisplayModel] = {}
        
    def schedule_update(self, uid: str, columns: Set[GridColumn] = None):
        """计划更新"""
        if columns is None:
            # 更新所有列
            columns = set(GridColumn)
        self._pending_updates[uid].update(columns)
        
    def commit_updates(self):
        """提交所有待更新"""
        for uid, columns in self._pending_updates.items():
            if uid in self._display_models:
                model = self._display_models[uid]
                updates = {col: model.get_value(col) for col in columns}
                self.batch_update.emit(uid, updates)
        self._pending_updates.clear()
        
    def register_strategy(self, uid: str) -> GridDisplayModel:
        """注册策略显示模型"""
        model = GridDisplayModel()
        self._display_models[uid] = model
        return model
        
    def unregister_strategy(self, uid: str):
        """注销策略显示模型"""
        self._display_models.pop(uid, None)
        self._pending_updates.pop(uid, None)

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
    
    def __init__(self, strategy_wrapper: StrategyManagerWrapper):
        visible_columns = GridColumnManager.get_visible_columns()
        super().__init__(0, len(visible_columns))
        
        self.strategy_wrapper = strategy_wrapper
        self.updater = GridUpdater()
        # 连接批量更新信号
        self.updater.batch_update.connect(self._handle_batch_update)
        
        self.setup_table()

    def _handle_batch_update(self, uid: str, updates: Dict[GridColumn, Any]):
        """处理批量更新"""
        try:
            # 查找对应行
            row = -1
            uid_col = GridColumnManager.get_column_index(GridColumn.UID)
            for i in range(self.rowCount()):
                uid_item = self.item(i, uid_col)
                if uid_item and uid_item.text() == uid:
                    row = i
                    break
                    
            if row == -1:
                print(f"[GridTable] 未找到策略行: {uid}")
                return
                
            # 更新单元格
            for column, value in updates.items():
                if column == GridColumn.OPERATIONS:
                    continue  # 操作按钮需要特殊处理
                    
                col_idx = GridColumnManager.get_column_index(column)
                if col_idx >= 0:
                    # 为None的值显示为"-"
                    display_value = "-" if value is None else str(value)
                    
                    item = QTableWidgetItem(display_value)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.setItem(row, col_idx, item)
                    
        except Exception as e:
            print(f"[GridTable] 批量更新失败: {e}")
            print(f"[GridTable] 错误详情: {traceback.format_exc()}")
        
    def setup_table(self):
        """设置表格基本属性"""
        visible_columns = GridColumnManager.get_visible_columns()
        
        # 设置列标题
        headers = [GridColumnManager.get_column_name(col) for col in visible_columns]
        self.setHorizontalHeaderLabels(headers)
        
        # 设置列宽
        for i, col in enumerate(visible_columns):
            self.setColumnWidth(i, GridColumnManager.get_column_width(col))
        
        # 设置表格属性
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        
        # 设置样式
        # self.setStyleSheet("""
        #     QTableWidget {
        #         gridline-color: #E5E5E5;
        #         background-color: white;
        #         border: 1px solid #D3D3D3;
        #     }
        #     QTableWidget::item {
        #         padding: 5px;
        #     }
        #     QHeaderView::section {
        #         background-color: #F5F5F5;
        #         padding: 5px;
        #         border: none;
        #         border-right: 1px solid #D3D3D3;
        #         border-bottom: 1px solid #D3D3D3;
        #     }
        # """)

    def add_strategy_row(self, grid_data: GridData):
        try:
            # 创建显示模型
            display_model = self.updater.register_strategy(grid_data.uid)
            display_model.update(grid_data)
            
            # 添加新行
            row = self.rowCount()
            self.insertRow(row)
            
            # 创建操作按钮
            operation_status = grid_data.row_dict.get("操作", {"开仓": True, "平仓": True})
            self._create_operation_buttons(row, grid_data.uid, operation_status)
            
            # 更新所有列
            self.updater.schedule_update(grid_data.uid)
            self.updater.commit_updates()
            
        except Exception as e:
            print(f"[GridTable] 添加策略行失败: {e}")

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

    def update(self, grid_data) -> None:
        """更新所有显示数据"""
        position_metrics = grid_data.calculate_position_metrics()
        grid_status = grid_data.get_grid_status()
        tp_sl_prices = grid_data.calculate_avg_price_tp_sl_prices()
        
        # 更新所有可能的数据
        updates = {
            # 基础信息
            GridColumn.PAIR: grid_data.pair,
            GridColumn.DIRECTION: grid_data.direction.value,
            GridColumn.STATUS: grid_data.row_dict.get("运行状态", ""),
            GridColumn.GRID_LEVEL: f"{grid_status['filled_levels']}/{grid_status['total_levels']}",
            GridColumn.EXCHANGE: grid_data.exchange,
            GridColumn.UID: grid_data.uid,
            
            # 市场数据  
            GridColumn.LAST_PRICE: str(grid_data.last_price) if grid_data.last_price else "-",
            GridColumn.LAST_TIME: grid_data.last_update_time.strftime("%H:%M:%S") if grid_data.last_update_time else "-",
            
            # 持仓数据
            GridColumn.AVG_PRICE: str(position_metrics['avg_price']),
            GridColumn.POS_VALUE: str(position_metrics['total_value']),
            GridColumn.POS_PNL: str(position_metrics['unrealized_pnl']),
            GridColumn.REALIZED_PNL: str(grid_data.total_realized_profit),
            
            # 触发价格
            GridColumn.OPEN_TRIGGER: grid_data.row_dict.get("开仓触发价", "-"),
            GridColumn.TP_TRIGGER: grid_data.row_dict.get("止盈触发价", "-"),
            
            # 止盈止损
            GridColumn.AVG_TP: grid_data.row_dict.get("均价止盈", "-"),
            GridColumn.AVG_SL: grid_data.row_dict.get("均价止损", "-"),
            GridColumn.TOTAL_TP: grid_data.row_dict.get("总体止盈", "-"), 
            GridColumn.TOTAL_SL: grid_data.row_dict.get("总体止损", "-"),
        }
        
        # 更新额外的止盈止损触发价
        if tp_sl_prices['avg_tp_price']:
            updates[GridColumn.ATP_TRIGGER] = str(tp_sl_prices['avg_tp_price'])
        if tp_sl_prices['avg_sl_price']:
            updates[GridColumn.ASL_TRIGGER] = str(tp_sl_prices['avg_sl_price'])
                
        self._data.update(updates)

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

    def get_column_index(self, column: Union[str, GridColumn]) -> int:
        """获取列索引"""
        if isinstance(column, str):
            # 兼容字符串列名 -> 枚举 的转换
            try:
                column = next(k for k, v in GridColumnManager.COLUMN_CONFIGS.items() 
                            if v.name == column)
            except StopIteration:
                return -1
        return GridColumnManager.get_column_index(column)

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