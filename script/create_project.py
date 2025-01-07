import os
import sys
from typing import List, Dict

PROJECT_STRUCTURE = {
    "src": {
        "config": {
            "api_config": {},  # 存放API配置文件
        },
        "core": {
            "engine": {},      # 策略引擎
            "risk": {},        # 风险管理
        },
        "exchange": {
            "base": {},        # 交易所基类
            "bitget": {
                "rest": {},    # REST API
                "ws": {},      # WebSocket
            },
        },
        "strategy": {
            "grid": {},        # 网格策略
            "base": {},        # 策略基类
        },
        "ui": {
            "components": {},  # UI组件
            "dialogs": {},     # 对话框
            "tabs": {},        # 标签页
            "windows": {},     # 窗口
        },
        "utils": {
            "logger": {},      # 日志
            "common": {},      # 通用工具
        },
    },
    "tests": {                 # 测试目录
        "unit": {},
        "integration": {},
    },
    "docs": {},               # 文档
    "logs": {},               # 日志文件
    "data": {                 # 数据存储
        "grid_data": {},
    },
}

# 需要创建的空文件
INIT_FILES = [
    "src/__init__.py",
    "src/config/__init__.py",
    "src/core/__init__.py",
    "src/core/engine/__init__.py",
    "src/core/engine/strategy_engine.py",
    "src/core/risk/__init__.py",
    "src/core/risk/risk_manager.py",
    "src/exchange/__init__.py",
    "src/exchange/base/__init__.py",
    "src/exchange/base/base_client.py",
    "src/exchange/base/base_ws.py",
    "src/exchange/bitget/__init__.py",
    "src/exchange/bitget/rest/__init__.py",
    "src/exchange/bitget/ws/__init__.py",
    "src/strategy/__init__.py",
    "src/strategy/base/__init__.py",
    "src/strategy/base/base_strategy.py",
    "src/strategy/grid/__init__.py",
    "src/strategy/grid/grid_strategy.py",
    "src/ui/__init__.py",
    "src/ui/components/__init__.py",
    "src/ui/components/grid_table.py",
    "src/ui/dialogs/__init__.py",
    "src/ui/dialogs/grid_settings.py",
    "src/ui/tabs/__init__.py",
    "src/ui/tabs/api_tab.py",
    "src/ui/tabs/strategy_tab.py",
    "src/ui/windows/__init__.py",
    "src/ui/windows/main_window.py",
    "src/utils/__init__.py",
    "src/utils/logger/__init__.py",
    "src/utils/logger/log_handler.py",
    "src/utils/common/__init__.py",
    "src/utils/common/tools.py",
    "src/main.py",
    "tests/__init__.py",
    "tests/unit/__init__.py",
    "tests/integration/__init__.py",
    "requirements.txt",
    "README.md",
]

def create_directory_structure(base_path: str, structure: Dict, current_path: str = ""):
    """递归创建目录结构"""
    for name, contents in structure.items():
        path = os.path.join(base_path, current_path, name)
        try:
            if not os.path.exists(path):
                os.makedirs(path)
                print(f"Created directory: {path}")
            if isinstance(contents, dict):
                create_directory_structure(base_path, contents, os.path.join(current_path, name))
        except Exception as e:
            print(f"Error creating directory {path}: {e}")

def create_files(base_path: str, file_list: List[str]):
    """创建初始文件"""
    for file_path in file_list:
        full_path = os.path.join(base_path, file_path)
        try:
            # 确保文件所在目录存在
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            # 创建文件
            if not os.path.exists(full_path):
                with open(full_path, 'w', encoding='utf-8') as f:
                    if file_path.endswith('.py'):
                        # 添加基本的文件头注释
                        f.write('#!/usr/bin/env python\n')
                        f.write('# -*- coding: utf-8 -*-\n\n')
                print(f"Created file: {full_path}")
            
        except Exception as e:
            print(f"Error creating file {full_path}: {e}")

def create_readme(base_path: str):
    """创建README文件"""
    readme_path = os.path.join(base_path, 'README.md')
    try:
        if not os.path.exists(readme_path):
            with open(readme_path, 'w', encoding='utf-8') as f:
                f.write('# Crypto Grid Trading System\n\n')
                f.write('A cryptocurrency grid trading system built with qtpy.\n\n')
                f.write('## Project Structure\n\n')
                f.write('```\n')
                # 添加项目结构树
                for line in generate_tree_structure(PROJECT_STRUCTURE):
                    f.write(line + '\n')
                f.write('```\n')
            print(f"Created README: {readme_path}")
    except Exception as e:
        print(f"Error creating README {readme_path}: {e}")

def generate_tree_structure(structure: Dict, prefix: str = '', is_last: bool = True) -> List[str]:
    """生成树形结构字符串"""
    lines = []
    items = list(structure.items())
    for i, (name, contents) in enumerate(items):
        is_last_item = i == len(items) - 1
        lines.append(f"{prefix}{'└── ' if is_last_item else '├── '}{name}")
        if isinstance(contents, dict):
            extension = '    ' if is_last_item else '│   '
            lines.extend(generate_tree_structure(contents, prefix + extension, is_last_item))
    return lines

def main():
    # 获取当前目录作为基础路径
    base_path = os.getcwd()
    project_name = 'grid_trading'
    project_path = os.path.join(base_path, project_name)

    print(f"Creating project structure in: {project_path}")

    try:
        # 创建项目根目录
        if not os.path.exists(project_path):
            os.makedirs(project_path)
            print(f"Created project directory: {project_path}")

        # 创建目录结构
        create_directory_structure(project_path, PROJECT_STRUCTURE)

        # 创建初始文件
        create_files(project_path, INIT_FILES)

        # 创建README
        create_readme(project_path)

        print("\nProject structure created successfully!")
        
    except Exception as e:
        print(f"Error creating project structure: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()