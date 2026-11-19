# task1.py - 第一问主任务：循迹上报 + 倒T顺序计数 + 车位数字识别
#
# 流程（单摄像头循环，一帧图同时喂给三个已验证模块）:
#   每帧: 采集 -> 1) 循迹算误差并发串口  2) 倒T检测(fint_t内含多帧确认)
#         3) 若处于数字窗口内: 裁ROI -> PP-OCR -> 过滤1-6 -> 连续同数字多帧确认
#   状态机:
#     TRACK: 普通循迹。倒T确认 -> 车位序号+1，发 TT+0+Z，进入 DIGIT 窗口
#     DIGIT: 本车位数字识别窗口（直到识别出数字 或 下一个T 或 超时）:
#       - 连续 DIGIT_CONFIRM_FRAMES 帧同一数字 -> 发 CC+数字+车位编号+Z，回 TRACK
#       - 下一个倒T确认时仍无数字 -> 判障碍物，发 CC+N+车位编号+Z，随即开新车位
#       - 超时仍无数字 -> 判障碍物，发 CC+N+车位编号+Z，回 TRACK
# 启动方式: 所有模块初始化完成后显示开始画面，点击屏幕任意位置才开始任务循环
#           （无触摸屏的设备自动开始）
#
# 串口协议（帧尾固定 0x5A = 'Z'，115200 8N1 /dev/ttyS1）:
#   循迹误差:   AA + 误差 + Z   误差=像素偏差，钳位±127，按int8补码发1字节
#   倒T确认:    TT + 0  + Z     TT=两个'T'(0x54 0x54)，中间固定1字节0x00
#   数字识别:   CC + 数字 + 车位编号 + Z   数字=1~6的数值字节
#   障碍物:     CC + N    + 车位编号 + Z   N='N'(0x4E)，表示该车位禁止停车
#
# 本文件不含任何新的检测算法:
#   循迹复用 xunji.xunji_from_images，倒T复用 fint_t.detect_t_confirmed，
#   数字复用 number(PP-OCR) 的 init_ocr/filter_digit/参数；
#   本文件只负责调度、多帧计数、状态机和串口组帧。
# 对外接口: run()（main.py TASK="task1" 时调用）

from maix import camera, display, image, time, app, touchscreen
import camera_config
import xunji
import fint_t
import number
import UASRT

# ---------------- 串口参数 ----------------
UART_BAUDRATE = 115200          # 波特率
UART_DEVICE = "/dev/ttyS1"      # A19=TX, A18=RX

# ---------------- 串口协议常量 ----------------
FRAME_END = 0x5A                # 'Z' 帧尾
HDR_LINE = 0xAA                 # 循迹误差帧头
HDR_SLOT = 0xCC                 # 车位结果帧头（数字/障碍共用）
OBSTACLE_MARK = 0x4E            # 'N' 障碍物（禁止停车）
T_ID1 = 0x54       # "TT" 倒T帧头（两个字符'T'）
T_DATA0 = 0x00                  # TT+0+Z 中间固定的 0 字节

# ---------------- 任务可调参数 ----------------
DIGIT_CONFIRM_FRAMES = 1        # 连续 N 帧识别到同一数字才确认，防单帧误读
DIGIT_TIMEOUT_MS = 25000         # 数字窗口超时，毫秒。占位值！按车位间距和
                                # 车速标定；兜底最后一个车位（其后无下一个T）
LINE_SEND_ONLY_VALID = True     # True: 丢线帧不发误差（STM32自行判丢线）
                                # False: 丢线帧发误差0

STATE_TRACK = 0                 # 状态: 普通循迹（数字窗口关闭）
STATE_DIGIT = 1                 # 状态: 数字识别窗口（刚确认一个倒T）


# ---------------- 串口组帧 ----------------
def send_line_error(serial, error):
    # 循迹帧: AA + 误差 + Z。误差为像素偏差浮点数，钳位到 ±127 后
    # 按 int8 补码编码为 1 字节（负数即按补码存储）
    e = int(round(error))
    if e > 127:
        e = 127
    if e < -127:
        e = -127
    serial.write(bytes([HDR_LINE, e & 0xFF, FRAME_END]))


def send_t_found(serial):
    # 倒T确认帧: TT + 0 + Z
    serial.write(bytes([T_ID1, T_DATA0, FRAME_END]))


def send_slot_result(serial, digit, slot):
    # 车位结果帧: CC + 数字/N + 车位编号 + Z
    # digit 为 "1".."6" 时发数字的数值字节；为 "" 时发 'N' 表示障碍物
    # slot 为车位（倒T）序号，数值字节，从 1 开始
    if digit == "":
        data = OBSTACLE_MARK
    else:
        data = int(digit)
    serial.write(bytes([HDR_SLOT, data, slot, FRAME_END]))


# ---------------- 调试绘制 ----------------
def draw_debug(base, state, slot, l_valid, d_str, d_count, ocr_ms):
    # 画数字 ROI 框和顶部任务状态（倒T的三个ROI框由 fint_t.draw_debug 画）
    x, y, w, h = number.DIGIT_ROI
    if d_count > 0:
        color = image.COLOR_GREEN       # 已有连续识别计数
    elif state == STATE_DIGIT:
        color = image.COLOR_YELLOW      # 窗口开启中
    else:
        color = image.COLOR_WHITE       # 普通循迹
    base.draw_rect(x, y, w, h, color)
    if state == STATE_DIGIT:
        txt = "#%d DIGIT %s %d/%d %dms" % (slot, d_str if d_str else "-",
                                           d_count, DIGIT_CONFIRM_FRAMES, ocr_ms)
    else:
        txt = "#%d TRACK" % slot
    base.draw_string(2, 40, txt, color, scale=2)
    if not l_valid:
        base.draw_string(2, 60, "LINE LOST", image.COLOR_RED, scale=2)


# ---------------- 开始等待画面 ----------------
def wait_for_start(disp, ts):
    # 开始画面: 初始化完成后等待用户点击屏幕，点击任意位置才开始任务
    # 返回 True=已点击开始, False=app 退出
    # ts 为 None 表示设备无触摸屏，直接自动开始
    if ts is None:
        return True
    label = "TAP TO START"
    size = image.string_size(label)
    lw = size.width() * 2            # 下面文字用 scale=2 绘制，尺寸同步乘2
    lh = size.height() * 2
    # 触摸坐标以 disp 尺寸为坐标系，画面用同尺寸创建才能对齐
    w = disp.width()
    h = disp.height()
    lx = (w - lw) // 2
    ly = (h - lh) // 2
    while not app.need_exit():
        x, y, pressed = ts.read()
        img = image.Image(w, h)
        img.draw_string(lx, ly, label, image.COLOR_YELLOW, scale=2)
        if pressed:
            img.draw_string(lx, ly, "START!", image.COLOR_GREEN, scale=2)
            disp.show(img)
            time.sleep_ms(300)       # 点击反馈画面停留 300ms 再进任务
            return True
        if x >= 0 and y >= 0:
            img.draw_circle(x, y, 4, image.COLOR_RED, 2)  # 触摸位置小红圈
        disp.show(img)
        time.sleep_ms(20)            # 触摸轮询频率不宜过高
    return False


# ---------------- 主任务循环 ----------------
def run():
    # 第一问主入口: 初始化摄像头/串口/OCR模型，循环执行
    # 循迹上报 -> 倒T计数 -> 数字窗口识别 -> 结果组帧发送
    serial = UASRT.UART1_init(UART_BAUDRATE, UART_DEVICE)
    try:
        ocr = number.init_ocr()
    except Exception as e:
        print("PP-OCR model load FAILED: %s" % e)
        print("check /root/models/pp_ocr.mud exists and MaixPy >= 4.6")
        return
    # 摄像头格式必须跟随模型输入格式（实测 pp_ocr.mud 为 BGR888，
    # 模型加载日志显示 "input type: bgr"），否则 detect() 会因格式不匹配
    # 报错；分辨率保持项目标准 320x240，detect() 自动缩放裁剪图；
    # 循迹/倒T用的灰度图转换与颜色通道顺序无关，不受影响
    cam = camera.Camera(camera_config.WIDTH, camera_config.HEIGHT,
                        ocr.input_format())
    disp = display.Display()
    fint_t.reset_t_confirm()
    # 触摸屏初始化: 无触摸屏设备(非Pro)自动开始，Pro 上等待点击
    try:
        ts = touchscreen.TouchScreen()
    except Exception as e:
        print("no touchscreen, auto start:", e)
        ts = None
    # 等待屏幕点击: 点击后立即进入任务循环（此时所有模块已就绪）
    if not wait_for_start(disp, ts):
        return
    print("[task1] started, protocol: AA+err+Z | 54 54 00 5A | "
          "CC+digit/N+slot+Z")

    state = STATE_TRACK   # 当前状态机状态
    slot = 0              # 已确认的车位（倒T）序号，从1开始
    d_str = ""            # 数字窗口内最近一帧识别到的数字字符
    d_count = 0           # 连续识别到同一数字的帧数
    deadline = 15000          # 数字窗口超时时刻，ticks_ms 绝对值
    ocr_ms = 0            # 最近一次 OCR 耗时（实测）
    frame = 0
    last_t_valid=False
   # t_last = time.ticks_ms()
    last_t_time=None
    T_MAX_TIME_USE=100
    now_t=None
    while not app.need_exit():
        img, gray, bin_img = camera_config.get_images(cam)

        # (1) 循迹: 复用已验证模块，本帧图像同时供倒T检测使用
        l_valid, error, direction = xunji.xunji_from_images(img, gray, bin_img)
        if l_valid or not LINE_SEND_ONLY_VALID:
            send_line_error(serial, error)

        # (2) 倒T检测: 多帧确认已在 fint_t 内部完成
        t_valid, tx, ty, ratios = fint_t.detect_t_confirmed(bin_img)

        # (3) 数字识别: 仅在数字窗口内运行（OCR较慢，其余时间跳过省CPU）
        d_valid = False
        digit = ""
        score = 0.0
        ocr_ms = 0
        if state == STATE_DIGIT:
            number_img=cam.read()
            crop = number_img.crop(number.DIGIT_ROI[0], number.DIGIT_ROI[1],
                            number.DIGIT_ROI[2], number.DIGIT_ROI[3])
           # t0 = time.ticks_ms()
            objs = ocr.detect(crop, number.DET_THRESH, number.BOX_THRESH)
           # ocr_ms = time.ticks_diff(time.ticks_ms(), t0)
            d_valid, digit, score = number.filter_digit(objs)
            # 多帧确认: 连续同一数字计数，无效帧清零（不复用旧结果）
            if d_valid:
                print("detect number")
                if digit == d_str:
                    d_count += 1
                else:
                    d_str = digit
                    d_count = 1
            else:
                d_str = ""
                d_count = 0
            # 窗口关闭条件1: 数字确认 -> 发 CC+数字+车位编号+Z，回 TRACK
            if d_count >= DIGIT_CONFIRM_FRAMES:
                #send_slot_result(serial, digit, slot)
                #number.draw_debug_number(img, objs, d_valid, digit, score)
                if slot!=4:
                    print(f"number is {digit}")
                    if slot<4:
                        send_slot_result(serial, digit, slot)
                      
                    elif slot>4:
                        send_slot_result(serial, digit, slot-1)
                    state = STATE_TRACK
            # 窗口关闭条件2: 超时 -> 判障碍物，发 CC+N+车位编号+Z，回 TRACK
            elif time.ticks_diff(deadline,time.ticks_ms()) >= 0 or (t_valid and (not last_t_valid)):                
                state = STATE_TRACK
                if slot!=4:
                    if slot<4:
                        print("number is none")
                        send_slot_result(serial, "", slot)
                    elif slot>4:
                        print("number is none")
                        send_slot_result(serial, "", slot-1)
        # (4) 倒T事件: 先关闭旧窗口（若有且无数字->障碍物），再开新车位窗口
        if t_valid and (not last_t_valid):
                if state == STATE_TRACK:
                # 本车位窗口被下一个倒T关闭且无数字 -> 障碍物
                    now_t=time.ticks_ms()
                    if last_t_time is not None:
                        time_use_t=time.ticks_diff(last_t_time,now_t)
                    else: 
                        time_use_t=T_MAX_TIME_USE
                    if time_use_t: 
                        #send_slot_result(serial, "", slot)
                        
                        slot += 1
                      #  send_t_found(serial)
                        state = STATE_DIGIT
                        d_str = ""
                        d_count = 0
                        deadline = time.ticks_ms() + DIGIT_TIMEOUT_MS                        
                        print(f"slot is {slot}")
                        
                        #if last_t_time is not None:
                         #   print("first time, time_use=%d" %time_use_t)
                        last_t_time=now_t
        last_t_valid=t_valid   
            
        # (5) 调试显示: 倒T三ROI框 + 数字ROI框 + 任务状态
        base = bin_img if camera_config.SHOW_BINARY else img
        fint_t.draw_debug_t(base, t_valid, tx, ty, ratios)
       # draw_debug(base, state, slot, l_valid, d_str, d_count, ocr_ms)
        disp.show(base)

       # frame += 1
        #if frame % camera_config.PRINT_INTERVAL == 0:
         #   now = time.ticks_ms()
          #  ms = time.ticks_diff(now, t_last) / camera_config.PRINT_INTERVAL
           # t_last = now
            #st = "DIGIT" if state == STATE_DIGIT else "TRACK"