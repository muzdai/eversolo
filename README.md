# Eversolo for Home Assistant

Unofficial local-network integration for Eversolo players. HACS custom integration.

## Status: experimental
Endpoint names were identified in strings from Eversolo Controller 1.15.65. The full request/response schema has not yet been verified on hardware. In particular, volume scale, seek units, state field names, and model-specific support require validation.

## Install
Add this repository to HACS as a custom repository (category: Integration), then install **Eversolo**. Alternatively copy `custom_components/eversolo` into Home Assistant's `config/custom_components/` directory and restart.

## Configure
Settings → Devices & services → Add integration → Eversolo. Enter the player IP and port (default 9529).

## Current features
- Poll player state and volume
- Play/pause toggle, next, previous, seek and volume
- Local HTTP; no cloud API key required

## Known limitations
- No automatic discovery yet.
- Uses `/ZidooMusicControl/v2/getState`, `getVolume`, `playOrPause`, `playNext`, `playLast`, `seekTo` and `setDevicesVolume`.
- Volume is sent on a provisional 0–100 scale; seek is sent in milliseconds. Verify against your firmware.
- Response parsing uses common field-name heuristics.
- DSP, source selection, queue browsing, artwork and power controls are not implemented.

Contributions and reports with device model/firmware and redacted API responses are welcome.