class UpdateFailed(Exception): pass
class DataUpdateCoordinator:
    def __class_getitem__(cls, item): return cls
    def __init__(self, hass, logger, name=None, update_interval=None, request_refresh_debouncer=None):
        self.debouncer = request_refresh_debouncer
        self.hass, self.logger, self.name, self.update_interval = hass, logger, name, update_interval
        self.data = None; self.last_update_success = True; self.listeners = 0; self.refreshes = 0
    async def async_refresh(self):
        try:
            self.data = await self._async_update_data(); self.last_update_success = True
        except UpdateFailed:
            self.last_update_success = False
    async def async_request_refresh(self):
        self.refreshes += 1; await self.async_refresh()
    def async_update_listeners(self):
        self.listeners += 1
        for cb in list(getattr(self, "_cbs", [])): cb()
    def async_add_listener(self, cb):
        self.__dict__.setdefault("_cbs", []).append(cb)
        return lambda: self._cbs.remove(cb)
    def async_set_updated_data(self, data):
        self.data = data; self.last_update_success = True; self.listeners += 1
class CoordinatorEntity:
    def __class_getitem__(cls, item): return cls
    def __init__(self, coordinator): self.coordinator = coordinator
    @property
    def available(self): return self.coordinator.last_update_success
