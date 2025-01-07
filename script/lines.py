import os

def count_lines_in_project(directory, extensions):
    total_lines = 0
    for root, dirs, files in os.walk(directory):
        for file in files:
            if any(file.endswith(ext) for ext in extensions):
                file_path = os.path.join(root, file)
                with open(file_path, 'r', encoding='utf-8') as f:
                    total_lines += sum(1 for line in f)
    return total_lines

# 统计当前目录及其子目录下所有 .py 和 .js 文件的行数
lines = count_lines_in_project('.', ['.py', '.js'])
print(f"Total lines: {lines}")
