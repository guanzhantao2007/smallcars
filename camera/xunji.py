# xunji.py - 黑线循迹模块
# 流程: 采集 -> 灰度化 -> 阈值分割 -> 远/中/近三个 ROI 求线心 -> 加权求偏差
# 对外接口:
#   xunji(cam, disp)            完整执行一次循迹（自行采集）
#   xunji_from_images(...)      对已采集的一帧做循迹（复用图像）
#   run()                       循迹测试主循环
# 返回值: (valid, error, direction)
#   valid     : True 表示至少一个 ROI 找到了黑线
#   error     : 加权横向偏差，单位像素，正数表示黑线在画面右侧
#   direction : 远端线心X - 近端线心X，正数表示黑线前方向右弯，负数向左弯

from maix import display, image, time, app
from camera_config import (WIDTH, HEIGHT, GRAY_MIN, GRAY_MAX, SHOW_BINARY,
                           PRINT_INTERVAL, open_camera, get_images)

# ---------------- 循迹可调参数 ----------------
WEIGHT_FAR, WEIGHT_MID, WEIGHT_NEAR = 1,0 ,0   # 三个 ROI 的权重 w1/w2/w3

# ---- slope anomaly filter (active only while crossing the inverted-T) ----
# When the T horizontal bar enters an ROI it becomes the largest blob there,
# so that ROI's center jumps away from the line direction and the weighted
# error spikes. The filter tests signed slopes between the three centers
# (A=far, B=mid, C=near): k_AB=(xB-xA)/(yB-yA), k_BC, k_AC. Signs are kept.
#   |k_AB-k_BC| small            -> all centers trusted, original result
#   |k_AB-k_BC| > SLOPE_DIFF_MAX -> one center is anomalous: trust the pair
#       with smaller |slope|, set the remaining ROI WEIGHT TO 0 and recompute
#       the weighted error; if k_AC sign disagrees with the trusted slope the
#       picture is unreliable -> keep original result, cut nothing
# Per-ROI status is returned so debug draws the crosshair only for trusted
# centers. No state is kept between frames (a failed detection is never
# reused). Invalid ROIs never join the slope math.
SLOPE_FILTER_EN = True    # True: filter on; False: exact original behavior
SLOPE_DIFF_MAX = 0.3      # max allowed |k_AB-k_BC|, unit dx/dy, tune on site
SLOPE_MIN_DY = 5          # min vertical gap (pixels) between centers to trust a slope

MIN_LINE_PIXELS = 100           # 噪声过滤：小于该像素数的色块直接忽略
ROI_Y_MIN = 30         # ROI 允许的最高 y（现场已从 120 调为 30，布局检查用）
REF_X = WIDTH / 2               # 每个 ROI 的参考X = 画面中心 = 160

# ---- ROI 对称布局参数 ----
# 水平：每个 ROI 宽 ROI_W，以画面中线为对称中心居中；
# 垂直：近端 ROI 距画面底部 ROI_BOTTOM_MARGIN，向上依次排列，相邻间距 ROI_GAP
# 默认值 (320/70/0/0) 与当前已调好的布局完全一致（ROI_Y_MIN=30，三段各70px），
# 改小宽度、加间距后 ROI 远离画面左右/底边边缘，可避开边缘噪声与反光
ROI_W = 320             # 每个 ROI 宽度，像素，水平居中对称
ROI_HEIGHT = 30         # 每个 ROI 高度，像素
ROI_GAP = 30            # 相邻 ROI 垂直间距，像素
ROI_BOTTOM_MARGIN = 30   # 近端 ROI 下边缘距画面底部的间距，像素

# 垂直布局启动时一次算好；放不进 ROI_Y_MIN 以下的画面就立即报错（fail-fast）
ROI_TOTAL_H = 3 * ROI_HEIGHT + 2 * ROI_GAP                 # ROI 整叠总高度
ROI_STACK_TOP = HEIGHT - ROI_BOTTOM_MARGIN - ROI_TOTAL_H   # 远端 ROI 上边缘 y
if ROI_STACK_TOP < ROI_Y_MIN:
    raise ValueError("ROI layout too tall: reduce ROI_HEIGHT / ROI_GAP "
                     "/ ROI_BOTTOM_MARGIN")


def make_rois():
    # 三个 ROI 关于画面中线左右对称：宽度 ROI_W、水平居中；
    # 垂直方向从 ROI_STACK_TOP 向下排列，相邻间距 ROI_GAP
    # 顺序固定: [远, 中, 近]，每个 ROI 格式为 [x, y, w, h]
    rois = []
    x = int(REF_X - ROI_W / 2)
    for i in range(3):
        y = ROI_STACK_TOP + i * (ROI_HEIGHT + ROI_GAP)
        rois.append([x, y, ROI_W, ROI_HEIGHT])
    return rois


def find_line_center_x(gray, roi):
    # 在单个 ROI 内的灰度图上找黑线中心
    # 噪声过滤: 色块像素数必须不小于 MIN_LINE_PIXELS，
    # 多个色块时取最大者（即黑线），忽略小噪声块
    # 返回 (是否有效, 线心X, 线心Y)，无效时坐标为 0
    blobs = gray.find_blobs([(GRAY_MIN, GRAY_MAX)],
                            roi=roi,
                            pixels_threshold=MIN_LINE_PIXELS,
                            area_threshold=MIN_LINE_PIXELS)
    if len(blobs) == 0:
        return False, 0, 0
    best = blobs[0]
    for b in blobs:
        if b.pixels() > best.pixels():
            best = b
    return True, best.cx(), best.cy()


def slope_filter(results):
    # Anomalous-center detection from signed slopes of the three ROI centers.
    # results: [(valid, cx, cy), ...] far/mid/near, as from find_line_center_x
    # Returns (normal, k_diff):
    #   normal : [bool, bool, bool] per ROI; False = anomalous, weight becomes 0;
    #            all True also covers "inconclusive, keep original result"
    #   k_diff : |k_AB-k_BC| of this frame for debug text; None if not computable
    normal = [True, True, True]
    if not SLOPE_FILTER_EN:
        return normal, None
    # collect valid centers in far->near order; invalid ROIs are skipped
    pts = []
    for i in range(3):
        if results[i][0]:
            pts.append((i, results[i][1], results[i][2]))
    if len(pts) < 3:
        return normal, None          # slope test needs all three centers
    ia, xa, ya = pts[0]              # A = far
    ib, xb, yb = pts[1]              # B = mid
    ic, xc, yc = pts[2]              # C = near
    # tiny vertical gaps would make the slope noisy/divide by ~0
    if (abs(yb - ya) < SLOPE_MIN_DY or abs(yc - yb) < SLOPE_MIN_DY
            or abs(yc - ya) < SLOPE_MIN_DY):
        return normal, None
    # signed slopes; the sign carries the line trend and must not be dropped
    k_ab = (xb - xa) / (yb - ya)
    k_bc = (xc - xb) / (yc - yb)
    k_ac = (xc - xa) / (yc - ya)
    k_diff = abs(k_ab - k_bc)+abs(k_ac - k_bc)+abs(k_ab - k_ac)
    if k_diff <= SLOPE_DIFF_MAX:
        return normal, k_diff        # slopes agree: nothing anomalous
    # slopes disagree: one center is likely pulled aside by the T bar.
    # trust the pair with the smaller |slope| (normal tracking trend)

    if abs(k_ab) <= abs(k_bc)and abs(k_ab) <= abs(k_ac):
        k_trust = k_ab               # trust far+mid, suspect near
        bad = ic
    if abs(k_bc) <= abs(k_ac)and abs(k_bc) <= abs(k_ab):
        k_trust = k_bc               # trust far+mid, suspect near
        bad = ia
    if abs(k_ac) <= abs(k_bc)and abs(k_ac) <= abs(k_ab):
        k_trust = k_ac               # trust far+mid, suspect near
        bad = ib
    # overall slope must agree with the trusted slope in sign, otherwise the
    # picture is unreliable: keep the original result, cut nothing
    #if k_ac * k_trust < 0:
     #   return normal, k_diff
    normal[bad] = False
    return normal, k_diff


def calc_error(results, normal=None):
    # results: [(有效, 线心X, 线心Y), ...] 三个元素，对应远/中/近
    # normal: per-ROI trust status from slope_filter (None = filter disabled);
    #         a False entry means that ROI weight is 0 for this frame
    # 加权中心法: error = sum(w_i * e_i) / sum(w_i)，其中 e_i = cx_i - REF_X
    # 无效的 ROI 相当于权重取 0，不参与分子和分母
    # direction: 远端线心X - 近端线心X，仅当远、近都有效时才计算
    # 返回 (是否有效, 偏差, 方向)
    sum_we = 0.0
    sum_w = 0.0
    weights = (WEIGHT_FAR, WEIGHT_MID, WEIGHT_NEAR)
    for i in range(3):
        valid, cx, cy = results[i]  # cy 在这里用不到，但解包保持一致
        if valid and (normal is None or normal[i]):
            sum_we += weights[i] * (cx - REF_X)
            sum_w += weights[i]
    if sum_w == 0.0:
        return False, 0.0, 0.0
    error = sum_we / sum_w
    direction = 0.0
    if results[0][0] and results[2][0]:
        direction = results[0][1] - results[2][1]  # 远端线心X - 近端线心X
    return True, error, direction


def draw_debug_line(base_img, rois, results, valid, error, direction,
                    normal=None, k_diff=None):
    # 在图上画出 ROI、参考线、找到的线心和状态文字
    # normal/k_diff: from slope_filter; crosshair only on trusted centers,
    # an anomalous center gets a red X marker instead of a cross
    for i in range(3):
        valid_i, cx, cy = results[i]  # 线心X/Y，无效时为 (False, 0, 0)
        color = image.COLOR_GREEN if valid_i else image.COLOR_RED
        base_img.draw_rect(rois[i][0], rois[i][1], rois[i][2], rois[i][3], color)
        if valid_i and (normal is None or normal[i]):
            # 十字画在色块真实质心处，永远跟随识别到的黑线中心
            base_img.draw_line(cx - 5, cy, cx + 5, cy, image.COLOR_YELLOW, 2)
            base_img.draw_line(cx, cy - 5, cx, cy + 5, image.COLOR_YELLOW, 2)
        elif valid_i:
            # anomalous center: no crosshair, red X so you can see what was cut
            base_img.draw_string(cx - 5, cy - 10, "X", image.COLOR_RED, scale=2)
    base_img.draw_line(int(REF_X), ROI_Y_MIN, int(REF_X), HEIGHT,
                       image.COLOR_BLUE, 1)
    if valid:
        text = "err=%+.1f dir=%+.1f" % (error, direction)
        if k_diff is not None:
            text += " dk%.1f" % k_diff
        cut = ""
        for i in range(3):
            if normal is not None and not normal[i]:
                cut += "FMN"[i]      # F=far M=mid N=near
        if cut:
            text += " cut:" + cut
    else:
        text = "LOST"
    base_img.draw_string(2, 2, text, image.COLOR_YELLOW, scale=2)


# ---------------- 对外主接口 ----------------
def xunji_from_images(img, gray, bin_img, disp=None):
    # 对已采集的一帧图像做循迹计算（供复用同一帧给T检测等模块）
    rois = make_rois()
    results = []
    for i in range(3):
        results.append(find_line_center_x(gray, rois[i]))
    normal, k_diff = slope_filter(results)
    valid, error, direction = calc_error(results, normal)
    if disp is not None:
        if SHOW_BINARY:
            draw_debug_line(bin_img, rois, results, valid, error, direction,
                            normal, k_diff)
            disp.show(bin_img)
        else:
            draw_debug_line(img, rois, results, valid, error, direction,
                            normal, k_diff)
            disp.show(img)
    return valid, error, direction


def xunji(cam, disp=None):
    # 完整执行一次循迹计算，在主循环中调用（自行采集图像）
    # 返回 (是否有效, 偏差, 方向)，含义见文件头注释
    img, gray, bin_img = get_images(cam)
    return xunji_from_images(img, gray, bin_img, disp)


def run():
    # 循迹测试主循环
    cam = open_camera()
    disp = display.Display()
    frame = 0
    t_last = time.ticks_ms()
    while not app.need_exit():
        valid, error, direction = xunji(cam, disp)
        frame += 1
        if frame % PRINT_INTERVAL == 0:
            now = time.ticks_ms()
            ms = time.ticks_diff(now, t_last) / PRINT_INTERVAL
            t_last = now
            print("valid=%d err=%+.1f dir=%+.1f t=%.1fms"
                  % (valid, error, direction, ms))
