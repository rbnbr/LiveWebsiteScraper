import datetime
from dataclasses import dataclass


@dataclass
class DataElement:
    timestamp: datetime.datetime
