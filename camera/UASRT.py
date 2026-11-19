
from maix import uart, pinmap, app, time, err

bountrate=115200
device="/dev/ttyS1"

def UART1_init(bountrate:int,device:str):
    # 配置 UART1 引脚
    err.check_raise(
        pinmap.set_pin_function("A19", "UART1_TX"),
        "TX pin setup failed"
    )

    err.check_raise(
        pinmap.set_pin_function("A18", "UART1_RX"),
        "RX pin setup failed"
    )

    # 初始化 UART1
    serial = uart.UART(device, bountrate)

    print("MaixCAM UART1 ready")
    return serial


