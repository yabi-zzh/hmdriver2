# hmdriver2 自动化安装脚本

## 概述

`install_hmdriver2.sh` 是一个自动化安装脚本，用于安装 hmdriver2 的最新源码编译版本到 Python 的 site-packages 目录，让你可以在任意项目中使用。

## 核心功能

- **独立安装** - 安装到site-packages，可在任意项目中使用
- **智能替换** - 自动检测并替换已有版本
- **跨平台支持** - Linux、macOS、Windows (Git Bash/WSL)
- **自动验证** - 确保安装到正确位置

## 重要：Python环境选择

### **关键原则：安装时使用的Python = 其他项目使用的Python**

```bash
# 1. 确认你在其他项目中使用的Python解释器
which python        # Linux/macOS
where python        # Windows

# 2. 使用相同的Python运行安装脚本
python --version    # 确认版本一致
bash install_hmdriver2.sh
```

## 安装步骤

### 1. 下载项目
```bash
git clone https://github.com/your-repo/hmdriver2.git
cd hmdriver2
```

### 2. 运行安装脚本
```bash
bash install_hmdriver2.sh
```

### 3. 确认安装
在提示时输入 `y` 确认安装

## 安装完成后的输出

安装成功后，脚本会显示：

```bash
[i] 重要提醒:
     在其他项目中必须使用此Python解释器:
     C:\Users\zzh\AppData\Local\Programs\Python\Python312\python.exe

[✓] 独立版本 v1.5.0 安装完成！现在可以在任意项目中使用 hmdriver2
```

### **关键信息说明**

**脚本显示的Python解释器路径非常重要！**

- 这是安装hmdriver2的Python解释器
- 在其他项目中必须使用相同的解释器
- IDE项目设置中也要选择这个解释器

## 验证安装

安装完成后，验证是否成功：

```bash
# 方法1：检查pip包列表
pip show hmdriver2

# 方法2：在其他目录测试导入
cd /tmp  # 或任意其他目录
python -c "import hmdriver2; print(f'版本: {hmdriver2.__version__}')"
```

## 常见问题

### Q: 在其他项目中导入失败？

**A**: 最常见原因是Python解释器不一致：

1. **检查Python解释器**：确保使用安装脚本输出的解释器路径
2. **IDE设置**：
   - **PyCharm**: `File → Settings → Project → Python Interpreter`
   - **VSCode**: `Ctrl+Shift+P → Python: Select Interpreter`
3. **验证安装**：运行 `pip show hmdriver2`

### Q: 如何确认使用了正确的Python？

**A**: 比对解释器路径：

```bash
# 查看当前Python解释器
python -c "import sys; print(sys.executable)"

# 应该与安装脚本输出的路径一致
```

### Q: Windows用户注意事项

**A**: 
- 必须使用 **Git Bash** 或 **WSL** 运行脚本
- 如遇权限问题，以管理员身份运行Git Bash
- 确保Python已正确安装并在PATH中

### Q: 如何回到发布版本？

**A**: 
```bash
pip uninstall hmdriver2
pip install hmdriver2
```

---
