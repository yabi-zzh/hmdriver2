# -*- coding: utf-8 -*-

"""
设备管理器模块

提供统一的设备发现、状态管理和缓存功能
"""

import time
from typing import List, Optional, Set
from . import logger
from .hdc import _execute_command, _build_hdc_prefix
from .exception import HdcError


class DeviceManager:
    """
    设备管理器单例
    
    统一管理所有设备的发现、状态缓存和变更检测
    避免重复的设备查询调用，提供高效的设备管理
    """
    
    _instance: Optional['DeviceManager'] = None
    
    def __new__(cls) -> 'DeviceManager':
        """确保单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化设备管理器（仅执行一次）"""
        if self._initialized:
            return
            
        self._devices: List[str] = []
        self._last_update: float = 0
        self._cache_duration: float = 5.0  # 缓存5秒
        self._hdc_prefix = _build_hdc_prefix()
        self._initialized = True
        
        logger.debug("DeviceManager 初始化完成")
    
    def get_devices(self, force_refresh: bool = False) -> List[str]:
        """
        获取设备列表
        
        Args:
            force_refresh: 是否强制刷新，忽略缓存
            
        Returns:
            List[str]: 设备序列号列表
            
        Raises:
            HdcError: HDC 命令执行失败
        """
        current_time = time.time()
        
        # 检查是否需要更新
        if force_refresh or not self._devices or (current_time - self._last_update) > self._cache_duration:
            self._refresh_devices()
            
        return self._devices.copy()
    
    def _refresh_devices(self):
        """刷新设备列表"""
        try:
            result = _execute_command(f"{self._hdc_prefix} list targets")
            
            if result.exit_code != 0:
                raise HdcError("HDC 错误", result.error)
            
            devices = []
            if result.output:
                lines = result.output.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if line and 'Empty' not in line:
                        devices.append(line)
            
            # 检测设备变更
            old_devices = set(self._devices)
            new_devices = set(devices)
            
            added = new_devices - old_devices
            removed = old_devices - new_devices
            
            if added:
                logger.debug(f"检测到新设备: {list(added)}")
            if removed:
                logger.debug(f"设备已断开: {list(removed)}")
            
            self._devices = devices
            self._last_update = time.time()
            
        except Exception as e:
            logger.error(f"刷新设备列表失败: {e}")
            raise
    
    def has_device(self, serial: str, auto_refresh: bool = True) -> bool:
        """
        检查指定设备是否存在
        
        Args:
            serial: 设备序列号
            auto_refresh: 如果设备不存在，是否自动刷新设备列表
            
        Returns:
            bool: 设备存在返回 True
        """
        devices = self.get_devices()
        
        if serial in devices:
            return True
            
        if auto_refresh:
            # 设备不存在时强制刷新一次
            devices = self.get_devices(force_refresh=True)
            return serial in devices
            
        return False
    
    def get_first_device(self) -> Optional[str]:
        """
        获取第一个可用设备
        
        Returns:
            Optional[str]: 第一个设备序列号，没有设备时返回 None
        """
        devices = self.get_devices()
        return devices[0] if devices else None
    
    def set_cache_duration(self, duration: float):
        """设置缓存持续时间（秒）"""
        self._cache_duration = max(0.1, duration)
        logger.debug(f"设备缓存时间已设置为 {self._cache_duration} 秒")


# 全局单例实例
device_manager = DeviceManager()
