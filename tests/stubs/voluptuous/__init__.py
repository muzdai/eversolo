class _Key(str):
    def __new__(cls, key, default=None):
        o = str.__new__(cls, key); o.default = default; return o
def Required(key, default=None, description=None): return _Key(key, default)
def Optional(key, default=None, description=None): return _Key(key, default)
class In:
    def __init__(self, options): self.options = list(options)
    def __call__(self, v):
        if v not in self.options: raise ValueError(v)
        return v
class Schema:
    def __init__(self, schema): self.schema = schema
    def __call__(self, data):
        out = {}
        for k, check in self.schema.items():
            if k in data:
                out[k] = check(data[k]) if callable(check) and not isinstance(check, type) else data[k]
            elif getattr(k, "default", None) is not None:
                out[k] = k.default
        return out
def Coerce(t):
    return lambda v: t(v)
