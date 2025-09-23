#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HMDriver2 使用示例：两种清理方式和正则用法
"""

from hmdriver2 import driver
from hmdriver2._uiobject import Match


def demo_manual_cleanup():
    """方式1: 手动清理"""
    d = None
    try:
        d = driver.Driver()
        print(f"设备: {d.serial}")
        
        # 基本操作
        d.screenshot("screenshot.jpg")
        d.click(100, 200)
        
        # 正则查找
        element = d(text=("^设置.*", Match.RE))  # 以"设置"开头
        print(f"设置元素: {element.exists()}")
        
    finally:
        if d:
            d.close()
            print("手动清理完成")


def demo_context_manager():
    """方式2: 上下文管理器 (推荐)"""
    with driver.Driver() as d:
        print(f"设备: {d.serial}")
        
        width, height = d.display_size
        d.click(width // 2, height // 2)
        
        # 正则模式
        patterns = [
            ("^确定$", "精确匹配"),
            (r"\d+", "包含数字"),
            (r"[\u4e00-\u9fa5]+", "中文字符"),
            (r"(确定|取消)", "多选分支")
        ]
        
        for pattern, desc in patterns:
            element = d(text=(pattern, Match.RE))
            print(f"{desc}: {element.exists()}")
        
        # 不同匹配模式
        d(text="设置")                    # 完全匹配
        d(text=("设置", Match.IN))        # 包含匹配  
        d(text=("设置.*", Match.RE))      # 正则匹配
        
    print("自动清理完成")


if __name__ == "__main__":
    print("HMDriver2 清理方式和正则用法")
    print("-" * 30)
    
    demo_manual_cleanup()
    print()
    demo_context_manager()
    
    print("\n推荐使用 with 语句")
