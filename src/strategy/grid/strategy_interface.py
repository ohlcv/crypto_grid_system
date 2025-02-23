# src/strategy/grid/strategy_interface.py
from abc import ABC, abstractmethod
from typing import Optional
from .grid_core import GridData

class StrategyManagerInterface(ABC):
    @abstractmethod
    def get_strategy_data(self, uid: str) -> Optional[GridData]:
        """获取指定 uid 的策略数据"""
        pass