Let write a tool to gen gcc command based on CMAKE toolchain file (input as path). The tools allow 2 mode (input via argparse argument): compile for C or C++, you can refer get_tool_templates and return 2 template for this.

Tool chain file input example:
# cmake -DCMAKE_TOOLCHAIN_FILE=../ToolChain_arm32.9.2.cmake
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_VERSION arm)

# Specify the cross compilers in the Docker CI image
set(CMAKE_C_COMPILER /opt/gcc-arm-9.2-2019.12-x86_64-arm-none-linux-gnueabihf/bin/arm-none-linux-gnueabihf-gcc)
set(CMAKE_CXX_COMPILER /opt/gcc-arm-9.2-2019.12-x86_64-arm-none-linux-gnueabihf/bin/arm-none-linux-gnueabihf-g++)

set(CMAKE_SYSROOT /opt/armv7at2hf-neon-linux-gnueabi/)
set(CMAKE_FIND_ROOT_PATH /opt/armv7at2hf-neon-linux-gnueabi/)

Output example, keep test_program and file1 file2 as placeholder for input:
/opt/.../g++ [FLAGS] -I. -D_IESA_SUPPORT_ -std=c++17 file1.cpp file2.cpp -lpthread -o test_program