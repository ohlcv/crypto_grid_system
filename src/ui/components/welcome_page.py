from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QLabel
)
from qtpy.QtCore import Qt
from qtpy.QtGui import QFont

class WelcomePage(QWidget):
    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        # 创建主布局
        layout = QVBoxLayout(self)
        
        # 创建滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)
        
        # 创建内容容器
        content = QWidget()
        content_layout = QVBoxLayout(content)
        scroll.setWidget(content)
        
        # 标题样式
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        
        # 子标题样式
        subtitle_font = QFont()
        subtitle_font.setPointSize(12)
        subtitle_font.setBold(True)
        
        # 添加标题
        title = QLabel("网格交易策略系统 - 功能特点与使用指南")
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(title)
        
        # 主要特点
        content_layout.addWidget(self._create_section(
            "核心优势",
            [
                "• <b>灵活的参数调整：</b>所有网格参数（间隔、止盈、反弹等）均可随时修改，不受已开仓位置限制，真正实现动态调整", 
                "• <b>智能的网格间隔：</b>根据市场波动和价格区间自动调整网格间隔，避免死板的等比或等差间隔",
                "• <b>动态的开仓策略：</b>通过反弹参数智能控制开仓时机，避免追跌，提高开仓质量",
                "• <b>灵活的资金管理：</b>支持同时运行多个交易对的网格策略，实现资金分散，降低单一币种风险",
                "• <b>多维度的风控：</b>支持单网格止盈、总体止盈止损、持仓时间控制等多重风控手段",
                "• <b>实时的状态监控：</b>全面展示策略运行状态、持仓信息、盈亏数据等关键指标"
            ],
            subtitle_font
        ))
        
        # 使用步骤
        content_layout.addWidget(self._create_section(
            "使用步骤",
            [
                "1. <b>API配置</b>",
                "   - 填写交易所API信息并测试连接",
                "   - 确保WebSocket连接状态正常",
                "",
                "2. <b>添加交易对</b>",
                "   - 选择要交易的币种",
                "   - 选择做多或做空方向（合约）",
                "",
                "3. <b>设置网格参数</b>",
                "   - 配置总投资金额和网格层数",
                "   - 设置网格间隔和止盈比例",
                "   - 配置开仓和平仓反弹参数",
                "   - 设置总体止盈止损（可选）",
                "",
                "4. <b>策略运行与管理</b>",
                "   - 启动策略开始自动交易",
                "   - 随时查看运行状态和盈亏",
                "   - 根据市场灵活调整参数"
            ],
            subtitle_font
        ))
        
        # 参数说明
        content_layout.addWidget(self._create_section(
            "参数说明与建议",
            [
                "<b>1. 网格基础参数</b>",
                "   • 预算金额：建议根据总资金合理分配，避免单一策略占比过大",
                "   • 网格层数：结合预算和间隔确定，通常5-20层较为合适",
                "   • 间隔百分比：根据币种波动特性设置，可随时调整以适应行情",
                "   • 止盈百分比：建议设置在间隔的0.6-1倍之间",
                "",
                "<b>2. 反弹参数（特色功能）</b>",
                "   • 开仓反弹%：下跌触发价格后的反弹幅度要求，避免追跌",
                "   • 平仓反弹%：达到止盈价格后的回调幅度要求，避免追高",
                "   • 这两个参数是本系统的特色功能，可以显著提高交易质量",
                "",
                "<b>3. 总体止盈止损</b>",
                "   • 总体止盈：建议设置在投资金额的30%-50%",
                "   • 总体止损：建议设置在投资金额的10%-20%",
                "   • 这是重要的风控手段，建议始终开启"
            ],
            subtitle_font
        ))
        
        # 策略优化建议
        content_layout.addWidget(self._create_section(
            "策略优化建议",
            [
                "<b>1. 资金分散管理</b>",
                "   • 将资金分散到3-5个不同币种",
                "   • 选择相关性较低的币种组合",
                "   • 单个币种投资额不超过总资金的30%",
                "",
                "<b>2. 动态参数调整</b>",
                "   • 根据行情变化随时调整网格间隔",
                "   • 在趋势和震荡行情下使用不同参数组合",
                "   • 可以在同一币种设置多个不同参数的网格",
                "",
                "<b>3. 风险控制</b>",
                "   • 善用止盈止损功能",
                "   • 定期检查并平衡仓位",
                "   • 在重要行情前主动调整参数或暂停策略"
            ],
            subtitle_font
        ))
        
        # 常见问题
        content_layout.addWidget(self._create_section(
            "常见问题",
            [
                "<b>Q: 为什么要进行动态调整？</b>",
                "A: 加密货币市场波动剧烈，固定参数难以适应所有市况。本系统支持随时调整参数，可以根据市场变化优化策略表现。",
                "",
                "<b>Q: 如何判断参数是否合适？</b>",
                "A: 可以观察以下指标：",
                "   • 开仓频率是否合理",
                "   • 单笔交易盈亏比例",
                "   • 策略整体胜率",
                "   • 资金利用率",
                "",
                "<b>Q: 为什么要使用反弹参数？</b>",
                "A: 反弹参数可以：",
                "   • 避免在单边行情中频繁开仓",
                "   • 提高开仓和平仓价格",
                "   • 降低追涨杀跌风险",
                "",
                "<b>Q: 如何降低风险？</b>",
                "A: 建议采用以下策略：",
                "   • 资金分散到多个币种",
                "   • 设置合适的止损",
                "   • 定期检查并调整参数",
                "   • 关注市场重要变化"
            ],
            subtitle_font
        ))
        
        # 添加底部说明
        note = QLabel("注意：本系统仅供学习研究使用，请谨慎使用并注意控制风险。")
        note.setStyleSheet("color: red;")
        content_layout.addWidget(note)
        
        # 添加弹性空间
        content_layout.addStretch()

    def _create_section(self, title, items, font):
        """创建段落"""
        section = QWidget()
        layout = QVBoxLayout(section)
        
        # 添加标题
        title_label = QLabel(title)
        title_label.setFont(font)
        layout.addWidget(title_label)
        
        # 添加内容
        for item in items:
            label = QLabel(item)
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setWordWrap(True)
            layout.addWidget(label)
        
        layout.addSpacing(20)  # 添加段落间距
        return section