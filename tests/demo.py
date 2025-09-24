#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HMDriver2 使用示例：正则 + WebDriver
"""

import pytest
from hmdriver2.driver import Driver
from hmdriver2._uiobject import Match
from selenium.webdriver.common.by import By


@pytest.fixture
def d():
    """设备连接 fixture"""
    d = Driver("2UCUT24109029868")
    yield d
    d.close()


def test_regex_demo(d):
    """匹配模式示例 - 注意：RE 和 REI 暂时无效"""
    print(f"设备: {d.serial}")
    
    # 四种匹配方式对比
    print(f"完全匹配 EQ: {d(text='设置').exists()}")                    # 默认 EQ 模式
    print(f"包含匹配 IN: {d(text=('设置', Match.IN)).exists()}")
    print(f"开头匹配 SW: {d(text=('设置', Match.SW)).exists()}")         # 以"设置"开头
    print(f"结尾匹配 EW: {d(text=('确定', Match.EW)).exists()}")         # 以"确定"结尾
    
    # 正则匹配示例（暂时无效）
    print(f"正则匹配 RE: {d(text=('设.*', Match.RE)).exists()}")         # 正则模式
    print(f"忽略大小写 REI: {d(text=('SET', Match.REI)).exists()}")      # 忽略大小写
    
    print("匹配模式示例完成（注意：RE 和 REI 功能暂时无效）")


def test_webdriver_demo(d):
    """WebDriver 示例"""
    # 启动浏览器
    d.start_app("com.huawei.hmos.browser")

    # 连接浏览器
    wd = d.webdriver.connect("com.huawei.hmos.browser")
    
    # 访问网页
    wd.get("https://www.baidu.com")
    print(f"页面标题: {wd.title}")
    
    # 查找元素
    search_box = wd.find_element(By.ID, "index-kw")
    search_box.send_keys("HarmonyOS")
    
    # 关闭
    d.webdriver.close()
    print("WebDriver 示例完成")


