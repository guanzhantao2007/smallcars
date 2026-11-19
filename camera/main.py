# main.py - 项目主入口，每次运行本文件
# 在 MaixVision 中打开 src 所在项目文件夹，点击「运行项目」（不是「运行当前文件」），
# 整个文件夹会打包发送到设备，本文件通过 import 引用其他模块。
# 用 TASK 选择本次要执行的任务，改完保存再运行即可。
from maix import app
import xunji
import fint_t
import number
import task1

TASK = "task1"      # "line": 黑线循迹  | "t": 倒T检测 | "number": 数字识别
                    # "task1": 第一问主任务（循迹+倒T+数字+串口）

if not app.need_exit():
    if TASK == "line":
        xunji.run()
    elif TASK == "t":
        fint_t.run()
    elif TASK == "number":
        number.run()
    elif TASK == "task1":
        task1.run()
    else:
        print("unknown TASK: %s" % TASK)
