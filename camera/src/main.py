# main.py - 项目主入口，每次运行本文件
# 在 MaixVision 中打开 src 所在项目文件夹，点击「运行项目」（不是「运行当前文件」），
# 整个文件夹会打包发送到设备，本文件通过 import 引用其他模块。
# 用 TASK 选择本次要执行的任务，改完保存再运行即可。
from maix import app
import xunji
import fint_t

TASK = "t"      # "line": 黑线循迹 | "seg": 线段可视化调试 | "t": 倒T检测

if not app.need_exit():
    if TASK == "line":
        # 黑线循迹：屏幕显示三个ROI、线心十字和 error
        xunji.run()
    elif TASK == "seg":
        # 线段可视化：绿色画出 find_line_segments 在灰度图和二值图上的结果
        fint_t.run_seg_test()
    elif TASK == "t":
        # 倒T检测：T_DEBUG_VERBOSE=True 时输出分阶段判定日志
        fint_t.run_t_test()
    else:
        print("unknown TASK: %s" % TASK)
