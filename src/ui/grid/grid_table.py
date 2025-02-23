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
    UID = auto()            # 标识符 (移到第一列)
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
    AVG_TP = auto()         # 均价止盈
    AVG_SL = auto()         # 均价止损
    TOTAL_TP = auto()       # 总体止盈
    TOTAL_SL = auto()       # 总体止损
    POS_VALUE = auto()      # 持仓价值
    POS_PNL = auto()        # 持仓盈亏
    REALIZED_PNL = auto()   # 实现盈亏
    EXCHANGE = auto()       # 交易所

@dataclass
class GridColumnConfig:
    """列配置"""
    name: str              # 显示名称
    width: int            # 列宽
    editable: bool = False # 是否可编辑
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
        GridColumn.OPEN_TRIGGER: GridColumnConfig("开仓触发价", 115),
        GridColumn.TP_TRIGGER: GridColumnConfig("止盈触发价", 115),
        GridColumn.ATP_TRIGGER: GridColumnConfig("均价止盈触发价", 120),
        GridColumn.ASL_TRIGGER: GridColumnConfig("均价止损触发价", 120),
        GridColumn.AVG_TP: GridColumnConfig("均价止盈%", 100),
        GridColumn.AVG_SL: GridColumnConfig("均价止损%", 100),
        GridColumn.TOTAL_TP: GridColumnConfig("总止盈额", 100),
        GridColumn.TOTAL_SL: GridColumnConfig("总止损额", 100),
        GridColumn.POS_VALUE: GridColumnConfig("持仓价值", 100),
        GridColumn.POS_PNL: GridColumnConfig("持仓盈亏", 100),
        GridColumn.REALIZED_PNL: GridColumnConfig("实现盈亏", 100),
        GridColumn.EXCHANGE: GridColumnConfig("交易所", 100),
        GridColumn.UID: GridColumnConfig("标识符", 100),
    }

    @classmethod
    def get_visible_columns(cls) -> list:
        return [col for col, cfg in cls.COLUMN_CONFIGS.items() if cfg.visible]
    
    @classmethod
    def get_column_index(cls, column: GridColumn) -> int:
        visible_columns = cls.get_visible_columns()
        try:
            return visible_columns.index(column)
        except ValueError:
            return -1

    @classmethod
    def get_column_name(cls, column: GridColumn) -> str:
        return cls.COLUMN_CONFIGS[column].name

    @classmethod
    def get_column_width(cls, column: GridColumn) -> int:
        return cls.COLUMN_CONFIGS[column].width

class GridDisplayModel:
    """网格显示模型"""
    def __init__(self):
        self._data: Dict[GridColumn, Any] = {}
        
    def update(self, grid_data: GridData) -> None:
        """从GridData更新显示数据"""
        position_metrics = grid_data.calculate_position_metrics()
        grid_status = grid_data.get_grid_status()
        tp_sl_prices = grid_data.calculate_avg_price_tp_sl_prices()
        
        updates = {
            GridColumn.UID: grid_data.uid,
            GridColumn.PAIR: grid_data.symbol_config.pair,
            GridColumn.DIRECTION: grid_data.direction.value,
            GridColumn.STATUS: grid_data.status,
            GridColumn.GRID_LEVEL: f"{grid_status['filled_levels']}/{grid_status['total_levels']}" if grid_status['total_levels'] > 0 else "未设置",
            GridColumn.LAST_TIME: datetime.fromtimestamp(grid_data.ticker_data.ts / 1000).strftime("%H:%M:%S") if grid_data.ticker_data else "-",
            GridColumn.LAST_PRICE: str(grid_data.ticker_data.lastPr) if grid_data.ticker_data else "-",
            GridColumn.AVG_PRICE: str(position_metrics['avg_price']),
            GridColumn.OPEN_TRIGGER: str(grid_data.open_trigger_price) if grid_data.open_trigger_price else "-",
            GridColumn.TP_TRIGGER: str(grid_data.tp_trigger_price) if grid_data.tp_trigger_price else "-",
            GridColumn.ATP_TRIGGER: str(tp_sl_prices['avg_tp_price']) if tp_sl_prices['avg_tp_price'] else "-",
            GridColumn.ASL_TRIGGER: str(tp_sl_prices['avg_sl_price']) if tp_sl_prices['avg_sl_price'] else "-",
            GridColumn.AVG_TP: str(grid_data.avg_price_take_profit_config.profit_percent) if grid_data.avg_price_take_profit_config.enabled else "-",
            GridColumn.AVG_SL: str(grid_data.avg_price_stop_loss_config.loss_percent) if grid_data.avg_price_stop_loss_config.enabled else "-",
            GridColumn.TOTAL_TP: str(grid_data.take_profit_config.profit_amount) if grid_data.take_profit_config.enabled else "-",
            GridColumn.TOTAL_SL: str(grid_data.stop_loss_config.loss_amount) if grid_data.stop_loss_config.enabled else "-",
            GridColumn.POS_VALUE: str(position_metrics['total_value']),
            GridColumn.POS_PNL: str(position_metrics['unrealized_pnl']),
            GridColumn.REALIZED_PNL: str(grid_data.total_realized_profit),
            GridColumn.EXCHANGE: grid_data.exchange_str,
        }
        
        self._data.update(updates)
        
    def get_value(self, column: GridColumn) -> Any:
        return self._data.get(column)

    def get_all_values(self) -> Dict[GridColumn, Any]:
        return self._data.copy()

class GridUpdater(QObject):
    """UI更新管理器"""
    batch_update = Signal(str, dict)
    
    def __init__(self):
        super().__init__()
        self._pending_updates: Dict[str, Set[GridColumn]] = defaultdict(set)
        self._display_models: Dict[str, GridDisplayModel] = {}
        
    def schedule_update(self, uid: str, columns: Set[GridColumn] = None):
        if columns is None:
            columns = set(GridColumn)
        self._pending_updates[uid].update(columns)
        
    def commit_updates(self):
        for uid, columns in self._pending_updates.items():
            if uid in self._display_models:
                model = self._display_models[uid]
                updates = {col: model.get_value(col) for col in columns}
                self.batch_update.emit(uid, updates)
        self._pending_updates.clear()
        
    def register_strategy(self, uid: str) -> GridDisplayModel:
        model = GridDisplayModel()
        self._display_models[uid] = model
        return model
        
    def unregister_strategy(self, uid: str):
        self._display_models.pop(uid, None)
        self._pending_updates.pop(uid, None)

class GridTable(QTableWidget):
    """网格策略表格组件"""
    
    strategy_setting_requested = Signal(str)
    strategy_start_requested = Signal(str)
    strategy_stop_requested = Signal(str)
    strategy_delete_requested = Signal(str)
    strategy_close_requested = Signal(str)
    strategy_refresh_requested = Signal(str)
    dialog_requested = Signal(str, str, str)
    
    def __init__(self, strategy_wrapper: StrategyManagerWrapper):
        visible_columns = GridColumnManager.get_visible_columns()
        super().__init__(0, len(visible_columns))
        
        self.strategy_wrapper = strategy_wrapper
        self.updater = GridUpdater()
        self.updater.batch_update.connect(self._handle_batch_update)
        
        self.setup_table()

    def setup_table(self):
        headers = [GridColumnManager.get_column_name(col) for col in GridColumnManager.get_visible_columns()]
        self.setHorizontalHeaderLabels(headers)
        
        for i, col in enumerate(GridColumnManager.get_visible_columns()):
            self.setColumnWidth(i, GridColumnManager.get_column_width(col))
        
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)

    def get_all_uids(self) -> list:
        """获取表格中所有策略的 UID"""
        uids = []
        uid_col = GridColumnManager.get_column_index(GridColumn.UID)
        for row in range(self.rowCount()):
            uid_item = self.item(row, uid_col)
            if uid_item:
                uids.append(uid_item.text())
        return uids

    def add_strategy_row(self, grid_data: GridData):
        """添加策略行，所有数据居中对齐"""
        try:
            print(f"[GridTable] 添加策略行: UID={grid_data.uid}, Pair={grid_data.symbol_config.pair}")
            display_model = self.updater.register_strategy(grid_data.uid)
            display_model.update(grid_data)
            
            row = self.rowCount()
            self.insertRow(row)
            print(f"[GridTable] 已插入新行: Row={row}")
            
            # 添加所有列的数据
            visible_columns = GridColumnManager.get_visible_columns()
            for col in visible_columns:
                if col == GridColumn.OPERATIONS:
                    self._create_operation_buttons(row, grid_data.uid, grid_data.operations)
                else:
                    value = display_model.get_value(col)
                    display_value = "-" if value is None else str(value)
                    item = QTableWidgetItem(display_value)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)  # 居中对齐
                    col_idx = GridColumnManager.get_column_index(col)
                    self.setItem(row, col_idx, item)
            
            print(f"[GridTable] 策略行添加完成: UID={grid_data.uid}")
            
        except Exception as e:
            print(f"[GridTable] 添加策略行失败: {e}")
            print(f"[GridTable] 错误详情: {traceback.format_exc()}")
            self.dialog_requested.emit("error", "错误", f"添加策略行失败: {str(e)}")

    def update_strategy_row(self, uid: str, grid_data: GridData):
        """更新策略行，所有数据居中对齐"""
        try:
            uid_col = GridColumnManager.get_column_index(GridColumn.UID)
            row = -1
            for i in range(self.rowCount()):
                uid_item = self.item(i, uid_col)
                if uid_item and uid_item.text() == uid:
                    row = i
                    break
                    
            if row == -1:
                print(f"[GridTable] 未找到策略行: {uid}")
                return
                
            display_model = self.updater._display_models.get(uid)
            if display_model:
                display_model.update(grid_data)
                visible_columns = GridColumnManager.get_visible_columns()
                for col in visible_columns:
                    if col != GridColumn.OPERATIONS:  # 操作按钮单独处理
                        value = display_model.get_value(col)
                        display_value = "-" if value is None else str(value)
                        item = QTableWidgetItem(display_value)
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)  # 居中对齐
                        col_idx = GridColumnManager.get_column_index(col)
                        self.setItem(row, col_idx, item)
                
                # 更新操作按钮状态
                self._update_operation_buttons(row, uid, grid_data.operations)
                
            # print(f"[GridTable] 策略行更新完成: UID={uid}")
            
        except Exception as e:
            print(f"[GridTable] 更新策略行失败: {e}")
            print(f"[GridTable] 错误详情: {traceback.format_exc()}")

    def _handle_batch_update(self, uid: str, updates: Dict[GridColumn, Any]):
        """处理批量更新，所有数据居中对齐"""
        try:
            uid_col = GridColumnManager.get_column_index(GridColumn.UID)
            row = -1
            for i in range(self.rowCount()):
                uid_item = self.item(i, uid_col)
                if uid_item and uid_item.text() == uid:
                    row = i
                    break
                    
            if row == -1:
                print(f"[GridTable] 未找到策略行: UID={uid}")
                return
                
            for column, value in updates.items():
                if column == GridColumn.OPERATIONS:
                    continue
                    
                col_idx = GridColumnManager.get_column_index(column)
                if col_idx >= 0:
                    display_value = "-" if value is None else str(value)
                    item = QTableWidgetItem(display_value)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)  # 居中对齐
                    self.setItem(row, col_idx, item)
            
        except Exception as e:
            print(f"[GridTable] 批量更新失败: {e}")
            print(f"[GridTable] 错误详情: {traceback.format_exc()}")

    def _create_operation_buttons(self, row: int, uid: str, status: Dict[str, bool]):
        """创建操作按钮"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        open_button = QPushButton("开")
        close_button = QPushButton("平")

        open_button.setCheckable(True)
        close_button.setCheckable(True)
        open_button.setChecked(status.get("开仓", True))
        close_button.setChecked(status.get("平仓", True))

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

        def create_toggle_handler(operation_type: str):
            def handler(checked: bool):
                self._handle_operation_toggled(uid, operation_type, checked)
            return handler

        open_button.toggled.connect(create_toggle_handler("开仓"))
        close_button.toggled.connect(create_toggle_handler("平仓"))

        layout.addWidget(open_button)
        layout.addWidget(close_button)
        self.setCellWidget(row, GridColumnManager.get_column_index(GridColumn.OPERATIONS), container)

    def _update_operation_buttons(self, row: int, uid: str, status: Dict[str, bool]):
        """更新操作按钮状态"""
        operation_widget = self.cellWidget(row, GridColumnManager.get_column_index(GridColumn.OPERATIONS))
        if operation_widget:
            layout = operation_widget.layout()
            open_button = layout.itemAt(0).widget()
            close_button = layout.itemAt(1).widget()
            open_button.setChecked(status.get("开仓", True))
            close_button.setChecked(status.get("平仓", True))

    def _handle_operation_toggled(self, uid: str, operation_type: str, checked: bool):
        grid_data = self.strategy_wrapper.get_strategy_data(uid)
        if grid_data:
            grid_data.operations[operation_type] = checked
            grid_data.data_updated.emit(uid)

    def show_context_menu(self, position):
        index = self.indexAt(position)
        if not index.isValid():
            return

        row = index.row()
        uid_item = self.item(row, GridColumnManager.get_column_index(GridColumn.UID))
        if not uid_item:
            print(f"[GridTable] 未找到 UID 单元格: Row={row}")
            return
        uid = uid_item.text()
        
        status = self.get_strategy_status(uid)
        if not status:
            print(f"[GridTable] 未找到状态: UID={uid}")
            return
            
        menu = QMenu(self)
        menu.addAction("设置网格", lambda: self.strategy_setting_requested.emit(uid))
        
        if status == "运行中":
            menu.addAction("停止策略", lambda: self.strategy_stop_requested.emit(uid))
        else:
            menu.addAction("启动策略", lambda: self.strategy_start_requested.emit(uid))

        menu.addSeparator()
        if status != "运行中":
            menu.addAction("平仓", lambda: self._handle_close_strategy(uid))
        
        menu.addSeparator()
        menu.addAction("刷新数据", lambda: self.strategy_refresh_requested.emit(uid))

        menu.addSeparator()
        menu.addAction("删除", lambda: self._handle_delete_strategy(uid, status))
        
        menu.exec(self.mapToGlobal(position))

    def _handle_delete_strategy(self, uid: str, status: str):
        try:
            if status == "运行中":
                self.dialog_requested.emit("warning", "警告", "请先停止策略再删除！")
                return
                
            grid_data = self.strategy_wrapper.get_strategy_data(uid)
            if not grid_data:
                self.dialog_requested.emit("error", "错误", "策略数据不存在！")
                return
                
            position_metrics = grid_data.calculate_position_metrics()
            if position_metrics['total_value'] > 0:
                self.dialog_requested.emit("warning", "警告", "策略仍有持仓，请先平仓后再删除！")
                return
                
            self.strategy_delete_requested.emit(uid)
        except Exception as e:
            self.dialog_requested.emit("error", "错误", f"删除策略失败: {str(e)}")

    def _handle_close_strategy(self, uid: str):
        status = self.get_strategy_status(uid)
        if status == "运行中":
            self.dialog_requested.emit("warning", "警告", "请先停止策略再进行平仓！")
            return
            
        self.strategy_close_requested.emit(uid)

    def get_column_index(self, column: Union[str, GridColumn]) -> int:
        if isinstance(column, str):
            try:
                column = next(k for k, v in GridColumnManager.COLUMN_CONFIGS.items() 
                            if v.name == column)
            except StopIteration:
                return -1
        return GridColumnManager.get_column_index(column)

    def remove_strategy(self, uid: str):
        uid_col = GridColumnManager.get_column_index(GridColumn.UID)
        for row in range(self.rowCount()):
            if self.item(row, uid_col).text() == uid:
                self.removeRow(row)
                self.updater.unregister_strategy(uid)
                break

    def get_strategy_status(self, uid: str) -> Optional[str]:
        uid_col = GridColumnManager.get_column_index(GridColumn.UID)
        status_col = GridColumnManager.get_column_index(GridColumn.STATUS)
        for row in range(self.rowCount()):
            if self.item(row, uid_col).text() == uid:
                status_item = self.item(row, status_col)
                return status_item.text() if status_item else None
        return None

    def update_operation_status(self, uid: str, operation_type: str, enabled: bool):
        uid_col = GridColumnManager.get_column_index(GridColumn.UID)
        for row in range(self.rowCount()):
            if self.item(row, uid_col).text() == uid:
                operation_widget = self.cellWidget(row, GridColumnManager.get_column_index(GridColumn.OPERATIONS))
                if operation_widget:
                    layout = operation_widget.layout()
                    button_index = 0 if operation_type == "开仓" else 1
                    button = layout.itemAt(button_index).widget()
                    if button:
                        button.setChecked(enabled)
                break

    def set_all_operation_status(self, operation_type: str, enabled: bool):
        ops_col = GridColumnManager.get_column_index(GridColumn.OPERATIONS)
        for row in range(self.rowCount()):
            operation_widget = self.cellWidget(row, ops_col)
            if operation_widget:
                layout = operation_widget.layout()
                button_index = 0 if operation_type == "开仓" else 1
                button = layout.itemAt(button_index).widget()
                if button:
                    button.setChecked(enabled)

    def disable_all_operations(self, uid: str):
        self.update_operation_status(uid, "开仓", False)
        self.update_operation_status(uid, "平仓", False)

    def enable_all_operations(self, uid: str):
        self.update_operation_status(uid, "开仓", True)
        self.update_operation_status(uid, "平仓", True)