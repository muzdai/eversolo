class _Entry:
    def __init__(self, ceid): self.config_entry_id = ceid
class _Reg:
    def __init__(self): self.map = {}
    def async_get(self, eid):
        return _Entry(self.map[eid]) if eid in self.map else None
REG = _Reg()
def async_get(hass): return REG
REG.uids = {}
REG.removed = []
def _get_entity_id(domain, platform, uid): return REG.uids.get((domain, platform, uid))
def _remove(eid): REG.removed.append(eid)
REG.async_get_entity_id = _get_entity_id
REG.async_remove = _remove
