class Debouncer:
    def __init__(self, hass, logger, cooldown=10, immediate=True, function=None):
        self.cooldown, self.immediate = cooldown, immediate
