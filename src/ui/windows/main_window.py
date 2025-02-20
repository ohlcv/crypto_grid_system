import sys
import os
import traceback
from qtpy.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QTabWidget,
    QApplication, QMessageBox
)
from qtpy.QtCore import Qt
from qtpy.QtGui import QIcon
from src.exchange.base_client import ExchangeType
from src.ui.grid.grid_strategy_tab import GridStrategyTab
# from src.ui.tabs.grid_strategy_tab import GridStrategyTab
from src.exchange.client_factory import ExchangeClientFactory
from src.utils.common.common import resource_path
from src.ui.components.welcome_page import WelcomePage
from qt_material import apply_stylesheet
from qtpy.QtCore import QTimer

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("加密货币交易系统")
        self.resize(1250, 800)
        
        # 设置错误处理
        sys.excepthook = self.handle_exception
        
        # 创建工厂实例
        self.client_factory = ExchangeClientFactory()
        # 连接验证失败信号（只连接一次）
        self.client_factory.validation_failed.connect(
            lambda msg: QMessageBox.critical(self, "验证失败", msg)
        )
        
        # 初始化UI组件（但还不设置主题和图标）
        self.init_ui_components()
        
        # 设置主题（这可能会影响图标的显示）
        self.setup_theme()
        
        # 最后设置图标
        self.setup_icons()

    def init_ui_components(self):
        """初始化UI组件的基本结构"""
        # 创建中心部件和布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 创建主标签页
        self.main_tab_widget = QTabWidget()
        layout.addWidget(self.main_tab_widget)

        # 创建网格策略标签页
        grid_strategy_widget = QWidget()
        grid_strategy_layout = QVBoxLayout(grid_strategy_widget)
        
        # 创建网格策略子标签页
        self.grid_tab_widget = QTabWidget()
        grid_strategy_layout.addWidget(self.grid_tab_widget)
        
        # 添加现货网格标签页
        QTimer.singleShot(100, self.add_spot_tab)
        
        # 将网格策略页面添加到主标签页
        self.main_tab_widget.addTab(grid_strategy_widget, "网格策略")
        
        # 添加欢迎页面
        welcome_widget = WelcomePage()
        self.main_tab_widget.addTab(welcome_widget, "使用指南")
        
        # 延迟添加并连接合约网格标签页
        QTimer.singleShot(2000, self.add_futures_tab)

    def add_spot_tab(self):
        """添加现货网格标签页"""
        try:
            inst_type = ExchangeType.SPOT
            if self.client_factory.get_supported_exchanges(inst_type):
                self.spot_tab = GridStrategyTab("SPOT", self.client_factory)
                self.grid_tab_widget.addTab(self.spot_tab, "现货网格")
                print("✅ 现货网格标签页加载成功")
                # 立即连接现货
                self.spot_tab._auto_connect_exchange()
        except Exception as e:
            print(f"❌ 现货网格标签页加载失败: {str(e)}")

    def add_futures_tab(self):
        """延迟添加合约网格标签页"""
        try:
            self.futures_tab = GridStrategyTab("FUTURES", self.client_factory)
            self.grid_tab_widget.addTab(self.futures_tab, "合约网格")
            print("✅ 合约网格标签页加载成功")
            # 添加完立即自动连接
            self.futures_tab._auto_connect_exchange()
        except Exception as e:
            print(f"❌ 合约网格标签页加载失败: {str(e)}")

    def setup_theme(self):
        """设置应用程序主题"""
        try:
            extra = {
                'danger': '#dc3545',
                'warning': '#ffc107',
                'success': '#17a2b8',
                'font_family': 'Roboto',
                'density_scale': '0'
            }
            apply_stylesheet(QApplication.instance(), theme='light_cyan.xml', extra=extra)
            print("✅ qt-material 主题加载成功")
        except Exception as e:
            print(f"❌ qt-material 主题加载失败: {str(e)}")

    def setup_icons(self):
        """设置应用程序图标"""
        try:
            # 确保main_tab_widget已经创建
            if not hasattr(self, 'main_tab_widget'):
                print("⚠️ 警告: main_tab_widget尚未初始化")
                return
                
            # 设置窗口图标
            window_icon_path = resource_path(os.path.join('src', 'ui', 'icons', 'bitcoin.ico'))
            if window_icon_path and os.path.exists(window_icon_path):
                window_icon = QIcon(window_icon_path)
                self.setWindowIcon(window_icon)
                QApplication.instance().setWindowIcon(window_icon)
                # print(f"✅ 主窗口图标加载成功: {window_icon_path}")
            
            # 设置标签页图标
            svg_icon_path = resource_path(os.path.join('src', 'ui', 'icons', 'dogecoin256.svg'))
            if svg_icon_path and os.path.exists(svg_icon_path):
                tab_icon = QIcon(svg_icon_path)
                # 为所有标签页设置图标
                for i in range(self.main_tab_widget.count()):
                    self.main_tab_widget.setTabIcon(i, tab_icon)
                # print(f"✅ 标签栏图标加载成功: {svg_icon_path}")
                
        except Exception as e:
            print(f"❌ 图标加载失败: {str(e)}\n{traceback.format_exc()}")

    def handle_exception(self, exc_type, exc_value, exc_traceback):
        """处理未捕获的异常"""
        print("Uncaught exception:", exc_type, exc_value)
        import traceback
        traceback.print_exception(exc_type, exc_value, exc_traceback)
        
        # 使用自定义图标显示错误对话框
        QMessageBox.critical(
            self,
            "Error",
            f"发生未处理的异常:\n{exc_type.__name__}: {str(exc_value)}"
        )

    def closeEvent(self, event):
        """窗口关闭事件的处理"""
        reply = QMessageBox.question(
            self,
            '确认退出',
            '你确定要退出程序吗?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 关闭所有标签页
            for i in range(self.grid_tab_widget.count()):
                tab = self.grid_tab_widget.widget(i)
                if hasattr(tab, 'closeEvent'):
                    tab.closeEvent(event)
            event.accept()
        else:
            event.ignore()

def main():
    app = QApplication(sys.argv)
    
    # 创建必要的目录
    os.makedirs('./data', exist_ok=True)
    os.makedirs('./config/api_config', exist_ok=True)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
