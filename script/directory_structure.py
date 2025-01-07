import os

def print_directory_structure(start_path='.', exclude_dirs=None):
    if exclude_dirs is None:
        exclude_dirs = []

    for root, dirs, files in os.walk(start_path):
        # 从dirs列表中排除要排除的目录
        dirs[:] = [d for d in dirs if d not in exclude_dirs]

        # 计算当前目录的层级深度，使用缩进格式化输出
        level = root.replace(start_path, '').count(os.sep)
        indent = ' ' * 4 * level
        print(f"{indent}|-- {os.path.basename(root)}/")
        
        # 打印文件
        sub_indent = ' ' * 4 * (level + 1)
        for file in files:
            print(f"{sub_indent}|-- {file}")

if __name__ == "__main__":
    # 获取用户输入的路径
    # directory_path = input("请输入要打印目录结构的路径: ").strip()
    directory_path = r"C:\Users\24369\Desktop\crypto_grid_system"
    exclude_folders = ['.git', 'build', '__pycache__']  # 要排除的文件夹列表

    if not directory_path:
        print("未输入路径，默认使用当前目录。")
        directory_path = '.'

    print(f"\n{directory_path} 的目录结构:")
    print_directory_structure(directory_path, exclude_folders)
