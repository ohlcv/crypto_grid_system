from decimal import Decimal
import traceback
import uuid
from typing import Optional
from qtpy.QtWidgets import (
    QDialog, QVBoxLayout, QTableWidget, QLineEdit, QPushButton, QHBoxLayout,
    QMessageBox, QLabel, QHeaderView, QTableWidgetItem, QMenu, QSizePolicy, 
    QWidget, QGroupBox, QGridLayout, QCheckBox
)
from qtpy.QtGui import QIntValidator, QDoubleValidator, QAction
from qtpy.QtCore import Qt
from datetime import datetime

from src.exchange.base_client import (
    InstType, OrderType, OrderSide, TradeSide, PositionSide
)
from src.strategy.grid.grid_core import GridData, LevelConfig
from src.ui.grid.strategy_manager_wrapper import StrategyManagerWrapper
from src.utils.logger.log_helper import ui_logger

class GridSetting(QTableWidget):
    COLUMN_NAMES = ["间隔%", "止盈%", "开仓反弹%", "平仓反弹%", "成交额", "成交量", "开仓价", "开仓时间", "已开仓", "操作"]
    
    def __init__(self):
        super().__init__(0, len(self.COLUMN_NAMES))
        self.column_indices = {name: idx for idx, name in enumerate(self.COLUMN_NAMES)}
        self.setHorizontalHeaderLabels(self.COLUMN_NAMES)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.setShowGrid(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def show_context_menu(self, position):
        menu = QMenu(self)
        add_row_action = QAction("添加行", self)
        add_row_action.triggered.connect(lambda: self.add_row())
        menu.addAction(add_row_action)
        clear_table_action = QAction("清空表格", self)
        clear_table_action.triggered.connect(self.clear_table)
        menu.addAction(clear_table_action)
        menu.exec(self.viewport().mapToGlobal(position))

    def add_row(self, initial_values=None):
        """向表格中添加一行"""
        row_position = self.rowCount()
        self.insertRow(row_position)
        unique_id = str(uuid.uuid4())
        is_filled = initial_values.get("已开仓", "否") if initial_values else "否"
        
        for col_name, col_idx in self.column_indices.items():
            value = initial_values.get(col_name, "") if initial_values else ""
            if col_name == "操作":
                self.add_delete_button(row_position, unique_id)
            else:
                validator = None
                if col_name in ["间隔%", "止盈%", "开仓反弹%", "平仓反弹%"]:
                    validator = QDoubleValidator(0.0, 100.0, 3)
                elif col_name == "成交额":
                    validator = QDoubleValidator(0.0, 9999999.99, 2)
                
                cell_editable = not (is_filled == "是" or 
                                   col_name in ["成交量", "开仓价", "开仓时间", "已开仓"])
                self.set_table_cell(row_position, col_idx, value, validator, cell_editable)
                
        self.setRowProperty(row_position, "unique_id", unique_id)

    def handle_delete_row(self):
        button = self.sender()
        if not button:
            return
        unique_id = button.property("unique_id")
        if not unique_id:
            return
            
        row_to_delete = None
        for row in range(self.rowCount()):
            if self.getRowProperty(row, "unique_id") == unique_id:
                row_to_delete = row
                break
                
        if row_to_delete is not None:
            self.delete_row(row_to_delete)

    def add_delete_button(self, row, unique_id, setDisabled=False):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        delete_button = QPushButton("-")
        delete_button.setProperty("unique_id", unique_id)
        delete_button.clicked.connect(self.handle_delete_row)
        delete_button.setFixedWidth(50)
        layout.addWidget(delete_button)
        
        already_opened = self.get_cell_value(row, self.column_indices["已开仓"])
        if already_opened == "是" and setDisabled:
            delete_button.setDisabled(True)
        self.setCellWidget(row, self.column_indices["操作"], container)

    def setRowProperty(self, row, key, value):
        for col in range(self.columnCount()):
            item = self.item(row, col)
            if item:
                data = item.data(Qt.ItemDataRole.UserRole + 1) or {}
                data[key] = value
                item.setData(Qt.ItemDataRole.UserRole + 1, data)
            else:
                new_item = QTableWidgetItem()
                new_item.setData(Qt.ItemDataRole.UserRole + 1, {key: value})
                self.setItem(row, col, new_item)

    def getRowProperty(self, row, key):
        for col in range(self.columnCount()):
            item = self.item(row, col)
            if item:
                data = item.data(Qt.ItemDataRole.UserRole + 1)
                if data and key in data:
                    return data[key]
        return None

    def get_cell_value(self, row, col):
        widget = self.cellWidget(row, col)
        if widget:
            if isinstance(widget, QLineEdit):
                return widget.text()
            elif isinstance(widget, QWidget):
                line_edit = widget.findChild(QLineEdit)
                if line_edit:
                    return line_edit.text()
        item = self.item(row, col)
        return item.text() if item else ""

    def delete_row(self, row, setDisabled=False):
        is_filled = self.get_cell_value(row, self.column_indices["已开仓"])
        if is_filled == "是" and setDisabled:
            QMessageBox.information(self, "警告！", f"行 {row} 已开仓，不能删除")
            return False

        if is_filled == "是":
            interval = self.get_cell_value(row, self.column_indices["间隔%"])
            filled_price = self.get_cell_value(row, self.column_indices["开仓价"])
            filled_amount = self.get_cell_value(row, self.column_indices["成交量"])
            
            msg = (f"确认删除已开仓的网格层?\n"
                  f"开仓价格: {filled_price}\n"
                  f"开仓数量: {filled_amount}\n"
                  f"间隔: {interval}%")
            reply = QMessageBox.question(
                self,
                "删除确认",
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.No:
                return False

        self.removeRow(row)
        for i in range(row, self.rowCount()):
            widget = self.cellWidget(i, self.column_indices["操作"])
            if widget:
                button = widget.findChild(QPushButton)
                if button:
                    button.setProperty("row", i)
        return True

    def clear_table(self):
        self.setRowCount(0)

    def set_table_cell(self, row, col, value, validator=None, editable=True):
        if editable:
            line_edit = QLineEdit(str(value))
            line_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if validator:
                line_edit.setValidator(validator)
            self.setCellWidget(row, col, line_edit)
        else:
            item = QTableWidgetItem()
            item.setText(str(value))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if col == 0:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            old_item = self.item(row, col)
            if old_item:
                self.takeItem(row, col)
            self.setItem(row, col, item)

class GridDialog(QDialog):
    def __init__(self, grid_data: GridData, strategy_wrapper: StrategyManagerWrapper):
        super().__init__()
        self.grid_data = grid_data
        self.strategy_wrapper = strategy_wrapper
        self.setWindowTitle(f"设置网格策略 - {self.grid_data.symbol_config.pair}")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(1000)
        self.setMinimumHeight(500)
        self.setup_ui()
        self.load_grid_data()

    def setup_ui(self):
        layout = QVBoxLayout()

        # === 网格表格 ===
        self.table = GridSetting()
        layout.addWidget(self.table)

        # === 第一行输入框：预算和层数等 ===
        input_layout = QHBoxLayout()
        input_layout.setSpacing(5)

        # 预算
        self.budget_input = self.create_input_field("预算资金 (USDT)", QDoubleValidator(0.0, 9999999.99, 3))
        input_layout.addWidget(QLabel("预算:"))
        input_layout.addWidget(self.budget_input)

        # 层数
        self.grid_layers_input = self.create_input_field("层数", QIntValidator(1, 1000))
        input_layout.addWidget(QLabel("层数:"))
        input_layout.addWidget(self.grid_layers_input)

        # 间隔%
        self.build_interval_input = self.create_input_field("间隔%", QDoubleValidator(0.0, 100.0, 3))
        input_layout.addWidget(QLabel("间隔%:"))
        input_layout.addWidget(self.build_interval_input)

        # 止盈%
        self.take_profit_input = self.create_input_field("止盈%", QDoubleValidator(0.0, 100.0, 3))
        input_layout.addWidget(QLabel("止盈%:"))
        input_layout.addWidget(self.take_profit_input)

        # 开仓反弹%
        self.open_rebound_input = self.create_input_field("开仓反弹%", QDoubleValidator(0.0, 100.0, 3))
        input_layout.addWidget(QLabel("开仓反弹%:"))
        input_layout.addWidget(self.open_rebound_input)

        # 平仓反弹%
        self.close_rebound_input = self.create_input_field("平仓反弹%", QDoubleValidator(0.0, 100.0, 3))
        input_layout.addWidget(QLabel("平仓反弹%:"))
        input_layout.addWidget(self.close_rebound_input)

        layout.addLayout(input_layout)

        # === 止盈止损设置 ===
        tp_sl_layout = QHBoxLayout()
        tp_sl_layout.setSpacing(10)

        # 均价止盈设置
        self.avg_tp_enabled = QCheckBox("启用均价止盈")
        tp_sl_layout.addWidget(self.avg_tp_enabled)
                
        self.avg_tp_percent = QLineEdit()
        self.avg_tp_percent.setValidator(QDoubleValidator(0.0, 999999.99, 2))
        self.avg_tp_percent.setPlaceholderText("止盈百分比(%)")
        self.avg_tp_percent.setFixedWidth(120)
        self.avg_tp_percent.setEnabled(False)
        tp_sl_layout.addWidget(self.avg_tp_percent)

        # 均价止损设置
        self.avg_sl_enabled = QCheckBox("启用均价止损")
        tp_sl_layout.addWidget(self.avg_sl_enabled)

        self.avg_sl_percent = QLineEdit()
        self.avg_sl_percent.setValidator(QDoubleValidator(0.0, 999999.99, 2))
        self.avg_sl_percent.setPlaceholderText("止损百分比(%)")
        self.avg_sl_percent.setFixedWidth(120)
        self.avg_sl_percent.setEnabled(False)
        tp_sl_layout.addWidget(self.avg_sl_percent)

        # 总体止盈设置
        self.tp_enabled = QCheckBox("启用总体止盈")
        tp_sl_layout.addWidget(self.tp_enabled)
                    
        self.tp_amount = QLineEdit()
        self.tp_amount.setValidator(QDoubleValidator(0.0, 999999.99, 2))
        self.tp_amount.setPlaceholderText("止盈金额(USDT)")
        self.tp_amount.setFixedWidth(120)
        self.tp_amount.setEnabled(False)
        tp_sl_layout.addWidget(self.tp_amount)

        # 总体止损设置
        self.sl_enabled = QCheckBox("启用总体止损")
        tp_sl_layout.addWidget(self.sl_enabled)

        self.sl_amount = QLineEdit()
        self.sl_amount.setValidator(QDoubleValidator(0.0, 999999.99, 2))
        self.sl_amount.setPlaceholderText("止损金额(USDT)")
        self.sl_amount.setFixedWidth(120)
        self.sl_amount.setEnabled(False)
        tp_sl_layout.addWidget(self.sl_amount)

        # 添加弹性空间
        tp_sl_layout.addStretch(1)

        # 连接信号
        self.tp_enabled.toggled.connect(self._on_tp_toggled)
        self.sl_enabled.toggled.connect(self._on_sl_toggled)
        self.avg_tp_enabled.toggled.connect(self._on_avg_tp_toggled)
        self.avg_sl_enabled.toggled.connect(self._on_avg_sl_toggled)

        layout.addLayout(tp_sl_layout)

        # === 按钮布局 ===
        button_layout = QHBoxLayout()
        self.generate_grid_button = QPushButton("生成网格")
        self.generate_grid_button.clicked.connect(self.generate_grid)
        self.save_grid_button = QPushButton("保存设置")
        self.save_grid_button.clicked.connect(self.save_grid)
        button_layout.addWidget(self.generate_grid_button)
        button_layout.addWidget(self.save_grid_button)
        layout.addLayout(button_layout)

        # === 添加行按钮 ===
        add_row_button_layout = QHBoxLayout()
        self.add_row_button = QPushButton("+")
        self.add_row_button.clicked.connect(lambda: self.table.add_row())
        add_row_button_layout.addWidget(self.add_row_button)
        layout.addLayout(add_row_button_layout)

        self.setLayout(layout)

    def _on_tp_toggled(self, checked: bool):
        """处理止盈复选框状态变化"""
        self.tp_amount.setEnabled(checked)
        if not checked:
            self.tp_amount.clear()

    def _on_sl_toggled(self, checked: bool):
        """处理止损复选框状态变化"""
        self.sl_amount.setEnabled(checked)
        if not checked:
            self.sl_amount.clear()

    def _on_avg_tp_toggled(self, checked: bool):
        """处理均价止盈复选框状态变化"""
        self.avg_tp_percent.setEnabled(checked)
        if not checked:
            self.avg_tp_percent.clear()

    def _on_avg_sl_toggled(self, checked: bool):
        """处理均价止损复选框状态变化"""
        self.avg_sl_percent.setEnabled(checked)
        if not checked:
            self.avg_sl_percent.clear()

    def create_input_field(self, placeholder_text, validator):
        """创建带有验证器的输入框"""
        input_field = QLineEdit()
        input_field.setPlaceholderText(placeholder_text)
        input_field.setValidator(validator)
        return input_field

    def validate_input(self, text, data_type, field_name, min_value=0, min_trade_value=0):
        """验证输入值"""
        try:
            value = data_type(text)
            if value < min_value:
                raise ValueError(f"{field_name} 不能小于 {min_value}！")
                
            # 如果是预算资金，验证每格投资额
            if field_name == "预算资金":
                layers_text = self.grid_layers_input.text()
                if layers_text:
                    layers = int(layers_text)
                    if layers > 0:
                        step = value / layers
                        if step < min_trade_value:
                            raise ValueError(
                                f"每格投资金额 ({step:.2f} USDT) 小于最小交易额 {min_trade_value} USDT\n"
                                f"请增加总预算或减少网格层数！"
                            )
                    
            return value
        except ValueError as e:
            if str(e).startswith(field_name):
                raise
            raise ValueError(f"请输入有效的 {field_name}！")

    def generate_grid(self):
        """生成网格"""
        try:
            # 检查必填字段
            required_fields = [
                (self.budget_input, "预算资金"),
                (self.grid_layers_input, "层数"),
                (self.build_interval_input, "间隔%"),
                (self.take_profit_input, "止盈%"),
                (self.open_rebound_input, "开仓反弹%"),
                (self.close_rebound_input, "平仓反弹%"),
            ]
            for field, name in required_fields:
                if not field.text().strip():
                    raise ValueError(f"{name} 不能为空！")

            # 验证字段
            budget = self.validate_input(self.budget_input.text(), float, "预算资金")
            layers = self.validate_input(self.grid_layers_input.text(), int, "层数", min_value=1)
            build_interval = self.validate_input(self.build_interval_input.text(), float, "间隔%")
            take_profit = self.validate_input(self.take_profit_input.text(), float, "止盈%")
            open_callback = self.validate_input(self.open_rebound_input.text(), float, "开仓反弹%")
            close_callback = self.validate_input(self.close_rebound_input.text(), float, "平仓反弹%")

            # 计算每格投入 
            step = budget / layers

            # 清空表格重新生成
            self.table.clear_table()

            # 生成网格层
            for i in range(layers):
                row_data = {
                    "间隔%": round(build_interval, 2),
                    "开仓反弹%": round(open_callback, 2),
                    "平仓反弹%": round(close_callback, 2),
                    "止盈%": round(take_profit, 2),
                    "成交额": round(step, 2),
                    "成交量": "",
                    "开仓价": "",
                    "开仓时间": "",
                    "已开仓": "否",
                }
                self.table.add_row(row_data)

        except ValueError as e:
            QMessageBox.critical(self, "错误", str(e))
        except Exception as e:
            QMessageBox.critical(self, "错误", f"生成网格失败: {str(e)}")

    def load_grid_data(self):
        """加载网格数据到表格"""
        # 加载网格层数据
        self.table.clear_table()
        for level, config in self.grid_data.grid_levels.items():
            self.table.add_row({
                "间隔%": str(config.interval_percent),
                "止盈%": str(config.take_profit_percent),
                "开仓反弹%": str(config.open_rebound_percent),
                "平仓反弹%": str(config.close_rebound_percent),
                "成交额": str(config.invest_amount),
                "成交量": str(config.filled_amount) if config.filled_amount else "",
                "开仓价": str(config.filled_price) if config.filled_price else "",
                "开仓时间": config.filled_time.strftime("%m-%d %H:%M") if config.filled_time else "",
                "已开仓": "是" if config.is_filled else "否",
            })
            
        # 加载总体止盈止损设置
        self.tp_enabled.setChecked(self.grid_data.take_profit_config.enabled)
        if self.grid_data.take_profit_config.enabled and self.grid_data.take_profit_config.profit_amount is not None:
            self.tp_amount.setEnabled(True)
            self.tp_amount.setText(str(self.grid_data.take_profit_config.profit_amount))
            
        self.sl_enabled.setChecked(self.grid_data.stop_loss_config.enabled)
        if self.grid_data.stop_loss_config.enabled and self.grid_data.stop_loss_config.loss_amount is not None:
            self.sl_amount.setEnabled(True)
            self.sl_amount.setText(str(self.grid_data.stop_loss_config.loss_amount))

        # 加载均价止盈止损设置
        self.avg_tp_enabled.setChecked(self.grid_data.avg_price_take_profit_config.enabled)
        if (self.grid_data.avg_price_take_profit_config.enabled and 
            self.grid_data.avg_price_take_profit_config.profit_percent is not None):
            self.avg_tp_percent.setEnabled(True)
            self.avg_tp_percent.setText(str(self.grid_data.avg_price_take_profit_config.profit_percent))
            
        self.avg_sl_enabled.setChecked(self.grid_data.avg_price_stop_loss_config.enabled)
        if (self.grid_data.avg_price_stop_loss_config.enabled and 
            self.grid_data.avg_price_stop_loss_config.loss_percent is not None):
            self.avg_sl_percent.setEnabled(True)
            self.avg_sl_percent.setText(str(self.grid_data.avg_price_stop_loss_config.loss_percent))

    def save_grid(self):
        """保存网格设置并同步到后台数据结构"""
        try:
            valid_existing_rows = []  # 已开仓的行  
            valid_new_rows = []      # 未开仓的有效行
            
            # 收集和验证网格层数据
            for row in range(self.table.rowCount()):
                row_data = {
                    "已开仓": self.table.get_cell_value(row, self.table.column_indices["已开仓"]),
                    "间隔%": self.table.get_cell_value(row, self.table.column_indices["间隔%"]),
                    "止盈%": self.table.get_cell_value(row, self.table.column_indices["止盈%"]),
                    "开仓反弹%": self.table.get_cell_value(row, self.table.column_indices["开仓反弹%"]),
                    "平仓反弹%": self.table.get_cell_value(row, self.table.column_indices["平仓反弹%"]),
                    "成交额": self.table.get_cell_value(row, self.table.column_indices["成交额"]),
                    "成交量": self.table.get_cell_value(row, self.table.column_indices["成交量"]),
                    "开仓价": self.table.get_cell_value(row, self.table.column_indices["开仓价"]),
                    "开仓时间": self.table.get_cell_value(row, self.table.column_indices["开仓时间"])
                }
                
                if row_data["已开仓"] == "是":
                    valid_existing_rows.append(row_data)
                else:
                    required_fields = ["间隔%", "止盈%", "开仓反弹%", "平仓反弹%", "成交额"]
                    if all(row_data.get(field) for field in required_fields):
                        valid_new_rows.append(row_data)

            # 保存总体止盈止损设置
            if self.tp_enabled.isChecked():
                if not self.tp_amount.text().strip():
                    raise ValueError("请输入总体止盈金额")
                tp_amount = Decimal(self.tp_amount.text())
                if tp_amount <= 0:
                    raise ValueError("总体止盈金额必须大于0")
                self.grid_data.take_profit_config.enable(tp_amount)
            else:
                self.grid_data.take_profit_config.disable()

            if self.sl_enabled.isChecked():
                if not self.sl_amount.text().strip():
                    raise ValueError("请输入总体止损金额")
                sl_amount = Decimal(self.sl_amount.text())
                if sl_amount <= 0:
                    raise ValueError("总体止损金额必须大于0")
                self.grid_data.stop_loss_config.enable(sl_amount)
            else:
                self.grid_data.stop_loss_config.disable()

            # 保存均价止盈止损设置
            if self.avg_tp_enabled.isChecked():
                if not self.avg_tp_percent.text().strip():
                    raise ValueError("请输入均价止盈百分比")
                avg_tp_percent = Decimal(self.avg_tp_percent.text())
                if avg_tp_percent <= 0:
                    raise ValueError("均价止盈百分比必须大于0")
                self.grid_data.avg_price_take_profit_config.enable(avg_tp_percent)
            else:
                self.grid_data.avg_price_take_profit_config.disable()

            if self.avg_sl_enabled.isChecked():
                if not self.avg_sl_percent.text().strip():
                    raise ValueError("请输入均价止损百分比")
                avg_sl_percent = Decimal(self.avg_sl_percent.text())
                if avg_sl_percent <= 0:
                    raise ValueError("均价止损百分比必须大于0")
                self.grid_data.avg_price_stop_loss_config.enable(avg_sl_percent)
            else:
                self.grid_data.avg_price_stop_loss_config.disable()

            # 处理网格层数据
            if len(valid_existing_rows) == 0 and len(valid_new_rows) == 0:
                self.grid_data.reset_to_initial()
            else:
                # 清理未开仓的网格层
                unfilled_levels = [
                    level for level, config in self.grid_data.grid_levels.items()
                    if not config.is_filled
                ]
                for level in unfilled_levels:
                    del self.grid_data.grid_levels[level]

                # 添加新的网格层 - 使用英文key
                max_level = max(self.grid_data.grid_levels.keys(), default=-1)
                next_level = max_level + 1
                
                for row_data in valid_new_rows:
                    # 使用英文key创建配置
                    level_config = {
                        "interval_percent": row_data["间隔%"],
                        "take_profit_percent": row_data["止盈%"],  
                        "open_rebound_percent": row_data["开仓反弹%"],
                        "close_rebound_percent": row_data["平仓反弹%"],
                        "invest_amount": row_data["成交额"]
                    }
                    self.grid_data.update_level(next_level, level_config)
                    next_level += 1

            # 更新网格数据
            self.grid_data.data_updated.emit(self.grid_data.uid)
            # 触发策略管理器的保存
            # self.grid_data.data_updated.connect(
            #     lambda uid: self.strategy_wrapper.save_strategies(show_message=False)
            # )
            self.accept()
            
        except ValueError as e:
            QMessageBox.warning(self, "输入错误", str(e))
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存设置失败: {str(e)}")
            print(f"[GridDialog] 保存网格设置出错: {e}")
            print(f"[GridDialog] 错误详情: {traceback.format_exc()}")