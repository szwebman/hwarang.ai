"""아이콘 생성 스크립트

PIL(Pillow)로 화랑 Grid 에이전트 아이콘을 생성합니다.

사용법:
    pip install Pillow
    python generate_icons.py
"""

import os

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow 필요: pip install Pillow")
    exit(1)


def create_icon(size, bg_color=(59, 130, 246), text="H"):
    """화랑 아이콘 생성."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 둥근 사각형 배경
    padding = size // 8
    radius = size // 4
    draw.rounded_rectangle(
        [padding, padding, size - padding, size - padding],
        radius=radius,
        fill=bg_color,
    )

    # 글자 H
    font_size = size // 2
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
    except (OSError, IOError):
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except (OSError, IOError):
            font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (size - tw) // 2
    y = (size - th) // 2 - size // 16

    draw.text((x, y), text, fill=(255, 255, 255), font=font)

    return img


def create_tray_icon(size=22):
    """트레이/메뉴바 아이콘 (작고 심플)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 심플한 H
    draw.rounded_rectangle([2, 2, size-2, size-2], radius=4, fill=(59, 130, 246))

    font_size = size - 8
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
    except (OSError, IOError):
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), "H", font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(((size - tw) // 2, (size - th) // 2 - 1), "H", fill=(255, 255, 255), font=font)

    return img


# 앱 아이콘 생성
sizes = {
    "32x32.png": 32,
    "128x128.png": 128,
    "128x128@2x.png": 256,
}

for filename, size in sizes.items():
    icon = create_icon(size)
    icon.save(filename)
    print(f"생성: {filename} ({size}x{size})")

# macOS .icns용 (1024x1024)
icon_1024 = create_icon(1024)
icon_1024.save("icon.png")
print("생성: icon.png (1024x1024)")

# macOS icns (sips 명령으로 변환 필요)
os.system("sips -s format icns icon.png --out icon.icns 2>/dev/null || echo 'icon.icns: sips 필요 (macOS에서 실행)'")

# Windows .ico
icon_256 = create_icon(256)
icon_48 = create_icon(48)
icon_32 = create_icon(32)
icon_16 = create_icon(16)
icon_256.save("icon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (256, 256)],
              append_images=[icon_16, icon_32, icon_48])
print("생성: icon.ico")

# 트레이 아이콘
tray = create_tray_icon(22)
tray.save("tray-icon.png")
print("생성: tray-icon.png (22x22)")

# 트레이 아이콘 (2x, 레티나)
tray_2x = create_tray_icon(44)
tray_2x.save("tray-icon@2x.png")
print("생성: tray-icon@2x.png (44x44)")

print("\n아이콘 생성 완료!")
