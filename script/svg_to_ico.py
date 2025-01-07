from PIL import Image
import cairosvg
import os

# 输入 SVG 文件路径
svg_path = r"C:\Users\24369\Desktop\crypto_grid_system\src\ui\icons\dogecoin256.svg"
# 输出 ICO 文件路径
ico_path = r"C:\Users\24369\Desktop\crypto_grid_system\src\ui\icons\dogecoin256.ico"

# 定义需要的图标尺寸
sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256), (512, 512)]

# 创建高分辨率 PNG 文件
try:
    # 高分辨率 PNG 路径
    png_path = svg_path.replace(".svg", "_highres.png")

    # 将 SVG 转换为 1024x1024 的高分辨率 PNG
    cairosvg.svg2png(url=svg_path, write_to=png_path, output_width=1024, output_height=1024)
    print(f"Generated high-resolution PNG: {png_path}")

    # 打开高分辨率 PNG
    img = Image.open(png_path)

    # 生成 ICO 文件，包含所有指定分辨率
    img.save(ico_path, format="ICO", sizes=sizes)
    print(f"Generated high-quality ICO file: {ico_path}")
except Exception as e:
    print(f"Error: {e}")
finally:
    # 删除临时高分辨率 PNG 文件
    if os.path.exists(png_path):
        os.remove(png_path)
