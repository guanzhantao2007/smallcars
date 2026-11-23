# ============================================================================
#  smart_cars —— STM32F407VET6 双轮差速小车（速度环 / 角度环）
#
#  构建：
#    cmake -B build -G Ninja -DCMAKE_TOOLCHAIN_FILE=cmake/gcc-arm-none-eabi.cmake
#    cmake --build build
#  产物：
#    build/smart_cars.elf / .hex / .bin / .map
#
#  设计说明：
#   - 源文件用 GLOB + CONFIGURE_DEPENDS：新增 .c 不用改本文件，Ninja 会自动重新配置。
#     这是本工程明确要的（原 Keil 工程加文件必须手改 uvprojx，容易忘）。
#   - 不定义任何业务宏在这里，业务配置全在代码里，避免两处真值。
# ============================================================================

cmake_minimum_required(VERSION 3.20)

project(smart_cars C ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Debug CACHE STRING "Debug / Release" FORCE)
endif()

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})

# ---------------------------------------------------------------- 架构参数
set(MCU_ARCH -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard)
set(MCU_DEFS  USE_HAL_DRIVER STM32F407xx)

# ---------------------------------------------------------------- 源文件
file(GLOB CORE_SOURCES CONFIGURE_DEPENDS ${CMAKE_SOURCE_DIR}/Core/Src/*.c)
file(GLOB HAL_SOURCES  CONFIGURE_DEPENDS ${CMAKE_SOURCE_DIR}/Drivers/STM32F4xx_HAL_Driver/Src/*.c)
set(STARTUP_SOURCE ${CMAKE_SOURCE_DIR}/Core/Startup/startup_stm32f407xx.s)
set(LINKER_SCRIPT  ${CMAKE_SOURCE_DIR}/STM32F407VETX_FLASH.ld)

add_executable(${PROJECT_NAME}
  ${CORE_SOURCES}
  ${HAL_SOURCES}
  ${STARTUP_SOURCE}
)

# ---------------------------------------------------------------- 头文件路径
target_include_directories(${PROJECT_NAME} PRIVATE
  ${CMAKE_SOURCE_DIR}/Core/Inc
  ${CMAKE_SOURCE_DIR}/Drivers/STM32F4xx_HAL_Driver/Inc
  ${CMAKE_SOURCE_DIR}/Drivers/STM32F4xx_HAL_Driver/Inc/Legacy
  ${CMAKE_SOURCE_DIR}/Drivers/CMSIS/Device/ST/STM32F4xx/Include
  ${CMAKE_SOURCE_DIR}/Drivers/CMSIS/Include
)

target_compile_definitions(${PROJECT_NAME} PRIVATE ${MCU_DEFS})

target_compile_options(${PROJECT_NAME} PRIVATE
  ${MCU_ARCH}
  -Wall -Wextra
  -ffunction-sections -fdata-sections
  -fno-common
)

if(CMAKE_BUILD_TYPE STREQUAL "Debug")
  target_compile_options(${PROJECT_NAME} PRIVATE -Og -g3 -gdwarf-2)
else()
  target_compile_options(${PROJECT_NAME} PRIVATE -O2 -g)
endif()

# 启动文件按汇编处理，参数一致
set_source_files_properties(${STARTUP_SOURCE} PROPERTIES COMPILE_OPTIONS "${MCU_ARCH}")

# ---------------------------------------------------------------- 链接
target_link_options(${PROJECT_NAME} PRIVATE
  ${MCU_ARCH}
  -T${LINKER_SCRIPT}
  -specs=nano.specs
  -specs=nosys.specs
  -Wl,--gc-sections
  -Wl,-Map=${CMAKE_BINARY_DIR}/${PROJECT_NAME}.map
  -Wl,--print-memory-usage
  -Wl,--no-warn-rwx-segments
)

# 数学库必须用 target_link_libraries，不能用 target_link_options。
# 否则 -lm 会排到 .obj 前面，链接器左→右解析时还没遇到 atan2f/sqrtf，
# 就会报 undefined reference。
target_link_libraries(${PROJECT_NAME} PRIVATE m)

# ---------------------------------------------------------------- 后处理
# 注意：本工程路径含中文（代码库/（renxun first）。
# objcopy 经 cmd.exe 传参时中文会被转成 GBK 乱码，导致 "No such file or directory"。
# 所以这里全部用相对文件名 + WORKING_DIRECTORY，绝不传绝对路径。
set_target_properties(${PROJECT_NAME} PROPERTIES SUFFIX ".elf")

add_custom_command(TARGET ${PROJECT_NAME} POST_BUILD
  COMMAND ${CMAKE_OBJCOPY} -O ihex   $<TARGET_FILE_NAME:${PROJECT_NAME}> ${PROJECT_NAME}.hex
  COMMAND ${CMAKE_OBJCOPY} -O binary $<TARGET_FILE_NAME:${PROJECT_NAME}> ${PROJECT_NAME}.bin
  COMMAND ${CMAKE_SIZE} $<TARGET_FILE_NAME:${PROJECT_NAME}>
  WORKING_DIRECTORY ${CMAKE_BINARY_DIR}
  COMMENT "生成 .hex / .bin 并打印尺寸"
)
