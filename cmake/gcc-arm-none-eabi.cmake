# ============================================================================
# 交叉编译工具链：arm-none-eabi-gcc
# 用法：cmake -B build -G Ninja -DCMAKE_TOOLCHAIN_FILE=cmake/gcc-arm-none-eabi.cmake
# ============================================================================

set(CMAKE_SYSTEM_NAME      Generic)
set(CMAKE_SYSTEM_PROCESSOR arm)

set(TOOLCHAIN_DIR    "D:/App/gnu-toolchain/bin" CACHE PATH "arm-none-eabi 工具链 bin 目录")
set(TOOLCHAIN_PREFIX "arm-none-eabi-"           CACHE STRING "工具链前缀")

set(CMAKE_C_COMPILER   "${TOOLCHAIN_DIR}/${TOOLCHAIN_PREFIX}gcc.exe")
set(CMAKE_ASM_COMPILER "${TOOLCHAIN_DIR}/${TOOLCHAIN_PREFIX}gcc.exe")
set(CMAKE_OBJCOPY      "${TOOLCHAIN_DIR}/${TOOLCHAIN_PREFIX}objcopy.exe")
set(CMAKE_SIZE         "${TOOLCHAIN_DIR}/${TOOLCHAIN_PREFIX}size.exe")

# 关键：裸机环境试编译无法链接（缺 _write/_sbrk 等），
# 设成只做静态库，CMake 的编译器探测才不会失败。
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
