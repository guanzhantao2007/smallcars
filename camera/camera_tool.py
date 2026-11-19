# camera_tool.py - 停车挑战视觉模块：黑线循迹 + 倒T型车位边界识别
# 处理流程: 采集 -> 灰度化 -> 阈值分割 -> 远/中/近三个 ROI 求线心 -> 加权求偏差
# 返回值: (valid, error, direction)
#   valid     : True 表示至少一个 ROI 找到了黑线
#   error     : 加权横向偏差，单位像素，正数表示黑线在画面右侧
#   direction : 远端线心X - 近端线心X，正数表示黑线前方向右弯，负数向左弯
#
# 倒T检测（detect_t_junction）：
#   在二值图 ROI 内用 find_line_segments 找线段，取最长者为主边界线，
#   找与其近似垂直的线段为分隔线，无限直线求交点，并用端点关系区分
#   T型（分隔线一端贴主线、另一端伸出）和十字（两端等距跨线）；
#   detect_t_confirmed 在其外包连续多帧确认，丢失防抖；
#   无检出立即返回 (False, 0, 0)，绝不返回上一帧坐标
# Phase-2 fault isolation (TEST_MODE / T_DEBUG_VERBOSE):
#   TEST_MODE="seg"  : dump raw find_line_segments results on BOTH gray and
#                      binary images, draw all segments green, no T logic
#   TEST_MODE="t"    : T test; T_DEBUG_VERBOSE=True runs per-stage checks
#                      (S1 raw count -> S2 length filter -> S3 main/sep
#                      -> S4 angle -> S5 intersection -> S6 endpoints)
#                      and prints a detailed log block on every verdict change
# API 均已对照 MaixPy 官方文档核实（wiki.sipeed.com，2024-11）：
#   img.to_format(image.Format.FMT_GRAYSCALE) 返回新的灰度图
#   binary(..., copy=True): 默认 copy=False 会原地修改图像，务必传 copy=True
#   灰度图上 find_blobs 使用两值阈值 (Lmin, Lmax)，取值范围 0-255
#   blob 方法: cx(), cy(), pixels(), x(), y(), w(), h()

from maix import camera, display, image, time, app
import math

# ---------------- 可调参数 ----------------
WIDTH, HEIGHT = 320, 240        # 摄像头分辨率，像素

GRAY_MIN, GRAY_MAX = 0,70 # 黑线灰度值范围（0-255），
                                # 当前为占位值，需在实地标定
WEIGHT_FAR, WEIGHT_MID, WEIGHT_NEAR = 1, 2, 1  # 三个 ROI 的权重 w1/w2/w3

MIN_LINE_PIXELS = 100          # 噪声过滤：小于该像素数的色块直接忽略
ROI_Y_MIN = HEIGHT // 2         # 只使用画面下半部分（y=120 开始）
ROI_HEIGHT = (HEIGHT - ROI_Y_MIN) // 3  # 单个 ROI 高度 = 40 像素
REF_X = WIDTH / 2               # 每个 ROI 的参考X = 画面中心 = 160

SHOW_BINARY = True             # True: 显示二值图，用于调阈值
PRINT_INTERVAL = 10             # 每 N 帧打印一次状态

TEST_MODE = "seg"         # "line": tracking test, "seg": raw segment dump, "t": T test
T_DEBUG_VERBOSE = True  # True: staged per-frame T logs for fault isolation

# ---------------- 倒T检测参数 ----------------
T_ROI = [0, 0, 320, 240]      # T检测区域（默认画面下半部分），可按现场调整
T_MIN_LINE_LEN = 20           # 候选线段最短长度，像素，过滤短线噪声
T_ANGLE_TOL = 40              # 判定垂直的容差，度；俯拍透视不是90度，故放宽
T_ENDPOINT_TOL = 20             # 分隔线端点距主线的判定距离，像素
T_MIN_STICKOUT = 25             # 分隔线另一端需伸出主线的最小距离，像素
                                # （用于区分T型与十字交叉）
T_CONFIRM_FRAMES = 1        # 连续 N 帧检出才确认T有效
T_LOST_FRAMES = 3               # 连续 N 帧未检出才复位（防止同个T被反复触发）


# ---------------- 基础初始化 ----------------
def open_camera():
    # 按目标分辨率打开摄像头，返回 camera 对象
    return camera.Camera(WIDTH, HEIGHT)


def make_rois():
    # 把画面下半部分均分为 3 个 ROI，从上到下 = 远、中、近
    # 每个 ROI 格式为 [x, y, w, h]，顺序固定: [远, 中, 近]
    rois = []
    for i in range(3):
        y = ROI_Y_MIN + i * ROI_HEIGHT  # 远=120-160，中=160-200，近=200-240
        rois.append([0, y, WIDTH, ROI_HEIGHT])
    return rois


# ---------------- 每帧处理 ----------------
def get_images(cam):
    # 采集一帧，转灰度图，并生成用于调试显示的二值图
    # 关键: binary() 默认 copy=False 会原地修改 gray！必须 copy=True，
    # 否则后续 find_blobs 在被改写的二值图上检测，阈值(0,70)会把
    # 黑色背景当成目标（线已变成白色255，反而不在阈值内）
    # 返回 (彩色图, 灰度图, 二值图)
    img = cam.read()
    gray = img.to_format(image.Format.FMT_GRAYSCALE)
    bin_img = gray.binary([(GRAY_MIN, GRAY_MAX)], copy=True)
    return img, gray, bin_img


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


def calc_error(results):
    # results: [(有效, 线心X, 线心Y), ...] 三个元素，对应远/中/近
    # 加权中心法: error = sum(w_i * e_i) / sum(w_i)，其中 e_i = cx_i - REF_X
    # 无效的 ROI 相当于权重取 0，不参与分子和分母
    # direction: 远端线心X - 近端线心X，仅当远、近都有效时才计算
    # 返回 (是否有效, 偏差, 方向)
    sum_we = 0.0
    sum_w = 0.0
    weights = (WEIGHT_FAR, WEIGHT_MID, WEIGHT_NEAR)
    for i in range(3):
        valid, cx, cy = results[i]  # cy 在这里用不到，但解包保持一致
        if valid:
            sum_we += weights[i] * (cx - REF_X)
            sum_w += weights[i]
    if sum_w == 0.0:
        return False, 0.0, 0.0
    error = sum_we / sum_w
    direction = 0.0
    if results[0][0] and results[2][0]:
        direction = results[0][1] - results[2][1]  # 远端线心X - 近端线心X
    return True, error, direction


def draw_debug(base_img, rois, results, valid, error, direction):
    # 在图上画出 ROI、参考线、找到的线心和状态文字
    for i in range(3):
        valid_i, cx, cy = results[i]  # 线心X/Y，无效时为 (False, 0, 0)
        color = image.COLOR_GREEN if valid_i else image.COLOR_RED
        base_img.draw_rect(rois[i][0], rois[i][1], rois[i][2], rois[i][3], color)
        if valid_i:
            # 十字画在色块真实质心处，永远跟随识别到的黑线中心
            base_img.draw_line(cx - 5, cy, cx + 5, cy, image.COLOR_YELLOW, 2)
            base_img.draw_line(cx, cy - 5, cx, cy + 5, image.COLOR_YELLOW, 2)
    base_img.draw_line(int(REF_X), ROI_Y_MIN, int(REF_X), HEIGHT,
                       image.COLOR_BLUE, 1)
    if valid:
        text = "err=%+.1f dir=%+.1f" % (error, direction)
    else:
        text = "LOST"
    base_img.draw_string(2, 2, text, image.COLOR_YELLOW, scale=2)


# ---------------- 对外主接口：黑线循迹 ----------------
def xunji_from_images(img, gray, bin_img, disp=None):
    # 对已采集的一帧图像做循迹计算（供复用同一帧给T检测等模块）
    rois = make_rois()
    results = []
    for i in range(3):
        results.append(find_line_center_x(gray, rois[i]))
    valid, error, direction = calc_error(results)
    if disp is not None:
        if SHOW_BINARY:
            draw_debug(bin_img, rois, results, valid, error, direction)
            disp.show(bin_img)
        else:
            draw_debug(img, rois, results, valid, error, direction)
            disp.show(img)
    return valid, error, direction


def xunji(cam, disp=None):
    # 完整执行一次循迹计算，在主循环中调用（自行采集图像）
    # 返回 (是否有效, 偏差, 方向)，含义见文件头注释
    img, gray, bin_img = get_images(cam)
    return xunji_from_images(img, gray, bin_img, disp)


# ---------------- 倒T检测：几何工具 ----------------
def line_intersection(l1, l2):
    # 两条线段所在无限直线求交点（行列式法），近平行返回 None
    x1, y1, x2, y2 = l1.x1(), l1.y1(), l1.x2(), l1.y2()
    x3, y3, x4, y4 = l2.x1(), l2.y1(), l2.x2(), l2.y2()
    d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(d) < 1e-6:
        return None
    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / d
    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / d
    return (px, py)


def seg_angle_diff(l1, l2):
    # 两线段方向向量夹角，0-90 度（用向量点积，避免 theta 0-179 环绕问题）
    vx1, vy1 = l1.x2() - l1.x1(), l1.y2() - l1.y1()
    vx2, vy2 = l2.x2() - l2.x1(), l2.y2() - l2.y1()
    n1 = math.sqrt(vx1 * vx1 + vy1 * vy1)
    n2 = math.sqrt(vx2 * vx2 + vy2 * vy2)
    if n1 == 0 or n2 == 0:
        return 180.0
    c = abs(vx1 * vx2 + vy1 * vy2) / (n1 * n2)
    if c > 1.0:
        c = 1.0
    return math.degrees(math.acos(c))


def point_line_dist(px, py, l):
    # 点到无限直线的距离（基于线段两端点确定直线）
    x1, y1, x2, y2 = l.x1(), l.y1(), l.x2(), l.y2()
    n = math.sqrt((x2 - x1) * (x2 - x1) + (y2 - y1) * (y2 - y1))
    if n == 0:
        return 1e9
    return abs((y2 - y1) * (px - x1) - (x2 - x1) * (py - y1)) / n


def point_near_segment(px, py, l, tol):
    # 点是否落在线段上（含两端各 tol 像素的容差）：投影长度 0-tol .. len+tol
    x1, y1, x2, y2 = l.x1(), l.y1(), l.x2(), l.y2()
    vx, vy = x2 - x1, y2 - y1
    seg_len2 = vx * vx + vy * vy
    if seg_len2 == 0:
        return False
    t = ((px - x1) * vx + (py - y1) * vy) / seg_len2  # 投影比例 0..1
    s = t * math.sqrt(seg_len2)                        # 投影长度，像素
    seg_len = math.sqrt(seg_len2)
    return -tol <= s <= seg_len + tol


def find_longest_seg(segs):
    # return the longest segment in the list, or None if empty
    # (never assume the first element is the longest!)
    best = None
    best_len = -1
    for s in segs:
        if s.length() > best_len:
            best_len = s.length()
            best = s
    return best


# ---------------- 倒T检测：单帧识别 ----------------
def detect_t_junction(bin_img, roi, draw_base=None):
    # 单帧倒T检测（纯函数，无历史状态）：
    #   1. 在二值图 roi 内找线段（LSD，端点是真实端点）
    #   2. 最长线段 = 主边界线，其余中找与主线近似垂直的分隔线
    #   3. 无限直线求交点；交点需落在两条线段身上
    #   4. 端点判别T型：分隔线一端贴主线(near<=TOL)、
    #      另一端明显伸出(far>=STICKOUT)；两端都跨线则是十字，判无效
    # bin_img : 传入 get_images() 生成的二值图（LSD/霍夫需在二值图上跑）
    # draw_base: 可选，把找到的线段和交点画上去供调试
    # 返回 (valid, 交点x, 交点y)，无有效T返回 (False, 0, 0)
    segs = bin_img.find_line_segments(roi=roi,
                                      merge_distance=10,
                                      max_theta_difference=15)
    cand = []
    for s in segs:
        if s.length() >= T_MIN_LINE_LEN:
            cand.append(s)
    if len(cand) < 2:
        return False, 0, 0
    main = find_longest_seg(cand)  # longest segment = main boundary line
    for i in range(len(cand)):
        sep = cand[i]
        if sep is main:
            continue
        if seg_angle_diff(main, sep) < 90.0 - T_ANGLE_TOL:
            continue  # 不够垂直
        p = line_intersection(main, sep)
        if p is None:
            continue  # 近平行
        if not point_near_segment(p[0], p[1], main, T_ENDPOINT_TOL):
            continue  # 交点不在主线段上
        if not point_near_segment(p[0], p[1], sep, T_ENDPOINT_TOL):
            continue  # 交点不在分隔线段上
        d1 = point_line_dist(sep.x1(), sep.y1(), main)
        d2 = point_line_dist(sep.x2(), sep.y2(), main)
        near = d1 if d1 < d2 else d2
        far = d2 if d1 < d2 else d1
        # T型: 一端贴主线，另一端伸出；十字: 两端都跨线(near过大)
        if near <= T_ENDPOINT_TOL and far >= T_MIN_STICKOUT:
            if draw_base is not None:
                draw_base.draw_line(main.x1(), main.y1(), main.x2(), main.y2(),
                                    image.COLOR_BLUE, 2)
                draw_base.draw_line(sep.x1(), sep.y1(), sep.x2(), sep.y2(),
                                    image.COLOR_YELLOW, 2)
                draw_base.draw_line(int(p[0]) - 6, int(p[1]),
                                    int(p[0]) + 6, int(p[1]), image.COLOR_RED, 2)
                draw_base.draw_line(int(p[0]), int(p[1]) - 6,
                                    int(p[0]), int(p[1]) + 6, image.COLOR_RED, 2)
            return True, int(p[0]), int(p[1])
    return False, 0, 0


# ---------------- 倒T检测：多帧确认 ----------------
_t_confirm = 0    # 连续检出计数
_t_lost = 0       # 连续未检出计数
_t_active = False # 已确认状态锁存


def reset_t_confirm():
    # 清空T确认状态（测试用）
    global _t_confirm, _t_lost, _t_active
    _t_confirm = 0
    _t_lost = 0
    _t_active = False


def detect_t_confirmed(bin_img, roi):
    # 带多帧确认的倒T检测对外接口：
    #   - 新T需连续 T_CONFIRM_FRAMES 帧检出才输出 valid=True
    #   - 已确认期间单帧丢失不打断（下一帧检出立即有效），
    #     连续 T_LOST_FRAMES 帧丢失才复位
    #     （同个T不会因噪声闪烁反复触发上升沿，T离开后才会重新确认新T）
    #   - 仅当前帧检出才输出坐标；当前帧无检出立即返回 (False, 0, 0)，
    #     绝不返回上一帧的交点坐标
    global _t_confirm, _t_lost, _t_active
    ok, x, y = detect_t_junction(bin_img, roi)
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
        return True, x, y
    return False, 0, 0


# ---------------- 倒T检测：分阶段调试（阶段二） ----------------
_t_dbg_summary = None  # last stage-summary key, for change-detection printing


def _seg_str(s):
    # compact segment description for logs
    return "(%d,%d)-(%d,%d) len=%d" % (s.x1(), s.y1(), s.x2(), s.y2(), s.length())


def detect_t_debug(bin_img, roi, draw_base, frame):
    # staged single-frame T detection for fault isolation:
    #   S1 raw segment count -> S2 length filter -> S3 main/sep selection
    #   -> S4 angle -> S5 intersection on segments -> S6 endpoint distances
    # prints a detailed log block when any stage verdict changes, and
    # re-prints every PRINT_INTERVAL frames as heartbeat (coords jitter)
    # draws: green=all candidates, blue=main, yellow=sep(passed angle),
    #        red cross=computed intersection
    # returns (valid, x, y), same contract as detect_t_junction
    global _t_dbg_summary
    ok, ox, oy = False, 0, 0
    segs = bin_img.find_line_segments(roi=roi,
                                      merge_distance=10,
                                      max_theta_difference=15)
    n_raw = len(segs)
    cand = []
    for s in segs:
        if s.length() >= T_MIN_LINE_LEN:
            cand.append(s)
    n_cand = len(cand)
    lines = []
    lines.append("raw=%d cand=%d" % (n_raw, n_cand))
    if n_cand < 2:
        lines.append("FAIL S2: need >=2 segments >= %dpx" % T_MIN_LINE_LEN)
        summary = "raw=%d cand=%d need2" % (n_raw, n_cand)
    else:
        main = find_longest_seg(cand)
        lines.append("main(longest): %s" % _seg_str(main))
        if draw_base is not None:
            for s in cand:
                draw_base.draw_line(s.x1(), s.y1(), s.x2(), s.y2(),
                                    image.COLOR_GREEN, 1)
            draw_base.draw_line(main.x1(), main.y1(), main.x2(), main.y2(),
                                image.COLOR_BLUE, 2)
        verdicts = []
        for i in range(len(cand)):
            sep = cand[i]
            if sep is main:
                continue
            angle = seg_angle_diff(main, sep)
            if angle < 90.0 - T_ANGLE_TOL:
                verdicts.append("sep%d S4-angle-fail %.1fdeg" % (i, angle))
                continue
            if draw_base is not None:
                draw_base.draw_line(sep.x1(), sep.y1(), sep.x2(), sep.y2(),
                                    image.COLOR_YELLOW, 1)
            p = line_intersection(main, sep)
            if p is None:
                verdicts.append("sep%d S5-parallel-fail" % i)
                continue
            on_main = point_near_segment(p[0], p[1], main, T_ENDPOINT_TOL)
            on_sep = point_near_segment(p[0], p[1], sep, T_ENDPOINT_TOL)
            d1 = point_line_dist(sep.x1(), sep.y1(), main)
            d2 = point_line_dist(sep.x2(), sep.y2(), main)
            near = d1 if d1 < d2 else d2
            far = d2 if d1 < d2 else d1
            passed = (on_main and on_sep and near <= T_ENDPOINT_TOL
                      and far >= T_MIN_STICKOUT)
            if passed:
                verdicts.append("sep%d I=(%d,%d) S5=1/1 S6 near=%.0f far=%.0f PASS"
                                % (i, int(p[0]), int(p[1]), near, far))
            else:
                verdicts.append("sep%d I=(%d,%d) S5 on_main=%d on_sep=%d "
                                "S6 near=%.0f/%.0f far=%.0f/%.0f"
                                % (i, int(p[0]), int(p[1]), on_main, on_sep,
                                   near, T_ENDPOINT_TOL, far, T_MIN_STICKOUT))
            if draw_base is not None:
                draw_base.draw_line(int(p[0]) - 6, int(p[1]),
                                    int(p[0]) + 6, int(p[1]),
                                    image.COLOR_RED, 2)
                draw_base.draw_line(int(p[0]), int(p[1]) - 6,
                                    int(p[0]), int(p[1]) + 6,
                                    image.COLOR_RED, 2)
            if passed:
                ok, ox, oy = True, int(p[0]), int(p[1])
                break
        if len(verdicts) == 0:
            verdicts.append("no separator candidate besides main")
        for v in verdicts:
            lines.append(v)
        summary = "raw=%d cand=%d main_len=%d | %s" \
            % (n_raw, n_cand, main.length(), "; ".join(verdicts))
    if summary != _t_dbg_summary or frame % PRINT_INTERVAL == 0:
        _t_dbg_summary = summary
        print("[T-DBG] f=%d %s" % (frame, lines[0]))
        for i in range(1, len(lines)):
            print("   %s" % lines[i])
    return ok, ox, oy


def draw_t_status(base_img, valid, x, y):
    # 画T检测 ROI 框和状态文字（交点十字由 detect_t_junction 的 draw_base 绘制）
    base_img.draw_rect(T_ROI[0], T_ROI[1], T_ROI[2], T_ROI[3], image.COLOR_BLUE)
    if valid:
        text = "T:OK x=%d y=%d" % (x, y)
    else:
        text = "T:none"
    base_img.draw_string(2, 20, text, image.COLOR_RED, scale=2)


# ---------------- 测试入口 ----------------
def run_line_test():
    # 黑线循迹测试主循环
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


def run_seg_test():
    # stage-0 debug: raw find_line_segments on BOTH gray and binary images,
    # no T logic at all; one capture feeds both tests and the display
    # draw: green width1 = segments found on gray image,
    #       green width2 = segments found on binary image
    cam = open_camera()
    disp = display.Display()
    frame = 0
    t_last = time.ticks_ms()
    while not app.need_exit():
        img, gray, bin_img = get_images(cam)
        segs_gray = gray.find_line_segments(roi=T_ROI,
                                            merge_distance=10,
                                            max_theta_difference=15)
        segs_bin = bin_img.find_line_segments(roi=T_ROI,
                                              merge_distance=10,
                                              max_theta_difference=15)
        for s in segs_gray:
            img.draw_line(s.x1(), s.y1(), s.x2(), s.y2(), image.COLOR_GREEN, 1)
        for s in segs_bin:
            img.draw_line(s.x1(), s.y1(), s.x2(), s.y2(), image.COLOR_GREEN, 2)
        img.draw_rect(T_ROI[0], T_ROI[1], T_ROI[2], T_ROI[3], image.COLOR_BLUE)
        # self-test marker: thick green tick on left edge. If you can see it
        # but no other green lines, find_line_segments returned 0 segments
        # -> extraction problem, not a display problem
        img.draw_line(2, 50, 2, 110, image.COLOR_GREEN, 4)
        img.draw_string(2, 2, "gray=%d bin=%d"
                        % (len(segs_gray), len(segs_bin)),
                        image.COLOR_RED, scale=2)
        disp.show(img)
        frame += 1
        if frame % PRINT_INTERVAL == 0:
            now = time.ticks_ms()
            ms = time.ticks_diff(now, t_last) / PRINT_INTERVAL
            t_last = now
            print("[SEG] f=%d gray=%d bin=%d t=%.1fms"
                  % (frame, len(segs_gray), len(segs_bin), ms))
            for i in range(len(segs_bin)):
                s = segs_bin[i]
                print("  bin#%d %s" % (i + 1, _seg_str(s)))
            for i in range(len(segs_gray)):
                s = segs_gray[i]
                print("  gray#%d %s" % (i + 1, _seg_str(s)))


def run_t_test():
    # 倒T检测测试主循环
    # T_DEBUG_VERBOSE=True: staged checks + detailed logs (fault isolation)
    # T_DEBUG_VERBOSE=False: normal path with multi-frame confirm
    cam = open_camera()
    disp = display.Display()
    frame = 0
    t_last = time.ticks_ms()
    reset_t_confirm()
    while not app.need_exit():
        img, gray, bin_img = get_images(cam)  # one capture, shared by stages
        base = bin_img if SHOW_BINARY else img
        if T_DEBUG_VERBOSE:
            ok, x, y = detect_t_debug(bin_img, T_ROI, base, frame)
        else:
            ok, x, y = detect_t_confirmed(bin_img, T_ROI)
        draw_t_status(base, ok, x, y)
        disp.show(base)
        frame += 1
        if frame % PRINT_INTERVAL == 0:
            now = time.ticks_ms()
            ms = time.ticks_diff(now, t_last) / PRINT_INTERVAL
            t_last = now
            print("T valid=%d x=%d y=%d t=%.1fms" % (ok, x, y, ms))


if __name__ == "__main__":
    if TEST_MODE == "seg":
        run_seg_test()
    elif TEST_MODE == "t":
        run_t_test()
    else:
        run_line_test()
