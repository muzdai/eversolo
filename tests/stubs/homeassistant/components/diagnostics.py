def async_redact_data(data, to_redact):
    if isinstance(data, dict):
        return {k: ("**REDACTED**" if k in to_redact else async_redact_data(v, to_redact)) for k, v in data.items()}
    if isinstance(data, list):
        return [async_redact_data(v, to_redact) for v in data]
    return data
