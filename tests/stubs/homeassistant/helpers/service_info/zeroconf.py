from dataclasses import dataclass, field
@dataclass
class ZeroconfServiceInfo:
    ip_address: object = None; ip_addresses: list = field(default_factory=list); port: int = None
    hostname: str = ''; type: str = ''; name: str = ''; properties: dict = field(default_factory=dict)
    @property
    def host(self): return str(self.ip_address)
