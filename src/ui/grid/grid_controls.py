# src/ui/components/grid_controls.py

from typing import Dict, Optional
from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, 
    QPushButton, QLabel, QMessageBox
)
from qtpy.QtCore import Qt, Signal, QRegularExpression
from qtpy.QtGui import QRegularExpressionValidator, QColor

class GridControls(QWidget):
    """网格策略控制组件"""
    
    # 信号定义
    pair_added = Signal(str, str)  # symbol, base_currency
    stop_all_requested = Signal()
    operation_toggled = Signal(str, bool)  # operation_type, enabled
    position_mode_changed = Signal(bool)  # is_long
    dialog_requested = Signal(str, str, str)

    def __init__(self, inst_type: str):
        super().__init__()
        self.inst_type = inst_type
        self.client = None
        self.setup_ui()

    def set_client(self, client):
        """设置交易所客户端"""
        self.client = client

    def setup_ui(self):
        """设置UI界面"""
        layout = QHBoxLayout(self)
        layout.setSpacing(5)

        # === 交易对输入区域 ===
        # 交易对输入
        layout.addWidget(QLabel("交易对:"))
        self.input_symbol = QLineEdit()
        self.input_symbol.setPlaceholderText("请输入交易对 (如BTC)")
        validator = QRegularExpressionValidator(QRegularExpression("^[A-Za-z0-9]*$"))
        self.input_symbol.setValidator(validator)
        layout.addWidget(self.input_symbol)

        # 基础货币
        layout.addWidget(QLabel("基础货币:"))
        self.input_base = QLineEdit("USDT")
        self.input_base.setValidator(validator)
        layout.addWidget(self.input_base)

        # 添加按钮
        add_button = QPushButton("添加交易对")
        add_button.clicked.connect(self._handle_add_pair)
        layout.addWidget(add_button)

        # === 多空切换按钮 ===
        self.position_mode_button = QPushButton("做多")
        self.position_mode_button.setCheckable(True)
        self.position_mode_button.setChecked(False)  # 默认做多
        self.position_mode_button.clicked.connect(self._handle_position_mode_changed)
        self.update_position_mode_button_style()
        layout.addWidget(self.position_mode_button)
        
        # 现货模式下隐藏多空切换按钮
        if self.inst_type == "SPOT":
            self.position_mode_button.hide()

        # === 批量操作按钮 ===
        stop_all_button = QPushButton("停止全部")
        stop_all_button.clicked.connect(self.stop_all_requested.emit)
        layout.addWidget(stop_all_button)

        # === 开平仓控制按钮 ===
        self.toggle_all_open_button = QPushButton("开仓开关")
        self.toggle_all_open_button.setCheckable(True)
        self.toggle_all_open_button.setChecked(True)
        self.toggle_all_open_button.clicked.connect(
            lambda: self._handle_operation_toggled("开仓")
        )
        layout.addWidget(self.toggle_all_open_button)

        self.toggle_all_close_button = QPushButton("平仓开关")
        self.toggle_all_close_button.setCheckable(True)
        self.toggle_all_close_button.setChecked(True)
        self.toggle_all_close_button.clicked.connect(
            lambda: self._handle_operation_toggled("平仓")
        )
        layout.addWidget(self.toggle_all_close_button)

        # 添加弹性空间
        layout.addStretch()

        self.setLayout(layout)

    def update_position_mode_button_style(self):
        """更新多空切换按钮样式"""
        is_short = self.position_mode_button.isChecked()
        self.position_mode_button.setText("做空" if is_short else "做多")
        
        if is_short:
            self.position_mode_button.setStyleSheet(
                "QPushButton { "
                "   background-color: #dc3545; "
                "   color: white; "
                "   border-radius: 4px; "
                "   padding: 5px; "
                "} "
                "QPushButton:hover { background-color: #c82333; }"
            )
        else:
            self.position_mode_button.setStyleSheet(
                "QPushButton { "
                "   background-color: #28a745; "
                "   color: white; "
                "   border-radius: 4px; "
                "   padding: 5px; "
                "} "
                "QPushButton:hover { background-color: #218838; }"
            )

    def _handle_position_mode_changed(self):
        """处理多空模式切换"""
        # 现货模式下禁止切换到做空
        if self.inst_type == "SPOT" and self.position_mode_button.isChecked():
            self.position_mode_button.setChecked(False)
            self.dialog_requested.emit("warning", "警告", "现货模式不支持做空")
            return
            
        # 更新按钮样式
        self.update_position_mode_button_style()
        
        # 发送信号通知模式变化
        self.position_mode_changed.emit(not self.position_mode_button.isChecked())

    def _handle_add_pair(self):
        """处理添加交易对请求"""
        symbol = self.input_symbol.text().strip().upper()
        base = self.input_base.text().strip().upper()
        
        if not symbol or not base:
            self.dialog_requested.emit("warning", "错误", "交易对和基础货币不能为空！")
            return

        if not self.client:
            self.dialog_requested.emit("warning", "错误", "交易所客户端未连接！")
            return
            
        pair = f"{symbol}/{base}"
        
        try:
            result = self.client.validate_pair(pair)
            if not result.get("valid", False):
                self.dialog_requested.emit("warning", "错误", 
                    result.get("error", "验证交易对失败"))
                return
                
            self.pair_added.emit(symbol, base)
            self.input_symbol.clear()
            
        except Exception as e:
            self.dialog_requested.emit("error", "错误", f"验证交易对失败: {str(e)}")
            return

    def _handle_operation_toggled(self, operation_type: str):
        """处理开平仓操作切换"""
        button = (self.toggle_all_open_button if operation_type == "开仓" 
                 else self.toggle_all_close_button)
        is_enabled = button.isChecked()
        
        # 发送操作状态变化信号
        self.operation_toggled.emit(operation_type, is_enabled)

    def get_position_mode(self) -> bool:
        """获取当前持仓模式 (True=做多,False=做空)"""
        return not self.position_mode_button.isChecked()

    def get_operation_states(self) -> Dict[str, bool]:
        """获取当前开平仓操作状态"""
        return {
            "开仓": self.toggle_all_open_button.isChecked(),
            "平仓": self.toggle_all_close_button.isChecked()
        }
        
    def set_operation_state(self, operation_type: str, enabled: bool):
        """设置指定操作状态"""
        if operation_type == "开仓":
            self.toggle_all_open_button.setChecked(enabled)
        elif operation_type == "平仓":
            self.toggle_all_close_button.setChecked(enabled)

    def set_all_operation_states(self, states: Dict[str, bool]):
        """批量设置操作状态"""
        for operation_type, enabled in states.items():
            self.set_operation_state(operation_type, enabled)

    def reset_position_mode(self):
        """重置为默认的做多模式"""
        if self.position_mode_button.isChecked():
            self.position_mode_button.setChecked(False)
            self.update_position_mode_button_style()
            self.position_mode_changed.emit(True)

    def disable_all_controls(self):
        """禁用所有控制"""
        self.input_symbol.setEnabled(False)
        self.input_base.setEnabled(False)
        self.position_mode_button.setEnabled(False)
        self.toggle_all_open_button.setEnabled(False)
        self.toggle_all_close_button.setEnabled(False)

    def enable_all_controls(self):
        """启用所有控制"""
        self.input_symbol.setEnabled(True)
        self.input_base.setEnabled(True)
        self.position_mode_button.setEnabled(True)
        self.toggle_all_open_button.setEnabled(True)
        self.toggle_all_close_button.setEnabled(True)