from dataclasses import dataclass
from src.data_elements.data_element import DataElement


@dataclass
class SignalElement(DataElement):
    value: int
