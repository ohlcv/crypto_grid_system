"""
目录结构分析工具 - 最终修正版
修复输出错误并完整显示代码统计信息
"""

import os
import fnmatch
import json
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

# ================== 配置区域 ==================
CONFIG = {
    "target_path": r"C:\Users\24369\Desktop\crypto_grid_system",
    "output_format": "text",  # text/markdown/json
    "exclude_dirs": [
        '__pycache__', '.git', '.vscode',
        '.idea', 'venv', 'node_modules',
        'logs', 'dist', 'build'
    ],
    "exclude_files": [
        '*.pyc', '*.pyo', '*.log', '*.json',
        '*.tmp', '*.bak', '*.zip', '*.7z',
        'Thumbs.db', '.DS_Store', '.gitignore'
    ],
    "include_patterns": ['*.py'],
    "enable_code_stats": True,
    "show_hidden": False,
    "max_workers": 4
}
# ================== 配置结束 ====================

CODE_CONFIG = {
    '.py': {'single_comment': '#', 'multi_comment': ('"""', '"""')},
    '.js': {'single_comment': '//', 'multi_comment': ('/*', '*/')},
    '.java': {'single_comment': '//', 'multi_comment': ('/*', '*/')},
    '.cpp': {'single_comment': '//', 'multi_comment': ('/*', '*/')},
    '.go': {'single_comment': '//', 'multi_comment': ('/*', '*/')}
}

@dataclass
class FileStats:
    total_lines: int = 0
    code_lines: int = 0
    comment_lines: int = 0
    blank_lines: int = 0
    complexity: int = 0

class DirectoryScanner:
    def __init__(self, config: Dict):
        self.config = config
        self.root_path = Path(config["target_path"]).resolve()

    def _is_excluded(self, name: str, patterns: List[str]) -> bool:
        return any(fnmatch.fnmatch(name, p) for p in patterns)

    def _should_include(self, name: str) -> bool:
        if not self.config["include_patterns"]:
            return True
        return any(fnmatch.fnmatch(name, p) for p in self.config["include_patterns"])

    def scan(self) -> Dict:
        result = {
            "structure": [],
            "stats": {},
            "total": {
                "files": 0,
                "total_lines": 0,
                "code_lines": 0,
                "comment_lines": 0,
                "blank_lines": 0,
                "complexity": 0
            }
        }

        for root, dirs, files in os.walk(self.root_path, topdown=True):
            dirs[:] = [d for d in dirs if not self._should_exclude_dir(d)]
            current_dir = self._create_dir_entry(Path(root).relative_to(self.root_path))
            
            with ThreadPoolExecutor(max_workers=self.config["max_workers"]) as executor:
                futures = []
                for f in files:
                    if self._should_process_file(f):
                        futures.append(executor.submit(self._analyze_file, Path(root) / f))

                for future in as_completed(futures):
                    file_entry, stats = future.result()
                    if file_entry:
                        current_dir["children"].append(file_entry)
                        result["stats"][file_entry["path"]] = stats.__dict__
                        self._update_total_stats(result["total"], stats)

            result["structure"].append(current_dir)
        return result

    def _should_exclude_dir(self, dir_name: str) -> bool:
        if not self.config["show_hidden"] and dir_name.startswith('.'):
            return True
        return self._is_excluded(dir_name, self.config["exclude_dirs"])

    def _should_process_file(self, file_name: str) -> bool:
        if not self.config["show_hidden"] and file_name.startswith('.'):
            return False
        if self._is_excluded(file_name, self.config["exclude_files"]):
            return False
        return self._should_include(file_name)

    def _create_dir_entry(self, rel_path: Path) -> Dict:
        return {
            "path": str(rel_path),
            "name": rel_path.name if rel_path != Path('.') else self.root_path.name,
            "type": "directory",
            "children": []
        }

    def _analyze_file(self, file_path: Path) -> tuple:
        try:
            rel_path = str(file_path.relative_to(self.root_path))
            stats = FileStats()
            
            if self.config["enable_code_stats"] and file_path.suffix in CODE_CONFIG:
                stats = CodeAnalyzer(file_path).analyze()

            return ({
                "path": rel_path,
                "name": file_path.name,
                "type": "file",
                "size": file_path.stat().st_size
            }, stats)
        except Exception as e:
            return None, None

    def _update_total_stats(self, total: Dict, stats: FileStats):
        total["files"] += 1
        total["total_lines"] += stats.total_lines
        total["code_lines"] += stats.code_lines
        total["comment_lines"] += stats.comment_lines
        total["blank_lines"] += stats.blank_lines
        total["complexity"] += stats.complexity

class CodeAnalyzer:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.config = CODE_CONFIG.get(file_path.suffix, {})
        self.in_comment_block = False

    def analyze(self) -> FileStats:
        stats = FileStats()
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.rstrip('\n')
                    stats.total_lines += 1
                    
                    if not line.strip():
                        stats.blank_lines += 1
                        continue
                        
                    if self._is_comment(line):
                        stats.comment_lines += 1
                    else:
                        stats.code_lines += 1
                        stats.complexity += self._calc_complexity(line)
        except UnicodeDecodeError:
            pass
        except Exception as e:
            print(f"分析文件错误: {self.file_path} - {str(e)}")
        return stats

    def _is_comment(self, line: str) -> bool:
        line = line.strip()
        if self.in_comment_block:
            if self.config.get('multi_comment') and self.config['multi_comment'][1] in line:
                self.in_comment_block = False
            return True
        
        if self.config.get('single_comment') and line.startswith(self.config['single_comment']):
            return True
            
        if self.config.get('multi_comment') and line.startswith(self.config['multi_comment'][0]):
            self.in_comment_block = True
            return True
            
        return False

    def _calc_complexity(self, line: str) -> int:
        keywords = ['if', 'elif', 'else', 'for', 'while', 
                   'and', 'or', 'case', 'catch', 'except',
                   'try', '??', '?', '=>', 'match', 'with']
        return sum(1 for kw in keywords if kw in line)

class OutputFormatter:
    @staticmethod
    def format(result: Dict, config: Dict) -> str:
        formatters = {
            "text": OutputFormatter._text_format,
            "markdown": OutputFormatter._markdown_format,
            "json": OutputFormatter._json_format
        }
        return formatters[config["output_format"]](result)

    @staticmethod
    def _text_format(result: Dict) -> str:
        output = []
        for entry in result["structure"]:
            OutputFormatter._format_entry(entry, result, output, 0)
        
        output.append("\n=== 代码统计汇总 ===")
        output.append(f"总文件数: {result['total']['files']}")
        output.append(f"总代码行: {result['total']['code_lines']}")
        output.append(f"总注释行: {result['total']['comment_lines']}")
        output.append(f"总空行数: {result['total']['blank_lines']}")
        output.append(f"总复杂度: {result['total']['complexity']}")
        return '\n'.join(output)

    @staticmethod
    def _format_entry(entry: Dict, result: Dict, output: List, level: int):
        indent = '    ' * level
        prefix = f"{indent}|-- "
        
        if entry["type"] == "directory":
            output.append(f"{prefix}{entry['name']}/")
            for child in entry.get("children", []):
                OutputFormatter._format_entry(child, result, output, level + 1)
        else:
            file_info = OutputFormatter._file_info(entry, result)
            output.append(f"{prefix}{entry['name']} {file_info}")

    @staticmethod
    def _file_info(entry: Dict, result: Dict) -> str:
        stats = result["stats"].get(entry["path"], {})
        info = []
        
        if stats.get("total_lines", 0) > 0:
            info.extend([
                f"总行: {stats['total_lines']}",
                f"代码: {stats['code_lines']}",
                f"注释: {stats['comment_lines']}",
                f"空行: {stats['blank_lines']}",
                f"复杂度: {stats['complexity']}"
            ])
        
        if entry.get("size"):
            info.append(f"大小: {OutputFormatter._format_size(entry['size'])}")
        
        return f"({', '.join(info)})" if info else ""

    @staticmethod
    def _format_size(size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f}{unit}"
            size /= 1024.0
        return f"{size:.1f}TB"

    @staticmethod
    def _markdown_format(result: Dict) -> str:
        text = OutputFormatter._text_format(result)
        return f"```\n{text}\n```"

    @staticmethod
    def _json_format(result: Dict) -> str:
        return json.dumps(result, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    try:
        scanner = DirectoryScanner(CONFIG)
        scan_result = scanner.scan()
        print(OutputFormatter.format(scan_result, CONFIG))
    except KeyboardInterrupt:
        print("\n操作已取消")
    except Exception as e:
        print(f"发生错误: {str(e)}")