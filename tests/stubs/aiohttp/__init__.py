class ClientError(Exception): pass
class ClientSession: pass
class ClientTimeout:
    def __init__(self, **kw): self.kw = kw
