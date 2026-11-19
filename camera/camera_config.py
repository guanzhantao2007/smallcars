# camera_config.py - 所有视觉任务共享的基础层
# 内容：共享参数、摄像头/图像基础函数、几何工具函数
# 被 xunji.py / fint_t.py / main.py 引用
#
# API 均已对照 MaixPy 官方文档核实（wiki.sipeed.com）：
#   img.to_format(image.Format.FMT_GRAYSCALE) 返回新的灰度图
#   binary(..., copy=True): 默认 copy=False 会原地修改图像，务必传 copy=True
#   灰度图上 find_blobs 使用两值阈值 (Lmin, Lmax)，取值范围 0-255
#   blob 方法: cx(), cy(), pixels()；Line 方法: x1(),y1(),x2(),y2(),length()

from maix import camera, image
import math

# ---------------- 共享可调参数 ----------------
WIDTH, HEIGHT = 320, 240        # 摄像头分辨率，像素

GRAY_MIN, GRAY_MAX = 0, 70      # 黑线灰度值范围（0-255），已按现场标定
SHOW_BINARY = True              # True: 显示二值图；False: 显示原始彩色图
PRINT_INTERVAL = 10             # 每 N 帧打印一次状态


# ---------------- 基础初始化 ----------------
def open_camera():
    # 按目标分辨率打开摄像头，返回 camera 对象
    return camera.Camera(WIDTH, HEIGHT)


def get_images(cam):
    # 采集一帧，转灰度图，并生成用于调试显示的二值图
    # 关键: binary() 默认 copy=False 会原地修改 gray！必须 copy=True，
    # 否则后续 find_blobs 在被改写的二值图上检测，阈值会把
    # 黑色背景当成目标（线已变成白色255，反而不在阈值内）
    # 返回 (彩色图, 灰度图, 二值图)，三张图都基于同一帧
    img = cam.read()
    gray = img.to_format(image.Format.FMT_GRAYSCALE)
    bin_img = gray.binary([(GRAY_MIN, GRAY_MAX)], copy=True)
    return img, gray, bin_img


# ---------------- 几何与日志工具 ----------------
def seg_str(s):
    # 线段的紧凑描述，用于日志输出
    return "(%d,%d)-(%d,%d) len=%d" % (s.x1(), s.y1(), s.x2(), s.y2(), s.length())


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
    # 返回列表中最长的线段，空列表返回 None
    # （绝不假设第一条线段就是最长的）
    best = None
    best_len = -1
    for s in segs:
        if s.length() > best_len:
            best_len = s.length()
            best = s
    return best
