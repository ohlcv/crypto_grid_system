# grid_strategy_settings.py
from decimal import Decimal
import uuid
from qtpy.QtWidgets import (
    QDialog, QVBoxLayout, QTableWidget, QLineEdit, QPushButton, QHBoxLayout,
    QMessageBox, QLabel, QHeaderView, QTableWidgetItem, QMenu, QSizePolicy, QWidget
)
from qtpy.QtGui import QIntValidator, QDoubleValidator, QAction
from qtpy.QtCore import Qt
from src.utils.logger.log_helper import ui_logger


class GridSetting(QTableWidget):
    COLUMN_NAMES = ["间隔%", "止盈%", "开仓反弹%", "平仓反弹%", "成交额", "成交量", "开仓价", "开仓时间", "已开仓", "操作"]
    
    def __init__(self):
        super().__init__(0, len(self.COLUMN_NAMES))
        self.column_indices = {name: idx for idx, name in enumerate(self.COLUMN_NAMES)}
        self.setHorizontalHeaderLabels(self.COLUMN_NAMES)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.setSelectionMode(QTableWidget.SelectionMode.NoSelection)  # 禁用选择
        self.setShowGrid(True)  # 显示网格线
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def show_context_menu(self, position):
        """显示右键菜单"""
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
        # 为每一行生成唯一标识符
        unique_id = str(uuid.uuid4())
        # 获取是否已开仓
        is_filled = initial_values.get("已开仓", "否") if initial_values else "否"
        # 遍历所有列，设置每列的内容和属性
        for col_name, col_idx in self.column_indices.items():
            value = initial_values.get(col_name, "") if initial_values else ""
            if col_name == "操作":
                # 添加删除按钮，并将唯一标识符绑定到按钮
                self.add_delete_button(row_position, unique_id)
            else:
                # 设置验证器
                validator = None
                if col_name in ["间隔%", "止盈%", "开仓反弹%", "平仓反弹%"]:
                    validator = QDoubleValidator(0.0, 100.0, 3)
                elif col_name == "成交额":
                    validator = QDoubleValidator(0.0, 9999999.99, 2)
                # 如果已开仓，除了"已开仓"外的所有格子都禁用编辑
                cell_editable = not (is_filled == "是" or 
                                    col_name in ["成交量", "开仓价", "开仓时间", "已开仓"])
                self.set_table_cell(row_position, col_idx, value, validator, cell_editable)
        # 将唯一标识符存储在表格项属性中
        self.setRowProperty(row_position, "unique_id", unique_id)

    def handle_delete_row(self):
        """处理删除行按钮点击"""
        button = self.sender()
        if not button:
            return
        unique_id = button.property("unique_id")
        if not unique_id:
            return
        # 查找行号
        row_to_delete = None
        for row in range(self.rowCount()):
            if self.getRowProperty(row, "unique_id") == unique_id:
                row_to_delete = row
                break
        if row_to_delete is not None:
            self.delete_row(row_to_delete)
        else:
            print(f"[GridSetting] 未找到要删除的行，唯一标识符: {unique_id}")

    def add_delete_button(self, row, unique_id, setDisabled=False):
        """添加删除按钮"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        delete_button = QPushButton("-")
        delete_button.setProperty("unique_id", unique_id)  # 绑定唯一标识符
        delete_button.clicked.connect(self.handle_delete_row)
        delete_button.setFixedWidth(50)
        layout.addWidget(delete_button)
        already_opened = self.get_cell_value(row, self.column_indices["已开仓"])
        if already_opened == "是" and setDisabled:  # 如果该列的值是 "True"，禁用按钮
            delete_button.setDisabled(True)
        self.setCellWidget(row, self.column_indices["操作"], container)

    def setRowProperty(self, row, key, value):
        """为行设置属性"""
        for col in range(self.columnCount()):
            item = self.item(row, col) or QTableWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole + 1, {key: value})
            self.setItem(row, col, item)

    def getRowProperty(self, row, key):
        """获取行的属性"""
        for col in range(self.columnCount()):
            item = self.item(row, col)
            if item:
                data = item.data(Qt.ItemDataRole.UserRole + 1)
                if data and key in data:
                    return data[key]
        return None

    def get_cell_value(self, row, col):
        """获取单元格的值"""
        widget = self.cellWidget(row, col)
        if widget:
            if isinstance(widget, QLineEdit):
                return widget.text()
            elif isinstance(widget, QWidget):  # 处理带有布局的控件容器
                line_edit = widget.findChild(QLineEdit)
                if line_edit:
                    return line_edit.text()
        item = self.item(row, col)
        return item.text() if item else ""

    def delete_row(self, row, setDisabled=False):
        """删除表格行"""
        # 只检查是否已开仓，已开仓的不能删除
        is_filled = self.get_cell_value(row, self.column_indices["已开仓"])
        if is_filled == "是" and setDisabled:
            print(f"[GridDialog] 行 {row} 已开仓，不能删除")
            QMessageBox.information(self, "警告！", f"[GridDialog] 行 {row} 已开仓，不能删除")
            return False

        if is_filled == "是":
            # 获取当前行的配置信息
            interval = self.get_cell_value(row, self.column_indices["间隔%"])
            filled_price = self.get_cell_value(row, self.column_indices["开仓价"])
            filled_amount = self.get_cell_value(row, self.column_indices["成交量"])
            
            # 弹窗确认
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
                print(f"[GridDialog] 用户取消删除已开仓的行 {row}")
                return False

        # 未开仓的可以随时删除
        print(f"[GridDialog] 删除行 {row}")
        self.removeRow(row)
        
        # 更新剩余行的删除按钮序号
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
        """设置表格单元格的内容和属性"""
        if editable:
            line_edit = QLineEdit(str(value))
            line_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if validator:
                line_edit.setValidator(validator)
            self.setCellWidget(row, col, line_edit)
        else:
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if col == 0:  # 修复第一列显示问题
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.setItem(row, col, item)

class GridDialog(QDialog):
    def __init__(self, grid_data):
        super().__init__()
        self.grid_data = grid_data
        
        self.setWindowTitle(f"设置网格策略 - {self.grid_data.pair}")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(1000)
        self.setMinimumHeight(500)
        self.setup_ui()
        self.load_grid_data()  # 加载已有的网格数据

    def setup_ui(self):
        """设置UI布局"""
        layout = QVBoxLayout()

        # === 网格表格 ===
        self.table = GridSetting()
        layout.addWidget(self.table)

        # === 输入框和按钮布局 ===
        input_layout = QHBoxLayout()
        self.budget_input = self.create_input_field("预算资金 (USDT)", QDoubleValidator(0.0, 9999999.99, 3))
        self.grid_layers_input = self.create_input_field("层数", QIntValidator(1, 1000))
        self.build_interval_input = self.create_input_field("间隔%", QDoubleValidator(0.0, 100.0, 3))
        self.take_profit_input = self.create_input_field("止盈%", QDoubleValidator(0.0, 100.0, 3))
        self.open_rebound_input = self.create_input_field("开仓反弹%", QDoubleValidator(0.0, 100.0, 3))
        self.close_rebound_input = self.create_input_field("平仓反弹%", QDoubleValidator(0.0, 100.0, 3))

        # 布局输入框
        input_layout.addWidget(QLabel("预算:"))
        input_layout.addWidget(self.budget_input)
        input_layout.addWidget(QLabel("层数:"))
        input_layout.addWidget(self.grid_layers_input)
        input_layout.addWidget(QLabel("间隔%:"))
        input_layout.addWidget(self.build_interval_input)
        input_layout.addWidget(QLabel("止盈%:"))
        input_layout.addWidget(self.take_profit_input)
        input_layout.addWidget(QLabel("开仓反弹%:"))
        input_layout.addWidget(self.open_rebound_input)
        input_layout.addWidget(QLabel("平仓反弹%:"))
        input_layout.addWidget(self.close_rebound_input)
        layout.addLayout(input_layout)

        # === 按钮布局 ===
        button_layout = QHBoxLayout()
        self.generate_grid_button = QPushButton("生成网格")
        self.generate_grid_button.clicked.connect(self.generate_grid)
        self.save_grid_button = QPushButton("保存设置")
        self.save_grid_button.clicked.connect(self.save_grid)
        button_layout.addWidget(self.generate_grid_button)
        button_layout.addWidget(self.save_grid_button)
        layout.addLayout(button_layout)

        # === 单独一行的 + 按钮 ===
        add_row_button_layout = QHBoxLayout()
        self.add_row_button = QPushButton("+")
        self.add_row_button.clicked.connect(lambda: self.table.add_row())
        add_row_button_layout.addWidget(self.add_row_button)
        layout.addLayout(add_row_button_layout)

        self.setLayout(layout)

    def create_input_field(self, placeholder_text, validator):
        """创建带有验证器的输入框"""
        input_field = QLineEdit()
        input_field.setPlaceholderText(placeholder_text)
        input_field.setValidator(validator)
        return input_field

    def validate_input(self, text, data_type, field_name, min_value=0):
        """验证输入值"""
        try:
            value = data_type(text)
            if value < min_value:
                raise ValueError(f"{field_name} 不能小于 {min_value}！")
            return value
        except ValueError:
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
                (self.open_rebound_input, "开仓反弹%"),  # 修改这里的变量名
                (self.close_rebound_input, "平仓反弹%"),  # 修改这里的变量名
            ]
            for field, name in required_fields:
                if not field.text().strip():
                    raise ValueError(f"{name} 不能为空！")

            # 验证字段
            budget = self.validate_input(self.budget_input.text(), float, "预算资金")
            layers = self.validate_input(self.grid_layers_input.text(), int, "层数", min_value=1)
            build_interval = self.validate_input(self.build_interval_input.text(), float, "间隔%")
            take_profit = self.validate_input(self.take_profit_input.text(), float, "止盈%")
            open_callback = self.validate_input(self.open_rebound_input.text(), float, "开仓反弹%")  # 修改这里的变量名
            close_callback = self.validate_input(self.close_rebound_input.text(), float, "平仓反弹%")  # 修改这里的变量名


            # 计算每格投入
            step = budget / layers
            # 清空表格重新生成
            self.table.clear_table()

            # 生成网格时也要使用新的字段名
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
                print(f"[GridDialog] 添加第 {i+1} 层配置")

        except ValueError as e:
            print(f"[GridDialog] 生成网格错误: {str(e)}")
            QMessageBox.critical(self, "错误", str(e))

    def load_grid_data(self):
        """加载网格数据到表格"""
        # print("[GridSetting] === 加载网格数据 ===")
        self.table.clear_table()
        for level, config in self.grid_data.grid_levels.items():
            self.table.add_row({
                "间隔%": str(config.interval_percent),
                "止盈%": str(config.take_profit_percent),
                "开仓反弹%": str(config.open_rebound_percent),  # 修改
                "平仓反弹%": str(config.close_rebound_percent),  # 修改
                "成交额": str(config.invest_amount),
                "成交量": str(config.filled_amount) if config.filled_amount else "",
                "开仓价": str(config.filled_price) if config.filled_price else "",
                "开仓时间": config.filled_time.strftime("%m-%d %H:%M") if config.filled_time else "",
                "已开仓": "是" if config.is_filled else "否",
            })
        #     print(f"[GridSetting] 加载第 {level} 层配置")
        print("[GridSetting] === 网格数据加载完成 ===")

    def save_grid(self):
        """保存网格设置并同步到后台数据结构"""
        # print("[GridSetting] === 保存网格设置 ===")
        valid_existing_rows = []  # 已开仓的行
        valid_new_rows = []      # 未开仓的有效行
        
        # 收集和验证行数据
        for row in range(self.table.rowCount()):
            # 获取该行数据
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
                # 验证未开仓行的必填参数
                required_fields = ["间隔%", "止盈%", "开仓反弹%", "平仓反弹%", "成交额"]
                if all(row_data.get(field) for field in required_fields):
                    valid_new_rows.append(row_data)
        ui_logger.debug(f"[GridSetting] 已开仓行数: {len(valid_existing_rows)} {valid_existing_rows}")
        ui_logger.debug(f"[GridSetting] 新增有效行数: {len(valid_new_rows)} {valid_new_rows}")

        # 如果删除了所有行（包括已开仓的），重置 GridData
        if len(valid_existing_rows) == 0 and len(valid_new_rows) == 0:
            # 重置 GridData 到完全初始状态
            self.grid_data.reset_to_initial()
            ui_logger.info("[GridSetting] 重置 GridData 到初始状态")
        else:
            # 保留已开仓的配置, 清除所有未开仓配置
            unfilled_levels = [
                level for level, config in self.grid_data.grid_levels.items()
                if not config.is_filled
            ]
            for level in unfilled_levels:
                del self.grid_data.grid_levels[level]
                print(f"[GridSetting] 删除旧的未开仓层级 {level}")

            # 添加新的未开仓配置
            max_level = max(self.grid_data.grid_levels.keys(), default=-1)
            next_level = max_level + 1
            
            for row_data in valid_new_rows:
                level_config = {
                    "间隔%": row_data["间隔%"],
                    "止盈%": row_data["止盈%"],
                    "开仓反弹%": row_data["开仓反弹%"],
                    "平仓反弹%": row_data["平仓反弹%"],
                    "成交额": row_data["成交额"]
                }
                # print(f"[GridSetting] 添加第 {next_level} 层配置")
                self.grid_data.update_level(next_level, level_config)
                next_level += 1

            # 重新加载表格显示
            self.table.setRowCount(0)
            for row_data in valid_existing_rows + valid_new_rows:
                self.table.add_row(row_data)

        # 更新网格状态
        grid_status = self.grid_data.get_grid_status()
        current_level = (f"{grid_status['filled_levels']}/{grid_status['total_levels']}"
                        if grid_status['is_configured'] else "0/0")
        print(f"[GridSetting] 更新状态 - 当前层数: {current_level}")
        print(f"[GridSetting] 网格状态: {grid_status}")
        
        # 更新显示数据
        self.grid_data.row_dict.update({
            "当前层数": current_level
        })
        # 发送数据更新信号
        self.grid_data.data_updated.emit(self.grid_data.uid)
        self.accept()