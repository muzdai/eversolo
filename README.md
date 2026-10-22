# Eversolo for Home Assistant

An integration for **Eversolo DMP / DAC** players (local network, port 9529). It installs through HACS as a
custom repository and adds a device with entities, a player card and a screen mirror card. Every call mirrors
what the official Eversolo Controller 1.15.65 app does (see `docs/protocol.md`).

## Features

| Feature | Where |
|---|---|
| Player: play/pause, previous/next, volume (slider and steps), mute, seek, repeat/shuffle, input selection | `media_player.<name>` |
| Player card: landscape / portrait layout by screen orientation, background from the cover colors, RU/EN | Lovelace `custom:eversolo-player-card` |
| Screen mirroring with touch control, like "Screen mirroring" in the app | Lovelace `custom:eversolo-mirror-card` |
| Input and output switching | card, `select` "Input" and "Output", services `eversolo.set_input`, `eversolo.set_output` |
| VU meters and spectrum on the device display: next mode | card, "VU meter" and "Spectrum" buttons, services `eversolo.vu_next`, `eversolo.spectrum_next` |
| Streaming apps on the player (TIDAL, Qobuz, etc., whatever is installed) | card, service `eversolo.open_app` |
| Device power menu (standby, screen off, reboot: whatever the player reports) | card, one button per item, service `eversolo.power` |
| `eversolo:*` icons (30: logo, player, VU, spectrum, DSP/EQ/Sub, repeat modes, connectors, power) for any card or entity | loaded automatically, see `docs/icons.png` |
| API probing | service `eversolo.request` (GET on any path, returns the response) |

The name is set when the device is added (discovery fills in the player's name) and becomes the prefix of
all entity ids.

## Installation via HACS

1. HACS → "⋮" menu → **Custom repositories** → `https://github.com/muzdai/eversolo`, category **Integration**.
2. Install **Eversolo** and restart Home Assistant.
3. The player shows up under "Discovered" (mDNS `_eversolo._tcp`) with its model and name. Or: Settings → Devices &
   services → **Add integration** → Eversolo, then enter a name and the IP address.
4. Right after you submit the form, the player shows a connection request on its screen: allow it. If you
   miss it, the wizard offers to try again.

Settings → Devices & services → Eversolo → **Configure** lets you change the name, IP address and port.
Changing the name does not rename entities that already exist.

## Player card

```yaml
type: custom:eversolo-player-card
entity: media_player.eversolo
layout: auto            # auto | landscape | portrait
show_background: true   # background from the cover
show_spectrum: true     # animated level bars behind the controls while playing
show_volume: true       # volume slider
show_chips: false       # input/output/apps/power chips (the same is in the "⋯" menu)
```

The look follows the Eversolo app's now-playing screen: source and DSP/EQ/Sub, spectrum and VU badges on top,
file format and output under the track title. `layout: auto` uses the portrait layout when the screen is held
upright or the card is narrower than 460 px, landscape otherwise.
Buttons the current source does not support (for example seeking over Bluetooth) are disabled.

## Screen mirror card

```yaml
type: custom:eversolo-mirror-card
entity: media_player.eversolo
show_nav: true          # Back, Home and volume buttons under the picture
```

This is the same as "Screen mirroring" in the Eversolo app. The card shows the player's screen, and taps and
swipes on it are sent to the player. The video (H.264) goes through Home Assistant over the websocket, so no
extra ports need to be opened. The browser decodes it with WebCodecs, so you need Chrome, Edge or Safari and
Home Assistant over HTTPS (or localhost). The stream starts when the card is visible and stops 15 s after it
is closed. When the player is off, the card shows "Device offline" in the Home Assistant language and
reconnects as soon as the player is back.

## Services

```yaml
action: eversolo.set_input       # data: entity_id, name (name or tag from input_list)
action: eversolo.set_output      # data: entity_id, name
action: eversolo.set_loop_mode   # data: entity_id, mode: repeat_all | repeat_one | shuffle | play_once
action: eversolo.vu_next         # data: entity_id
action: eversolo.spectrum_next   # data: entity_id
action: eversolo.open_app        # data: entity_id, name (name or packageName from app_list)
action: eversolo.power           # data: entity_id, name (name or tag from power_list)
action: eversolo.request         # data: entity_id, path  -> response: the device's raw reply
```

`media_player` attributes: `input`, `input_list`, `output`, `output_list`, `loop_mode`, `vu_mode`,
`spectrum_mode`, `app`, `app_list`, `power_list`, `codec`, `bits`, `sample_rate`, `channels`, `bitrate`,
`output_format`, `output_codec`, `output_rate`, `output_bits`, `source_name`, `dsp`, `eq`, `sub`,
`volume_display`, `model`, `host`.

## Development

```
custom_components/eversolo/      the integration
  www/eversolo-player-card.js    player card and screen mirror card
  www/eversolo-icons.js          eversolo:* icon set
tools/eversolo_client.py         standalone CLI client for protocol checks
docs/protocol.md                 protocol description
docs/ui_reference/               layouts and icons of the original app
```

## License

[GNU General Public License v3.0](LICENSE). This is an unofficial project, not affiliated with Eversolo.
