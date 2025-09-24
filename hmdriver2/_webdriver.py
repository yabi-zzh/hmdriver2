# -*- coding: utf-8 -*-

"""
WebDriver 集成模块

提供 HarmonyOS 设备 WebView 调试和 WebDriver 控制功能
"""

__all__ = ['WebDriver']

import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
from typing import List, Optional, Union

from selenium import webdriver
from selenium.webdriver.chromium.options import ChromiumOptions

from hmdriver2 import logger
from hmdriver2.exception import (
    WebDriverSetupError, WebDriverConnectionError,
    ChromeDriverError, WebViewNotFoundError
)
from hmdriver2.hdc import _execute_command
from hmdriver2.utils import FreePort

# WebDriver 相关常量
DEFAULT_PAGE_LOAD_TIMEOUT = 10
DEFAULT_SCRIPT_TIMEOUT = 10
IMPLICIT_WAIT_TIMEOUT = 5
CHROME_DRIVER_LOG_LEVEL_ENV_NAME = "CHROME_DRIVER_LOG_LEVEL"


class WebDriver:
    """
    WebDriver 管理类
    
    提供 HarmonyOS 设备上 WebView 调试和控制功能，支持：
    - 自动发现和连接 WebView
    - ChromeDriver 生命周期管理
    - 端口转发和版本适配
    - 多窗口切换和管理
    """

    def __init__(self, driver):
        """
        初始化 WebDriver 管理器
        
        Args:
            driver: hmdriver2 的 Driver 实例
        """

        self._driver = driver
        self._device = driver.hdc
        self._bundle_name: Optional[str] = None
        self._webdriver: Optional[webdriver.Remote] = None
        self._local_port: int = 9222
        self._remote_port: Union[int, str] = 9222
        self._chromedriver_port = 9515
        self._chromedriver_host = f"http://localhost:{self._chromedriver_port}"
        self._domain_socket_prefix = "webview_devtools_remote_"
        self._chrome_log_path = ""
        self._chromedriver_exe_path = ""
        # 缓存 ChromeDriver 路径查询结果
        self._chromedriver_path_cache = {}
        
        # ChromeDriver 配置
        self.enable_chromedriver_log = False  # 默认禁用日志
        self.chromedriver_log_level = "INFO"
        self.backup_chromedriver_log = False  # 默认不备份

    @property
    def driver(self) -> webdriver.Remote:
        """获取 WebDriver 实例"""
        if self._webdriver is None:
            raise WebDriverConnectionError("WebView 未连接，请先调用 connect() 方法")
        return self._webdriver

    @driver.setter
    def driver(self, value: webdriver.Remote):
        """设置 WebDriver 实例"""
        self._webdriver = value
    
    def configure_chromedriver(self,
                              enable_log: bool = False,
                              log_level: str = "INFO",
                              backup_log: bool = False,
                              port: Optional[int] = None):
        """
        配置 ChromeDriver 选项
        
        Args:
            enable_log: 是否启用 ChromeDriver 日志
            log_level: 日志级别，可选: OFF/SEVERE/WARNING/INFO/DEBUG/ALL
            backup_log: 是否备份 ChromeDriver 日志
            port: ChromeDriver 服务端口，None 表示不修改当前端口
        """
        self.enable_chromedriver_log = enable_log
        self.chromedriver_log_level = log_level.upper()
        self.backup_chromedriver_log = backup_log
        
        if port is not None:
            self._chromedriver_port = port
            self._chromedriver_host = f"http://localhost:{port}"
        
        logger.debug(f"ChromeDriver 配置更新: 日志={enable_log}, 级别={log_level}, 备份={backup_log}, 端口={self._chromedriver_port}")

    def connect(self,
                bundle_name: str,
                remote_port: Optional[Union[int, str]] = None,
                options: Optional[ChromiumOptions] = None,
                chromedriver_version: Optional[int] = None) -> webdriver.Remote:
        """
        连接指定应用的 WebView
        
        Args:
            bundle_name: 应用包名
            remote_port: 远程调试端口（可选）
            options: Chrome 选项配置
            chromedriver_version: 指定 ChromeDriver 版本（可选），如 114、140 等
            
        Returns:
            WebDriver 实例
            
        Example:
            driver = Driver()
            
            # 配置 ChromeDriver（可选，默认已禁用日志）
            driver.webdriver.configure_chromedriver(
                enable_log=True,            # 启用日志（如需要）
                log_level="WARNING",        # 设置日志级别
                backup_log=True,           # 启用日志备份（如需要）
                port=9516                  # 自定义端口（可选，默认9515）
            )
            
            # 连接 WebView（示例包名：华为浏览器）
            wd = driver.webdriver.connect("com.huawei.hmos.browser")
            # 或指定版本
            wd = driver.webdriver.connect("com.huawei.hmos.browser", chromedriver_version=140)
            wd.get("https://www.baidu.com")
        """
        self._bundle_name = bundle_name
        # 只在有活跃连接时才关闭，避免不必要的端口操作
        if self._webdriver is not None:
            self.close()

        self._init_webview(bundle_name, remote_port, options, chromedriver_version)
        return self.driver

    def _init_webview(self,
                      bundle_name: str,
                      remote_port: Optional[Union[int, str]] = None,
                      options: Optional[ChromiumOptions] = None,
                      chromedriver_version: Optional[int] = None):
        """初始化 WebView 连接"""
        try:
            logger.debug(f"连接 WebView: {bundle_name}")

            # 检查 WebView 进程是否存在（最多5秒）
            if not self._check_webview_process(bundle_name, timeout=5):
                raise WebViewNotFoundError(f"未找到应用 {bundle_name} 的 WebView 进程，请确保应用已启动并使用了 WebView")

            # 设置端口转发
            self._setup_port_forward(bundle_name, remote_port)

            # 根据是否指定版本采用不同策略
            if chromedriver_version is not None:
                logger.debug(f"使用用户指定 ChromeDriver 版本: {chromedriver_version}")
                self._init_fixed_chromedriver(chromedriver_version)
            else:
                # 查询 WebView 版本并智能选择 ChromeDriver
                webview_version = self._get_webview_version()
                self._init_auto_chromedriver(webview_version)

            # 准备 Chrome 选项
            if not isinstance(options, ChromiumOptions):
                options = webdriver.ChromeOptions()

            options.add_experimental_option(
                name="debuggerAddress",
                value=f"127.0.0.1:{self._local_port}"
            )

            # 尝试连接 WebDriver
            try:
                self._webdriver = webdriver.Remote(
                    command_executor=self._chromedriver_host,
                    options=options
                )
                logger.debug(f"WebDriver 初始化成功: {self._webdriver}")
            except Exception as error:
                # 日志使用简化的错误信息，异常使用完整信息
                error_msg_short = str(error).split('\n')[0]
                error_msg_full = str(error)
                logger.error(f"连接失败 {self._chromedriver_host}，错误: {error_msg_short}")

                # 检查是否是用户指定版本的连接失败
                if chromedriver_version is not None:
                    # 用户指定了版本，连接失败应该直接报错，不重试
                    logger.error(f"指定的 ChromeDriver 版本 {chromedriver_version} 连接失败，停止重试")
                    self._kill_chromedriver()
                    if self.backup_chromedriver_log:
                        self._backup_chromedriver_log()
                    raise WebDriverConnectionError(f"ChromeDriver {chromedriver_version} 连接失败: {error_msg_full}")

                # 自动检测版本时，获取当前运行的版本进行重试逻辑
                current_version = self._get_chromedriver_version() or 114  # 获取不到时使用默认版本
                logger.debug(f"重新启动 ChromeDriver {current_version}")
                self._kill_chromedriver()
                self._backup_chromedriver_log()

                # 重新获取正确版本的 ChromeDriver 路径并启动
                chromedriver_name = WebDriver._get_chromedriver_name()
                chromedriver_path = self._get_chromedriver_path(current_version, chromedriver_name)
                if not chromedriver_path:
                    raise ChromeDriverError(f"未找到 ChromeDriver 版本 {current_version}")

                self._start_chromedriver(chromedriver_path)

                # 等待ChromeDriver启动并检查健康状态
                self._wait_for_chromedriver_ready(timeout=5)

                # 重新连接
                self._webdriver = webdriver.Remote(
                    command_executor=self._chromedriver_host,
                    options=options
                )

            # 设置超时时间
            self._webdriver.set_page_load_timeout(DEFAULT_PAGE_LOAD_TIMEOUT)
            self._webdriver.set_script_timeout(DEFAULT_SCRIPT_TIMEOUT)
            self._webdriver.implicitly_wait(IMPLICIT_WAIT_TIMEOUT)

            # 窗口信息
            handles = self._webdriver.window_handles
            logger.debug(f"连接成功！共 {len(handles)} 个窗口")

            if handles:
                self._switch_to_visible_window()

        except Exception as error:
            # 收集诊断信息
            forward_status = self._device.list_fport()
            logger.error(f"端口转发状态: {forward_status}")

            # 保留完整错误信息
            error_msg = str(error)

            if self.backup_chromedriver_log:
                self._backup_chromedriver_log()
            raise WebDriverSetupError(f"WebDriver 初始化失败: {error_msg}")

    def _setup_port_forward(self,
                            bundle_name: str,
                            remote_port: Optional[Union[int, str]] = None):
        """设置端口转发"""

        if remote_port is not None:
            self._remote_port = remote_port

            if isinstance(remote_port, int):
                self._check_tcp_port(self._remote_port)
                self._local_port = self._device.forward_port(self._remote_port)
                logger.debug(f"TCP 端口转发: {self._local_port} -> {self._remote_port}")
            else:
                self._local_port = WebDriver._allocate_local_port()
                cmd = f"{self._device.hdc_prefix} -t {self._device.serial} fport tcp:{self._local_port} {remote_port}"
                result = _execute_command(cmd)
                if result.exit_code != 0:
                    raise WebDriverSetupError(f"系统内部端口转发失败: {result.error}")
                logger.debug(f"系统内部端口转发: {self._local_port} -> {remote_port}")

        else:
            # 获取调试工具信息（一次查询，两次使用）
            devtools_info = self._get_devtools_info()

            if self._is_using_domain_socket(devtools_info):
                socket_name = self._find_devtools_socket(bundle_name, devtools_info)
                if socket_name is None:
                    raise WebViewNotFoundError(f"未找到 {bundle_name} 的调试端口")

                self._local_port = WebDriver._allocate_local_port()
                self._remote_port = f"localabstract:{socket_name}"
                cmd = f"{self._device.hdc_prefix} -t {self._device.serial} fport tcp:{self._local_port} {self._remote_port}"
                result = _execute_command(cmd)
                if result.exit_code != 0:
                    raise WebDriverSetupError(f"应用内部端口转发失败: {result.error}")
                logger.debug(f"应用内部端口转发: {self._local_port} -> {self._remote_port}")
            else:
                pass
                self._check_tcp_port(self._remote_port)
                self._local_port = self._device.forward_port(self._remote_port)
                logger.debug(f"默认端口转发: {self._local_port} -> {self._remote_port}")

    
    @staticmethod
    def _allocate_local_port() -> int:
        """分配本地端口"""
        free_port = FreePort()
        return free_port.get()
    
    def _get_version_from_url(self, url: str, pattern: str, timeout: int = 3) -> Optional[int]:
        """从URL获取版本信息"""
        try:
            response = urllib.request.urlopen(url, timeout=timeout)
            text = response.read().decode(encoding="utf-8", errors="ignore")
            match = re.search(pattern, text)
            if match:
                version = int(match.group(1))
                return version
            else:
                return None
        except Exception as e:
            logger.error(f"获取版本失败 {url}: {e}")
            return None
    
    def _get_devtools_info(self, timeout: int = 2) -> Optional[str]:
        """获取调试工具信息"""

        for i in range(timeout):
            try:
                result = self._device.shell(
                    "cat /proc/net/unix | grep devtools",
                    error_raise=False
                )

                if "devtools" in result.output:
                    return result.output

            except Exception as e:
                logger.warning(f"查询调试工具时出错: {e}")

            if i < timeout - 1:  # 最后一次不需要等待
                time.sleep(0.3)

        return None

    def _is_using_domain_socket(self, devtools_info: Optional[str] = None) -> bool:
        """检查是否使用应用内部端口"""
        if devtools_info is None:
            devtools_info = self._get_devtools_info()

        return devtools_info and self._domain_socket_prefix in devtools_info

    def _find_devtools_socket(self,
                              process_name: str,
                              devtools_info: Optional[str] = None,
                              timeout: int = 2) -> Optional[str]:
        """查找调试工具套接字"""

        # 如果没有提供调试工具信息，则获取
        if devtools_info is None:
            devtools_info = self._get_devtools_info(timeout)

        if not devtools_info:
            logger.warning(f"未找到任何调试工具信息")
            return None

        # 解析调试端口
        devtools_ports = []
        for line in devtools_info.split('\n'):
            items = line.split()
            if len(items) >= 1:
                devtools_ports.append(items[-1].strip('@'))


        for i in range(timeout):
            try:
                # 获取进程信息
                process_result = self._device.shell(f"ps -ef | grep {process_name}", error_raise=False)

                # 匹配进程和端口
                for line in process_result.output.split('\n'):
                    items = line.split()
                    if len(items) < 8:
                        continue

                    pid = items[1]
                    actual_process_name = items[7]

                    if process_name not in actual_process_name:
                        continue

                    for port in devtools_ports:
                        if pid in port:
                            logger.debug(f"找到 {process_name} 的调试端口: {port}")
                            return port

            except Exception as e:
                logger.warning(f"查找调试套接字时出错: {e}")

            if i < timeout - 1:  # 最后一次不需要等待
                time.sleep(0.3)

        logger.warning(f"未找到 {process_name} 的调试套接字")
        return None

    def _check_tcp_port(self, port: Union[int, str]):
        """检查 TCP 端口是否开放"""

        try:
            result = self._device.shell(f"netstat -tlnp | grep :{port}", error_raise=False)

            if str(port) not in result.output:
                logger.warning(f"端口 {port} 未开放，请检查应用是否启用了 Web 调试")
                # 不抛出异常，让后续流程尝试连接
            else:
                pass

        except Exception:
            pass
            # 端口检查失败不影响主流程

    def _get_webview_version(self) -> int:
        """获取 WebView 内核版本"""
        url = f"http://localhost:{self._local_port}/json/version"
        version = self._get_version_from_url(url, r'"Browser":\s*"[^/]+/(\d+)', timeout=3)
        if version:
            logger.debug(f"WebView 内核版本: {version}")
            return version

        raise WebDriverConnectionError(
            f"无法获取 WebView 版本信息。请检查：\n"
            f"1. 应用是否已启用 WebView 调试\n"
            f"2. 设备未锁屏且 WebView 界面可见\n"
            f"3. WebView 是否已完全加载"
        )

    def _get_chromedriver_version(self) -> Optional[int]:
        """获取 ChromeDriver 版本"""
        return self._get_version_from_url(f"{self._chromedriver_host}/status", r'"version":\s*"(\d+)', timeout=3)

    def _init_fixed_chromedriver(self, specified_version: int):
        """初始化用户指定版本的 ChromeDriver"""
        # 检查是否有 ChromeDriver 进程运行
        if self._is_chromedriver_running():
            logger.debug("检测到 ChromeDriver 正在运行")
            
            # 获取运行中的 ChromeDriver 版本
            running_version = self._get_chromedriver_version()
            if running_version == specified_version:
                logger.debug(f"运行中的 ChromeDriver 版本 {running_version} 匹配指定版本，复用现有进程")
                return
            else:
                if running_version:
                    logger.debug(f"运行中的版本 {running_version} 与指定版本 {specified_version} 不匹配，重启")
                else:
                    logger.debug("无法获取运行中的版本，重启")
                self._kill_chromedriver()
        else:
            logger.debug("未检测到 ChromeDriver 进程")
        
        # 启动指定版本的 ChromeDriver
        logger.debug(f"启动指定的 ChromeDriver 版本: {specified_version}")
        self._setup_chromedriver(specified_version)

    def _init_auto_chromedriver(self, webview_version: int):
        """自动选择兼容版本的 ChromeDriver"""
        # 检查是否有 ChromeDriver 进程运行
        if self._is_chromedriver_running():
            logger.debug("检测到 ChromeDriver 正在运行")
            
            # 获取运行中的 ChromeDriver 版本
            running_version = self._get_chromedriver_version()
            if running_version:
                logger.debug(f"运行中的 ChromeDriver 版本: {running_version}")
                
                # 检查是否支持当前 WebView 版本
                if self._is_compatible(running_version, webview_version):
                    logger.debug(f"ChromeDriver {running_version} 兼容 WebView {webview_version}，复用现有进程")
                    return
                else:
                    logger.warning(f"ChromeDriver {running_version} 不兼容 WebView {webview_version}，需要重启")
                    self._kill_chromedriver()
            else:
                logger.warning("无法获取运行中的 ChromeDriver 版本，将重启")
                self._kill_chromedriver()
        else:
            logger.debug("未检测到 ChromeDriver 进程")
        
        # 查找本地是否有支持 WebView 版本的 ChromeDriver
        available_versions = self._get_available_chromedriver_versions()
        if not available_versions:
            raise ChromeDriverError("未找到任何本地 ChromeDriver 版本")
        
        # 找到兼容的版本
        compatible_version = None
        for version in sorted(available_versions, reverse=True):
            if self._is_compatible(version, webview_version):
                compatible_version = version
                break
        
        if compatible_version is None:
            raise ChromeDriverError(
                f"不支持 WebView 版本 {webview_version}。\n"
                f"本地版本: {available_versions}\n"
                f"兼容性: ChromeDriver 114(支持114-132), ChromeDriver 140(支持140+)\n"
                f"请下载兼容版本到 assets/web_debug_tools/ 目录"
            )
        
        logger.debug(f"选择 ChromeDriver 版本 {compatible_version} 用于 WebView {webview_version}")
        self._setup_chromedriver(compatible_version)

    def _setup_chromedriver(self, version: int = 114):
        """准备和启动 ChromeDriver"""
        chromedriver_name = WebDriver._get_chromedriver_name()
        chromedriver_path = self._get_chromedriver_path(version, chromedriver_name)


        if chromedriver_path is None:
            raise ChromeDriverError("未找到 ChromeDriver")

        if not os.path.isfile(chromedriver_path):
            raise ChromeDriverError(f"ChromeDriver 文件不存在: {chromedriver_path}")

        if self._is_chromedriver_running():
            logger.debug(f"{chromedriver_name} 正在运行，将在连接失败时重启")
            # 不进行版本检查，直接尝试连接，失败时再处理
        else:
            logger.debug(f"{chromedriver_name} 未运行，启动版本 {version}")
            self._start_chromedriver(chromedriver_path)

    @staticmethod
    def _get_chromedriver_name() -> str:
        """获取 ChromeDriver 可执行文件名"""
        return "chromedriver.exe" if os.name == "nt" else "chromedriver"

    def _get_chromedriver_path(self, version: int, name: str) -> Optional[str]:
        """获取 ChromeDriver 路径（带缓存）

        目录结构要求（请将 chromedriver 放在项目托管目录中）：
        - hmdriver2/assets/web_debug_tools/chromedriver_<版本>/chromedriver[.exe]
          例如：
          - hmdriver2/assets/web_debug_tools/chromedriver_114/chromedriver.exe (Windows)
          - hmdriver2/assets/web_debug_tools/chromedriver_140/chromedriver (Linux/macOS)

        注意：不再从系统 PATH 中查找 chromedriver，只使用项目内置目录。
        """
        cache_key = f"{version}_{name}"
        if cache_key in self._chromedriver_path_cache:
            cached_path = self._chromedriver_path_cache[cache_key]
            if cached_path and os.path.isfile(cached_path):
                return cached_path
            else:
                # 缓存失效，清除
                del self._chromedriver_path_cache[cache_key]
        

        # 查找 ChromeDriver 文件的候选目录
        current_dir = os.path.dirname(os.path.abspath(__file__))

        candidate_dirs = [
            # hmdriver2/assets/web_debug_tools (主要目录)
            os.path.join(current_dir, "assets", "web_debug_tools"),
        ]

        for chromedriver_base_dir in candidate_dirs:

            if not os.path.exists(chromedriver_base_dir):
                continue

            # 尝试精确匹配版本
            chromedriver_dir = os.path.join(chromedriver_base_dir, f"chromedriver_{version}")
            chromedriver_path = os.path.join(chromedriver_dir, name)

            if os.path.isfile(chromedriver_path):
                self._cache_chromedriver_path(version, name, chromedriver_path)
                return chromedriver_path

            # 如果精确版本不存在，查找最接近的版本
            available_versions = []
            try:
                for item in os.listdir(chromedriver_base_dir):
                    if item.startswith("chromedriver_") and os.path.isdir(os.path.join(chromedriver_base_dir, item)):
                        try:
                            ver = int(item.split("_")[1])
                            path = os.path.join(chromedriver_base_dir, item, name)
                            if os.path.isfile(path):
                                available_versions.append((ver, path))
                        except (ValueError, IndexError):
                            continue

                if available_versions:
                    # 使用兼容性规则找到合适的版本
                    available_version_numbers = [ver for ver, path in available_versions]
                    compatible_version = None
                    for ver in sorted(available_version_numbers, reverse=True):
                        if self._is_compatible(ver, version):
                            compatible_version = ver
                            break
                    
                    if compatible_version:
                        # 找到兼容版本对应的路径
                        compatible_path = None
                        for ver, path in available_versions:
                            if ver == compatible_version:
                                compatible_path = path
                                break
                        
                        if compatible_path:
                            logger.debug(
                                f"在 {chromedriver_base_dir} 中使用兼容的 ChromeDriver 版本 {compatible_version} (WebView版本: {version})")
                            self._cache_chromedriver_path(version, name, compatible_path)
                            return compatible_path
                    
                    # 如果没有找到兼容版本，记录可用版本信息
                    available_version_numbers.sort()
                    logger.warning(
                        f"在 {chromedriver_base_dir} 中没有兼容 WebView {version} 的 ChromeDriver，可用版本: {available_version_numbers}")
                    continue

            except OSError:
                continue

        logger.error(f"未找到 ChromeDriver (版本 {version})")
        return None
    
    def _cache_chromedriver_path(self, version: int, name: str, path: str):
        """缓存 ChromeDriver 路径"""
        cache_key = f"{version}_{name}"
        self._chromedriver_path_cache[cache_key] = path

    def _is_chromedriver_running(self) -> bool:
        """检查 ChromeDriver 是否正在运行"""
        process_name = "chromedriver"

        if platform.system() == "Windows":
            try:
                result = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=10)
                return f"{process_name}.exe" in result.stdout
            except Exception as e:
                logger.warning(f"检查进程状态失败: {e}")
                return False
        else:
            try:
                result = subprocess.run(f"ps -A|grep {process_name}", shell=True, capture_output=True, text=True, timeout=10)
                return process_name in result.stdout
            except Exception as e:
                logger.warning(f"检查进程状态失败: {e}")
                return False


    def _kill_process_by_name(self, process_name: str):
        """按名称终止进程"""
        if sys.platform.startswith("win"):
            result = subprocess.run(
                f"taskkill /F /IM {process_name}",
                capture_output=True
            )
        else:
            result = subprocess.run(
                f"kill $(pidof {process_name})",
                capture_output=True,
                shell=True
            )

        echo = ""
        if result.stdout:
            echo = result.stdout.decode('utf-8', errors='ignore')
        if result.stderr:
            echo += result.stderr.decode('utf-8', errors='ignore')

        logger.debug(f"停止 {process_name}: {echo}")

    def _kill_chromedriver(self):
        """终止 ChromeDriver 进程"""
        chromedriver_name = WebDriver._get_chromedriver_name()
        self._kill_process_by_name(chromedriver_name)
        time.sleep(0.5)  # 等待进程终止

    def _start_chromedriver(self, chromedriver_path: str, args: Optional[List[str]] = None):
        """启动 ChromeDriver"""
        # 设置可执行权限（Unix 系统）
        if platform.system() in ["Darwin", "Linux"]:
            os.chmod(chromedriver_path, stat.S_IRWXU)

        if args:
            cmd_list = [chromedriver_path] + args
        else:
            cmd_list = [
                chromedriver_path,
                f"--port={self._chromedriver_port}",
            ]
            
            if self.enable_chromedriver_log:
                temp_log_path = os.path.join(tempfile.gettempdir(), "chromedriver.log")
                cmd_list.extend([
                    f"--log-level={self.chromedriver_log_level}",
                    f"--log-path={temp_log_path}"
                ])
                logger.debug(f"ChromeDriver 日志: {temp_log_path} ({self.chromedriver_log_level})")
                self._chrome_log_path = temp_log_path
            else:
                # 禁用日志时使用 OFF 级别
                cmd_list.append("--log-level=OFF")
                logger.debug("ChromeDriver 日志已禁用")
                self._chrome_log_path = ""

        process = subprocess.Popen(cmd_list)
        logger.debug(f"ChromeDriver 已启动，PID: {process.pid}")
        self._chromedriver_exe_path = chromedriver_path
    
    def _wait_for_chromedriver_ready(self, timeout: int = 5):
        """等待 ChromeDriver 准备就绪"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = urllib.request.urlopen(f"{self._chromedriver_host}/status", timeout=1)
                if response.getcode() == 200:
                    return
            except Exception:
                time.sleep(0.1)  # 短暂等待后重试
                continue
        
        logger.warning(f"ChromeDriver 启动超时 ({timeout}秒)，继续尝试连接")
    
    def _backup_chromedriver_log(self):
        """备份 ChromeDriver 日志"""
        if os.path.exists(self._chrome_log_path):
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_path = f"{self._chrome_log_path}.{timestamp}.bak"
            logger.debug(f"ChromeDriver 日志已备份: {backup_path}")
            shutil.copy(self._chrome_log_path, backup_path)
        else:
            logger.warning("没有 ChromeDriver 日志需要备份")
    
    def _check_webview_process(self, bundle_name: str, timeout: int = 5) -> bool:
        """检查 WebView 进程是否存在"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                result = self._device.shell(f"ps -ef | grep {bundle_name}", error_raise=False)
                if result.output:
                    # 逐行检查，排除 grep 进程本身
                    for line in result.output.split('\n'):
                        if bundle_name in line and 'grep' not in line:
                            logger.debug(f"找到应用进程: {line.strip()}")
                            return True
                time.sleep(0.5)
            except Exception as e:
                logger.warning(f"检查进程时出错: {e}")
                time.sleep(0.5)
        
        logger.error(f"超时 {timeout}s 未找到应用 {bundle_name} 的进程")
        return False
    
    def _check_chromedriver_support(self, version: int) -> bool:
        """检查是否支持指定的 WebView 版本"""
        available_versions = self._get_available_chromedriver_versions()
        
        # 按版本从高到低排序，优先选择高版本
        for chromedriver_version in sorted(available_versions, reverse=True):
            if self._is_compatible(chromedriver_version, version):
                return True
        
        logger.error(f"没有找到支持 WebView 版本 {version} 的 ChromeDriver")
        return False
    
    def _is_compatible(self, chromedriver_version: int, webview_version: int) -> bool:
        """检查 ChromeDriver 版本是否与 WebView 版本兼容"""
        if chromedriver_version == 114:
            return 114 <= webview_version <= 132
        elif chromedriver_version == 140:
            return webview_version >= 140
        else:
            return chromedriver_version >= webview_version
    
    
    def _get_available_chromedriver_versions(self) -> List[int]:
        """
        获取可用的 ChromeDriver 版本列表
        
        Returns:
            List[int]: 版本号列表
        """
        versions = []
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 检查 assets 目录
        assets_dir = os.path.join(current_dir, "assets", "web_debug_tools")
        if os.path.exists(assets_dir):
            try:
                for item in os.listdir(assets_dir):
                    if item.startswith("chromedriver_"):
                        try:
                            version_str = item.replace("chromedriver_", "")
                            version = int(version_str)
                            versions.append(version)
                        except ValueError:
                            continue
            except OSError:
                pass
        
        versions.sort()
        return versions

    def get_all_windows(self, with_details: bool = False):
        """获取所有窗口句柄"""
        if not with_details:
            return self.driver.window_handles

        result = []
        current_handle = self.driver.current_window_handle
        for handle in self.driver.window_handles:
            self.driver.switch_to.window(handle)
            result.append({
                "handle": handle,
                "url": self.driver.current_url,
                "title": self.driver.title,
                "visible": self.driver.execute_script("return document.visibilityState")
            })
        self.driver.switch_to.window(current_handle)
        return result

    def get_current_window(self):
        """获取当前窗口信息"""
        return {
            "handle": self.driver.current_window_handle,
            "url": self.driver.current_url,
            "title": self.driver.title
        }

    def switch_to_visible_window(self, index: int = 0):
        """
        切换到可见窗口
        
        Args:
            index: 窗口索引，支持负数（从后往前）
        """
        org_index = index
        handles = self.driver.window_handles

        if index >= 0:
            window_handles = handles
        else:
            window_handles = list(reversed(handles))
            index = abs(index) - 1

        if index >= len(handles):
            raise ValueError(f"总共 {len(handles)} 个窗口，索引 [{org_index}] 超出范围")

        visible_count = 0
        for handle in window_handles:
            self.driver.switch_to.window(handle)
            visible = self.driver.execute_script("return document.visibilityState")

            if visible == "visible":
                if visible_count == index:
                    return
                visible_count += 1

        logger.warning(f"未找到索引为 [{org_index}] 的可见窗口")

    def _switch_to_visible_window(self):
        """自动切换到最佳窗口（初始化时使用）"""
        handles = self._webdriver.window_handles
        if not handles:
            return
        
        # 查找可见窗口
        visible_handle = None
        for handle in handles:
            try:
                self._webdriver.switch_to.window(handle)
                visibility = self._webdriver.execute_script("return document.visibilityState")
                if visibility == "visible":
                    visible_handle = handle
                    break
            except Exception:
                continue
        
        # 如果找到可见窗口，使用它；否则使用最后一个窗口
        if visible_handle:
            self._webdriver.switch_to.window(visible_handle)
            logger.debug("已切换到可见窗口")
        else:
            # 回退到最后一个窗口（通常是最新的）
            self._webdriver.switch_to.window(handles[-1])
            logger.debug("已切换到最后一个窗口")

    def close(self):
        """关闭 WebDriver 连接"""
        if self._webdriver:
            try:
                # 关闭 WebDriver
                self._webdriver.quit()
                logger.debug("WebDriver 已关闭")
            except Exception:
                pass
            finally:
                self._webdriver = None

        # 清理 ChromeDriver 进程
        try:
            if self._is_chromedriver_running():
                self._kill_chromedriver()
                logger.debug("ChromeDriver 进程已清理")
        except Exception:
            pass

        # 尝试移除端口转发（忽略错误）
        try:
            if hasattr(self, '_local_port') and hasattr(self, '_remote_port'):
                if isinstance(self._remote_port, int):
                    # TCP 端口转发：tcp:local_port tcp:remote_port
                    cmd = f"{self._device.hdc_prefix} -t {self._device.serial} fport rm tcp:{self._local_port} tcp:{self._remote_port}"
                    _execute_command(cmd)
                elif isinstance(self._remote_port, str):
                    # 字符串端口（包括系统内部端口和手动指定的字符串端口）
                    cmd = f"{self._device.hdc_prefix} -t {self._device.serial} fport rm tcp:{self._local_port} {self._remote_port}"
                    _execute_command(cmd)
        except Exception:
            pass

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.close()

    def __getattr__(self, item):
        """代理到 WebDriver 实例"""
        if self._webdriver is None:
            raise WebDriverConnectionError("WebView 未连接，请先调用 connect() 方法")
        return getattr(self._webdriver, item)
