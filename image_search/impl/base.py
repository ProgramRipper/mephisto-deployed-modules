from dataclasses import dataclass


@dataclass
class BaseConfig:
    enabled: bool = True
    max_page: int = 1
