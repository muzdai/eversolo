from enum import Enum
class HomeAssistant: pass
class ServiceCall:
    def __init__(self, data, user_id=None):
        self.data = data; self.context = type("Ctx", (), {"user_id": user_id})()
ServiceResponse = dict
class SupportsResponse(Enum):
    NONE='none'; OPTIONAL='optional'; ONLY='only'
def callback(f): return f
CALLBACK_TYPE = object
