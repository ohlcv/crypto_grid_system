import os


def get_project_root():
    """获取项目根目录"""
    return os.path.dirname(os.path.abspath(__file__))

project_root = get_project_root()

src_path = os.path.join(project_root, "src")
if os.path.exists(src_path):
    add_data_icons = f'--add-data={src_path.replace(os.sep, "/")}/ui/icons/;ui/icons/'
else:
    print(f"GUI 资源目录不存在: {src_path}")
    add_data_icons = None

print("src_path", src_path)
print("add_data_icons", add_data_icons)
