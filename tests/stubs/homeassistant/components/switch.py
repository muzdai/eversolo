class SwitchDeviceClass:
    SWITCH = "switch"
    OUTLET = "outlet"
class SwitchEntity:
    def async_write_ha_state(self): self.writes = getattr(self, "writes", 0) + 1
