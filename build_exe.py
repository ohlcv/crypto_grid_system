import os
import sys
import logging
import shutil
from venv import logger
import PyInstaller.__main__
import time
import toml
import certifi
from pathlib import Path

def load_project_config():
    """从pyproject.toml加载项目配置"""
    try:
        with open('pyproject.toml', 'r', encoding='utf-8') as f:
            return toml.load(f)
    except Exception as e:
        print(f"无法加载pyproject.toml: {e}")
        return None

def setup_logging():
    """配置日志系统，确保同时输出到文件和控制台
    
    这个函数创建一个日志记录器，它会：
    1. 将日志写入到带时间戳的文件中
    2. 同时在控制台显示日志
    3. 使用 UTF-8 编码确保正确处理所有字符
    """
    # 创建日志目录
    log_dir = Path("build/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建带时间戳的日志文件名
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    log_file = log_dir / f"build_{timestamp}.log"
    
    # 创建格式化器
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 创建文件处理器
    file_handler = logging.FileHandler(
        log_file,
        mode='w',  # 使用写入模式，每次都创建新文件
        encoding='utf-8'  # 明确指定 UTF-8 编码
    )
    file_handler.setFormatter(formatter)
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # 配置根日志记录器
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)  # 设置为最详细的日志级别
    
    # 清除现有的处理器（如果有的话）
    logger.handlers.clear()
    
    # 添加两个处理器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # 记录初始化信息
    logger.info("日志系统初始化完成")
    logger.info(f"日志文件位置: {log_file}")
    
    return logger

def create_runtime_hooks():
    """创建运行时钩子，使用二进制模式确保编码正确
    
    这个函数使用二进制模式写入文件，可以避免编码问题。同时，我们对文件内容
    进行预处理，确保它是标准的UTF-8格式。
    """
    hooks_dir = Path("src/runtime_hooks")
    hooks_dir.mkdir(parents=True, exist_ok=True)
    
    # 删除可能存在的旧文件
    ssl_hook = hooks_dir / "ssl_hook.py"
    if ssl_hook.exists():
        ssl_hook.unlink()
    
    # 准备钩子文件内容
    hook_content = '''# -*- coding: utf-8 -*-
import os
import sys
import ssl
import certifi

def configure_ssl():
    """配置SSL证书路径"""
    try:
        if getattr(sys, 'frozen', False):
            # 运行在打包环境中
            base_dir = sys._MEIPASS
            cert_path = os.path.join(base_dir, 'certifi', 'cacert.pem')
            
            if os.path.exists(cert_path):
                os.environ['SSL_CERT_FILE'] = cert_path
                os.environ['REQUESTS_CA_BUNDLE'] = cert_path
                os.environ['WEBSOCKET_CLIENT_CA_BUNDLE'] = cert_path
                ssl._create_default_https_context = ssl._create_unverified_context
                print(f"SSL证书配置成功: {cert_path}")
            else:
                print(f"警告: 未找到SSL证书文件: {cert_path}")
    except Exception as e:
        print(f"SSL证书配置失败: {str(e)}")

configure_ssl()
'''
    
    try:
        # 使用二进制模式写入文件，确保编码正确
        ssl_hook.write_bytes(hook_content.encode('utf-8-sig'))
        logger.info(f"成功创建运行时钩子: {ssl_hook}")
        
        # 验证文件是否可以正确读取
        with open(ssl_hook, 'r', encoding='utf-8') as f:
            f.read()  # 尝试读取文件，如果有编码问题会立即抛出异常
            
        return str(ssl_hook)
    except Exception as e:
        logger.error(f"创建运行时钩子失败: {str(e)}")
        return None


def build_exe():
    """执行打包过程，包含更智能的文件清理机制"""
    # 在创建日志之前清理旧的构建文件
    build_dir = Path("build")
    if build_dir.exists():
        try:
            # 仅清理特定的子目录，保留logs目录
            for item in build_dir.iterdir():
                if item.name != 'logs' and item.is_dir():
                    shutil.rmtree(item)
                elif item.name != 'logs' and item.is_file():
                    item.unlink()
        except Exception as e:
            print(f"清理旧文件时出错: {str(e)}")
    
    # 设置日志系统
    logger = setup_logging()
    logger.info("开始打包过程...")
    
    # 创建钩子文件
    hook_file = create_runtime_hooks()
    if not hook_file:
        logger.error("创建运行时钩子失败，终止打包过程")
        return
    
    # 验证钩子文件
    try:
        with open(hook_file, 'r', encoding='utf-8') as f:
            logger.info("验证运行时钩子文件编码...")
            f.read()
    except Exception as e:
        logger.error(f"运行时钩子文件验证失败: {str(e)}")
        return

    # 配置PyInstaller参数
    pyinstaller_args = [
        'main.py',
        f'--name=crypto-grid-trading',
        '--onedir',
        '--windowed',
        '--noconfirm',
        '--clean',
        f'--distpath={build_dir / "dist"}',
        f'--workpath={build_dir / "work"}',
        f'--specpath={build_dir / "spec"}',
    ]
    
    # 获取项目根目录
    project_root = Path.cwd()
    
    # 添加图标
    icon_file = project_root / 'src' / 'ui' / 'icons' / 'bitcoin.ico'
    if icon_file.exists():
        pyinstaller_args.append(f'--icon={icon_file}')
        logger.info(f"添加图标: {icon_file}")
    
    # 添加资源文件
    cert_file = Path(certifi.where())
    icons_dir = project_root / 'src' / 'ui' / 'icons'
    
    datas = [
        (str(cert_file), 'certifi'),
        (str(icons_dir), os.path.join('src', 'ui', 'icons')),
    ]
    
    for src, dst in datas:
        if os.path.exists(src):
            pyinstaller_args.append(f'--add-data={src}{os.pathsep}{dst}')
            logger.info(f"添加资源: {src} -> {dst}")
    
    # 添加运行时钩子
    if hook_file:
        pyinstaller_args.append(f'--runtime-hook={hook_file}')
        logger.info(f"添加运行时钩子: {hook_file}")
    
    # 添加必要的隐藏导入
    hidden_imports = [
        'websocket', 'websocket._app', 'websocket._core',
        'websocket._exceptions', 'websocket._handshake',
        'websocket._http', 'websocket._logging',
        'websocket._socket', 'websocket._utils',
        'websocket._url', 'qtpy', 'shiboken6',
        'qt_material', 'numpy', 'pandas', 'certifi',
    ]
    
    for imp in hidden_imports:
        pyinstaller_args.append(f'--hidden-import={imp}')
    
    # 执行打包
    try:
        logger.info("开始PyInstaller打包...")
        logger.info("PyInstaller参数:")
        logger.info(' '.join(pyinstaller_args))
        
        PyInstaller.__main__.run(pyinstaller_args)
        
        logger.info("打包完成！")
        
        # 验证打包结果
        dist_path = build_dir / 'dist' / 'crypto-grid-trading'/ '_internal' 
        if dist_path.exists():
            logger.info(f"打包成功: {dist_path}")
            
            # 验证关键文件
            cert_path = dist_path / 'certifi' / 'cacert.pem'
            icons_path = dist_path / 'src' / 'ui' / 'icons'
            
            if cert_path.exists():
                logger.info(f"SSL证书文件已包含: {cert_path}")
            else:
                logger.warning(f"警告: 未找到SSL证书文件: {cert_path}")
            
            if icons_path.exists():
                logger.info(f"图标文件已包含: {icons_path}")
            else:
                logger.warning(f"警告: 未找到图标文件夹: {icons_path}")
        else:
            logger.error(f"打包后的目录不存在: {dist_path}")
            
    except Exception as e:
        logger.exception("打包过程中出错:")
        raise

if __name__ == '__main__':
    build_exe()