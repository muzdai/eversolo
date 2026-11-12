COMMANDS = {}
class ActiveConnection:
    def __init__(self):
        self.sent, self.subscriptions = [], {}
    def send_message(self, m): self.sent.append(m)
    def send_result(self, i, r=None): self.sent.append({"id": i, "type": "result", "success": True})
    def send_error(self, i, code, msg): self.sent.append({"id": i, "type": "result", "success": False, "error": code, "message": msg})
def event_message(i, ev): return {"id": i, "type": "event", "event": ev}
def websocket_command(schema):
    def deco(f):
        f._ws_schema = schema
        return f
    return deco
def async_response(f): return f
def async_register_command(hass, handler):
    t = [v for k, v in handler._ws_schema.items() if str(k) == "type"][0]
    COMMANDS[t] = handler
