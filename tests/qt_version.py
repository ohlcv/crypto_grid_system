from qtpy.QtCore import QT_VERSION_STR
print("Qt Version:", QT_VERSION_STR)

from qtpy.QtCore import QLocale

locale = QLocale.system()  # 获取系统默认的语言环境
print(f"系统语言: {locale.name()}")  # 输出系统语言
