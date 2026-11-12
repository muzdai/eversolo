ConfigFlowResult = dict
class ConfigEntry:
    def __init__(self, entry_id, title, data):
        self.entry_id, self.title, self.data, self.options = entry_id, title, data, {}
        self.unique_id = None
    def async_on_unload(self, fn): self.__dict__.setdefault("unloads", []).append(fn)
class AbortFlow(Exception):
    def __init__(self, reason): super().__init__(reason); self.reason = reason
class ConfigFlow:
    _existing = []  # list of ConfigEntry-like (unique_id, data)
    def __init_subclass__(cls, domain=None, **kw): super().__init_subclass__(**kw); cls.domain = domain
    def __init__(self): pass
    @property
    def unique_id(self): return getattr(self, "_uid", None)
    async def async_set_unique_id(self, uid, raise_on_progress=True): self._uid = uid
    def _abort_if_unique_id_configured(self, updates=None):
        for uid, data in self._existing:
            if uid == self.unique_id: raise AbortFlow("already_configured")
    def _async_abort_entries_match(self, match):
        for uid, data in self._existing:
            if all(data.get(k) == v for k, v in match.items()): raise AbortFlow("already_configured")
    _entries = []
    def _async_current_entries(self): return list(self._entries)
    def async_abort(self, reason): return {"type": "abort", "reason": reason}
    def async_show_form(self, step_id, data_schema=None, errors=None, description_placeholders=None):
        return {"type": "form", "step_id": step_id, "errors": errors or {}, "placeholders": description_placeholders, "schema": data_schema}
    def async_create_entry(self, title, data):
        return {"type": "create_entry", "title": title, "data": data, "unique_id": self.unique_id}
class OptionsFlow:
    pass
