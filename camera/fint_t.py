# fint_t.py - 倒T检测模块（二值图 ROI 像素占比法）
# 思路参考 OpenMV「全程.py」的小区域统计 + 状态确认，检测判断为：
#   在「横线左侧 / 横线右侧 / 竖线」三个可调 ROI 内分别统计目标像素占比，
#   三个占比在同一帧内同时达到各自阈值 -> 本帧检出倒T；
#   再沿用项目原有的多帧确认机制（连续 N 帧确认 / 连续 N 帧丢失复位）
#   防止单帧噪声误报。
# 注意：
#   - 三个 ROI 是同一帧画面里的三个空间区域，条件是「同时满足」，
#     不存在先后顺序；
#   - 本模块只输出 valid 和竖线位置，不含任何停车/控制逻辑，
#     运动控制归 STM32。
# 对外接口:
#   detect_t(bin_img)            单帧检测（纯函数，无历史状态）
#   detect_t_confirmed(bin_img)  带多帧确认的对外接口
#   reset_t_confirm()            清空确认状态
#   run()                        检测测试主循环（main.py TASK="t" 调用）
# 返回值统一为 (valid, tx, ty, ratios):
#   valid  : 是否检出倒T（confirmed 版本已含多帧确认）
#   tx, ty : 竖线最大色块质心，作为参考点；无效时为 (0, 0)
#   ratios : [左%, 右%, 竖%] 三个 ROI 的实测像素占比，用于调阈值

from maix import display, image, time, app
from camera_config import SHOW_BINARY, PRINT_INTERVAL, open_camera, get_images

# ---------------- 倒T检测可调参数 ----------------
# ROI 格式 [x, y, w, h]，像素坐标，原点在画面左上角，画面 320x240。
# 下面三个 ROI 全部是占位值！必须看着调试画面现场标定。
T_ROI_LEFT  = [240, 60, 70, 30]   # 横线左侧：框住横线左臂
T_ROI_RIGHT = [240, 150, 70, 30]  # 横线右侧：框住横线右臂
T_ROI_STEM  = [130, 110, 130, 10]   # 竖线：横线下方、画面中线附近，框住竖杆
                                   # 注意竖线 ROI 不要和横线 ROI 重叠，
                                   # 否则横线像素会把竖线 ROI 也点亮

T_LEFT_MIN_RATIO  = 20             # 左 ROI 占比下限，单位 %，占位值需标定
T_RIGHT_MIN_RATIO = 20              # 右 ROI 占比下限，单位 %，占位值需标定
T_STEM_MIN_RATIO  = 70             # 竖线 ROI 占比下限，单位 %，占位值需标定

T_BIN_WHITE_MIN = 100              # 二值图上目标像素灰度下限。
                                   # binary() 已把目标变成白色(255)，
                                   # 所以用 (100, 255) 找色块即可，一般不用改

T_CONFIRM_FRAMES = 1               # 连续 N 帧同时达标才算确认（防误报，
                                   # 现场噪声大时调到 2~3）
T_LOST_FRAMES = 3                  # 连续 N 帧未达标才复位确认状态


# ---------------- 占比统计 ----------------
def roi_ratio(bin_img, roi):
    # 统计一个 ROI 内目标（白色）像素占比，并找出 ROI 内最大色块
    # 二值图上黑线已被 binary() 变成白色(255)，用白色阈值找色块；
    # pixels_threshold/area_threshold 取 1，不过滤任何色块，保证统计完整
    # （散点噪声也计入，但占比极小，不影响判断）
    # 返回 (占比%, 最大色块或 None)
    blobs = bin_img.find_blobs([(T_BIN_WHITE_MIN, 255)],
                               roi=roi,
                               pixels_threshold=1,
                               area_threshold=1)
    count = 0   # ROI 内目标像素总数
    best = None # ROI 内最大色块（竖线 ROI 用它求位置）
    for b in blobs:
        count += b.pixels()
        if best is None or b.pixels() > best.pixels():
            best = b
    area = roi[2] * roi[3]      # ROI 总像素数
    if area == 0:
        return 0.0, None
    return count * 100.0 / area, best


# ---------------- 单帧检测 ----------------
def detect_t(bin_img):
    # 单帧倒T检测（纯函数，无历史状态）：
    # 三个 ROI 占比在同一帧内同时达到阈值才判 valid
    # 返回 (valid, tx, ty, ratios)，含义见文件头
    ratio_l, _ = roi_ratio(bin_img, T_ROI_LEFT)    # 左臂只看占比
    ratio_r, _ = roi_ratio(bin_img, T_ROI_RIGHT)   # 右臂只看占比
    ratio_s, blob_s = roi_ratio(bin_img, T_ROI_STEM)  # 竖线还要取位置
    ratios = [ratio_l, ratio_r, ratio_s]
    valid = (ratio_l >= T_LEFT_MIN_RATIO
             and ratio_r >= T_RIGHT_MIN_RATIO
             and ratio_s >= T_STEM_MIN_RATIO)
    if valid and blob_s is not None:
        # 位置取竖线最大色块的质心
        return True, int(blob_s.cx()), int(blob_s.cy()), ratios
    return False, 0, 0, ratios


# ---------------- 多帧确认（沿用原有机制） ----------------
_t_confirm = 0     # 连续达标帧数
_t_lost = 0        # 连续未达标帧数
_t_active = False  # 已确认锁存


def reset_t_confirm():
    # 清空T确认状态（测试用）
    global _t_confirm, _t_lost, _t_active
    _t_confirm = 0
    _t_lost = 0
    _t_active = False


def detect_t_confirmed(bin_img):
    # 带多帧确认的倒T检测：
    #   - 新T需连续 T_CONFIRM_FRAMES 帧同时达标才输出 valid=True
    #   - 已确认期间单帧丢失不打断，连续 T_LOST_FRAMES 帧丢失才复位
    #   - 仅当前帧达标才输出坐标；当前帧未达标立即返回 (False, 0, 0, ratios)，
    #     绝不返回上一帧的坐标
    global _t_confirm, _t_lost, _t_active
    ok, x, y, ratios = detect_t(bin_img)
    if ok:
        _t_confirm += 1
        _t_lost = 0
        need = T_CONFIRM_FRAMES if not _t_active else 1
        if _t_confirm >= need:
            _t_active = True
    else:
        _t_confirm = 0
        _t_lost += 1
        if _t_lost >= T_LOST_FRAMES:
            _t_active = False
    if ok and _t_active:
        return True, x, y, ratios
    return False, 0, 0, ratios


# ---------------- 调试绘制 ----------------
def draw_debug_t(base_img, valid, tx, ty, ratios):
    # 画三个 ROI（达标绿框 / 未达标红框）、每框实测占比和阈值、
    # 竖线位置十字、整体状态文字
    rois = (T_ROI_LEFT, T_ROI_RIGHT, T_ROI_STEM)
    mins = (T_LEFT_MIN_RATIO, T_RIGHT_MIN_RATIO, T_STEM_MIN_RATIO)
    names = ("L", "R", "S")
    for i in range(3):
        passed = ratios[i] >= mins[i]
        color = image.COLOR_GREEN if passed else image.COLOR_RED
        r = rois[i]
        base_img.draw_rect(r[0], r[1], r[2], r[3], color)
        # 框内文字: 名称 实测占比/阈值，例如 "L 12.3/8"
        base_img.draw_string(r[0] + 2, r[1] + 2,
                             "%s %.1f/%.0f" % (names[i], ratios[i], mins[i]),
                             color)
    if valid:
        # 十字标出竖线参考点（ROI 未标定时位置仅供参考）
        base_img.draw_line(tx - 6, ty, tx + 6, ty, image.COLOR_YELLOW, 2)
        base_img.draw_line(tx, ty - 6, tx, ty + 6, image.COLOR_YELLOW, 2)
        base_img.draw_string(2, 2, "T OK x=%d y=%d" % (tx, ty),
                             image.COLOR_YELLOW, scale=2)
    else:
        base_img.draw_string(2, 2, "NO T", image.COLOR_RED, scale=2)


# ---------------- 测试主循环 ----------------
def run():
    # 倒T检测测试主循环（main.py TASK="t" 时调用）
    cam = open_camera()
    disp = display.Display()
    frame = 0
    t_last = time.ticks_ms()
    reset_t_confirm()
    while not app.need_exit():
        img, gray, bin_img = get_images(cam)
        valid, tx, ty, ratios = detect_t_confirmed(bin_img)
        base = bin_img if SHOW_BINARY else img
        draw_debug_t(base, valid, tx, ty, ratios)
        disp.show(base)
        frame += 1
        if frame % PRINT_INTERVAL == 0:
            now = time.ticks_ms()
            ms = time.ticks_diff(now, t_last) / PRINT_INTERVAL
            t_last = now
            print("T valid=%d x=%d y=%d L=%.1f%% R=%.1f%% S=%.1f%% t=%.1fms"
                  % (valid, tx, ty, ratios[0], ratios[1], ratios[2], ms))
