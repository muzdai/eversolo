SCHEDULED = []
def async_call_later(hass, delay, action):
    entry = {"delay": delay, "action": action, "cancelled": False}
    SCHEDULED.append(entry)
    def unsub(): entry["cancelled"] = True
    return unsub
