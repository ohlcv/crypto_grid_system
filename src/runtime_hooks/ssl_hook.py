# -*- coding: utf-8 -*-
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
