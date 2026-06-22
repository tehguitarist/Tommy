#UI Updates

## Guidelines
- All knobs are set at "noon" position and have a very small transparent buffer around them.
- Keep all replacement images the same size as close as is reasonable.
- Do not stretch any images, crop to fit where needed
- use a 2x resolution scaling at 100% scaling for the UI (so that when scaling the UI up, images don't blur until over 200% - could use 2.5x needed size)
- resize images (and save separately to preserve originals) to minimise plugin size as much as is reasonable whilst maintaining a sharp image.
- convert images to optimal format if needed
- all images except texture have an alpha channel/transparent background and are rotation safe.

## Parts to replace
- Peripheral input/output knobs = vol_trim.png
- vol/treble/bass/gain knobs = T_knob.png
- pedal background = Tommy_Texture.png
- LEDs = blue_led_off.png for off, blue_led_on.png for on, make this slightly larger than the original part as a glow is built into the image.
- footswitch = footswitch_up.png as default, footswitch_down.png on press only (footswitch position does not indicate state, it's just a button press "animation")
- clip switch = switch_up.png for up, switch_Mid.png for mid, switch_down.png for down. Retain drag operation, and ability to click to set as well