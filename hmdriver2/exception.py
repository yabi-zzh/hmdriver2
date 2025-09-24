# -*- coding: utf-8 -*-

class ElementNotFoundError(Exception):
    pass


class ElementFoundTimeout(Exception):
    pass


class XmlElementNotFoundError(Exception):
    pass


class HmDriverError(Exception):
    pass


class DeviceNotFoundError(Exception):
    pass


class HdcError(Exception):
    pass


class InvokeHypiumError(Exception):
    pass


class InvokeCaptures(Exception):
    pass


class InjectGestureError(Exception):
    pass


class ScreenRecordError(Exception):
    pass


class WebDriverError(Exception):
    """WebDriver 相关错误的基类"""
    pass


class WebDriverSetupError(WebDriverError):
    """WebDriver 设置错误"""
    pass


class WebDriverConnectionError(WebDriverError):
    """WebDriver 连接错误"""
    pass


class ChromeDriverError(WebDriverError):
    """ChromeDriver 进程相关错误"""
    pass


class WebViewNotFoundError(WebDriverError):
    """WebView 未找到错误"""
    pass
