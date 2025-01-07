import os
import json


class APIConfigLoader:
    """配置加载器，负责加载和校验 API 配置文件"""

    @staticmethod
    def load_config(config_path: str) -> dict:
        """加载配置文件"""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件未找到: {config_path}，请创建 config.json 文件，并添加必要的 API Key 和密钥。")

        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                config = json.load(file)
        except json.JSONDecodeError as e:
            raise ValueError(f"配置文件 {config_path} 解析失败，请检查 JSON 格式是否正确。错误信息: {e}")

        required_fields = ['user_id', 'api_key', 'api_secret', 'passphrase']
        if 'bitget' not in config:
            raise KeyError(f"配置文件中缺少 'bitget' 键，请确保文件内容符合以下格式: {required_fields}")

        for field in required_fields:
            if field not in config['bitget']:
                raise KeyError(f"配置文件中缺少 '{field}' 字段，请在 bitget 部分中添加此字段。")

        return config['bitget']
