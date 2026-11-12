class HomeAssistantError(Exception):
    pass
class Unauthorized(HomeAssistantError):
    def __init__(self, context=None, **kw): super().__init__("unauthorized"); self.context = context
