#!/bin/bash

# =============================================================================
# hmdriver2 自动化安装脚本 - 三端通用安装工具
# 支持 Linux, macOS, Windows (Git Bash/WSL)
# =============================================================================

set -e  # 遇到错误立即退出

# 颜色定义（加粗和亮色）
RED='\033[1;31m'      # 亮红色
GREEN='\033[1;32m'    # 亮绿色  
YELLOW='\033[1;33m'   # 亮黄色
BLUE='\033[1;34m'     # 亮蓝色
CYAN='\033[1;36m'     # 亮青色
GRAY='\033[0;37m'     # 灰色
NC='\033[0m'          # 无颜色

# 简化图标
SUCCESS="[✓]"
ERROR="[✗]"  
WARNING="[!]"
INFO="[i]"

# 全局变量
PYTHON_CMD=""
PIP_CMD=""
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# =============================================================================
# 工具函数
# =============================================================================

print_banner() {
    echo -e "${CYAN}"
    echo "================================================================="
    echo -e "               ${GREEN}hmdriver2 自动化安装工具${CYAN}"
    echo -e "             ${GRAY}三端通用 (Linux/macOS/Windows)${CYAN}"
    echo "================================================================="
    echo -e "${NC}"
}

print_step() {
    echo -e "${BLUE}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}${SUCCESS} $1${NC}"
}

print_error() {
    echo -e "${RED}${ERROR} $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}${WARNING} $1${NC}"
}

print_info() {
    echo -e "${CYAN}${INFO} $1${NC}"
}

# 检测操作系统
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "Linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macOS"
    elif [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
        echo "Windows"
    else
        echo "Unknown"
    fi
}

# 检测Python命令
detect_python() {
    local os_type=$(detect_os)
    
    # 在Windows上，优先使用python而不是python3
    if [[ "$os_type" == "Windows" ]] && command -v python &> /dev/null; then
        # 检查Python版本
        local version=$(python --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
        local major=$(echo $version | cut -d. -f1)
        if [[ $major -ge 3 ]]; then
            PYTHON_CMD="python"
            PIP_CMD="pip"
            return 0
        fi
    fi
    
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
        PIP_CMD="pip3"
    elif command -v python &> /dev/null; then
        # 检查Python版本
        local version=$(python --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
        local major=$(echo $version | cut -d. -f1)
        if [[ $major -ge 3 ]]; then
            PYTHON_CMD="python"
            PIP_CMD="pip"
        else
            return 1
        fi
    else
        return 1
    fi
    
    return 0
}

# 检查Python版本
check_python_version() {
    local version=$($PYTHON_CMD --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
    local major=$(echo $version | cut -d. -f1)
    local minor=$(echo $version | cut -d. -f2)
    
    if [[ $major -lt 3 ]] || [[ $major -eq 3 && $minor -lt 8 ]]; then
        print_error "Python版本过低: $version (需要 >= 3.8)"
        return 1
    fi
    
    print_success "Python版本检查通过: $version"
    return 0
}

# 获取项目版本
get_project_version() {
    local version
    if [[ -f "$SCRIPT_DIR/pyproject.toml" ]]; then
        version=$(grep '^version = ' "$SCRIPT_DIR/pyproject.toml" | sed 's/version = "\(.*\)"/\1/' | tr -d '"')
        if [[ -n "$version" ]]; then
            echo "$version"
            return 0
        fi
    fi
    echo "unknown"
    return 1
}

# 检查项目文件
check_project_files() {
    if [[ ! -f "$SCRIPT_DIR/pyproject.toml" ]]; then
        print_error "未找到 pyproject.toml，请确保在项目根目录运行此脚本"
        return 1
    fi
    
    if [[ ! -d "$SCRIPT_DIR/hmdriver2" ]]; then
        print_error "未找到 hmdriver2 源码目录"
        return 1
    fi
    
    local project_version=$(get_project_version)
    print_success "项目文件检查通过"
    print_info "项目版本: $project_version"
    
    return 0
}

# 安装依赖
install_dependencies() {
    print_step "安装基础依赖..."
    
    if $PIP_CMD install "lxml>=5.3.0"; then
        print_success "基础依赖安装完成"
        return 0
    else
        print_error "基础依赖安装失败"
        return 1
    fi
}

# 检查并处理已安装的hmdriver2
check_and_handle_existing() {
    print_step "检查已安装的hmdriver2..."
    
    # 检查是否通过pip安装
    local pip_info
    pip_info=$($PIP_CMD show hmdriver2 2>/dev/null)
    
    if [[ -n "$pip_info" ]]; then
        local version=$(echo "$pip_info" | grep "^Version:" | cut -d' ' -f2)
        print_warning "发现已安装的hmdriver2 (版本: ${version:-unknown})"
        print_info "将替换为当前源码版本"
        
        # 卸载现有版本
        if $PIP_CMD uninstall hmdriver2 -y &>/dev/null; then
            print_success "原版本卸载完成"
        else
            print_warning "卸载时出现问题，但会继续安装"
        fi
    else
        print_info "未发现pip安装的hmdriver2，将进行全新安装"
    fi
    
    return 0
}

# 从源码安装
install_from_source() {
    print_step "从源码构建并安装..."
    
    cd "$SCRIPT_DIR"
    
    # 安装构建工具
    print_info "安装构建工具..."
    if ! $PIP_CMD install build &>/dev/null; then
        print_error "安装构建工具失败"
        return 1
    fi
    
    # 构建wheel包
    print_info "构建独立安装包..."
    if $PYTHON_CMD -m build &>/dev/null; then
        print_success "构建完成"
        
        # 查找生成的wheel文件
        local wheel_file=$(find dist -name "*.whl" -type f | head -1)
        if [[ -n "$wheel_file" ]]; then
            print_info "安装独立版本..."
            if $PIP_CMD install "$wheel_file" --force-reinstall; then
                print_success "独立版本安装完成"
                
                # 清理构建文件
                rm -rf build/ dist/ *.egg-info/ 2>/dev/null
                return 0
            else
                print_error "独立版本安装失败"
                return 1
            fi
        else
            print_error "未找到构建的wheel文件"
            return 1
        fi
    else
        print_error "构建wheel包失败，请检查项目配置"
        return 1
    fi
}

# 验证安装
verify_installation() {
    print_step "验证安装..."
    
    local result
    result=$($PYTHON_CMD -c "
import os
import sys
import tempfile

# 保存原始工作目录
original_cwd = os.getcwd()

try:
    # 创建临时目录并切换到该目录
    temp_dir = tempfile.mkdtemp()
    os.chdir(temp_dir)
    
    try:
        # 确保不导入当前项目中的hmdriver2
        import hmdriver2
        print('SUCCESS')
        print(f'版本: {getattr(hmdriver2, \"__version__\", \"unknown\")}')
        print(f'路径: {hmdriver2.__file__}')
        
        # 检查是否在site-packages中
        if 'site-packages' in hmdriver2.__file__:
            print('位置: site-packages (正确)')
        else:
            print('位置: 非site-packages (可能有问题)')
            
    finally:
        # 恢复原始工作目录
        os.chdir(original_cwd)
        
        # 尝试清理临时目录，失败也不影响验证结果
        try:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
        except:
            pass  # 忽略清理错误

except ImportError as e:
    print(f'IMPORT_ERROR: {e}')
except Exception as e:
    print(f'OTHER_ERROR: {e}')
" 2>&1)
    
    if echo "$result" | grep -q "SUCCESS"; then
        print_success "安装验证通过"
        echo -e "${GREEN}$result${NC}" | grep -v "SUCCESS"
        
        # 额外检查：确认安装在site-packages
        if echo "$result" | grep -q "site-packages"; then
            print_success "✅ 已安装到site-packages，可在任意项目中使用"
        else
            print_warning "⚠️ 安装位置可能有问题，建议检查Python环境"
        fi
        return 0
    else
        print_error "安装验证失败"
        echo -e "${RED}$result${NC}"
        return 1
    fi
}


# 显示使用说明
show_usage_info() {
    local project_version=$(get_project_version)
    
    # 获取Python解释器的完整路径
    local python_full_path
    python_full_path=$($PYTHON_CMD -c "import sys; print(sys.executable)" 2>/dev/null)
    
    echo ""
    echo -e "${CYAN}${INFO} 重要提醒:${NC}"
    echo -e "     ${RED}在其他项目中必须使用此Python解释器:${NC}"
    echo -e "     ${YELLOW}${python_full_path:-$PYTHON_CMD}${NC}"
    echo ""
    
    echo -e "${GREEN}${SUCCESS} 独立版本 v$project_version 安装完成！现在可以在任意项目中使用 hmdriver2${NC}"
}

# 清理函数
cleanup() {
    if [[ $? -ne 0 ]]; then
        print_error "安装失败"
        print_info "你可以尝试重新运行脚本或安装发布版本: pip install hmdriver2"
    fi
}


# =============================================================================
# 主程序
# =============================================================================

main() {
    # 检查命令行参数
    if [[ -n "${1:-}" ]]; then
        print_error "此脚本不需要任何参数，直接运行即可"
        print_info "用法: $0"
        exit 1
    fi
    
    # 设置错误处理
    trap cleanup EXIT
    
    print_banner
    
    print_info "操作系统: $(detect_os)"
    
    # 1. 检测Python环境
    print_step "检测Python环境..."
    if ! detect_python; then
        print_error "未找到Python 3.8+，请先安装Python"
        exit 1
    fi
    
    print_success "Python命令: $PYTHON_CMD"
    print_success "Pip命令: $PIP_CMD"
    
    # 2. 检查Python版本
    if ! check_python_version; then
        exit 1
    fi
    
    # 3. 检查项目文件
    if ! check_project_files; then
        exit 1
    fi
    
    # 4. 确认安装
    echo ""
    local project_version=$(get_project_version)
    echo -e "${CYAN}─────────────────────────────────────────────────────────────${NC}"
    print_info "准备安装hmdriver2独立版本 ${GREEN}v$project_version${NC}"
    print_warning "这将替换任何现有的hmdriver2安装"
    echo -e "${CYAN}─────────────────────────────────────────────────────────────${NC}"
    
    read -p "$(echo -e ${YELLOW}"确认继续安装？(y/N): "${NC})" confirm_install
    if [[ ! "$confirm_install" =~ ^[Yy]$ ]]; then
        print_info "安装已取消"
        exit 0
    fi
    
    echo ""
    print_step "开始安装..."
    
    # 5. 检查并处理已安装版本
    check_and_handle_existing
    
    # 6. 安装依赖
    if ! install_dependencies; then
        exit 1
    fi
    
    # 7. 从源码安装
    if ! install_from_source; then
        exit 1
    fi
    
    # 8. 验证安装
    if ! verify_installation; then
        exit 1
    fi
    
    # 9. 显示使用说明
    show_usage_info
    
    # 禁用错误处理，安装成功
    trap - EXIT
}

# 运行主程序
main "$@"
