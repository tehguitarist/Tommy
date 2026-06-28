# UI Rules

## General

- Custom `LookAndFeel` subclass — no default JUCE styling anywhere
- All drawing code in LookAndFeel overrides only — zero drawing in component or DSP logic
- No foleys_gui_magic or XML-driven UI builders
- UI fully decoupled from DSP — visual design must be replaceable without touching DSP

## Layout

Three-column layout with an oversampling strip below:

```
┌──────────────────────────────────────────────────┐
│  [INPUT]          [PEDAL FACE]        [OUTPUT]   │
│                                                  │
│  Halo trim    ┌──────────────────┐  Halo trim   │
│  knob (png)   │  ⊕ 9V ⊖          │  knob (png)  │
│               │                  │               │
│  [VU bar]     │ [BASS] ⊣  [GAIN] │  [VU bar]   │
│  (tall,       │                  │  (tall,       │
│   fills       │    ● LED         │   fills       │
│   height)     │                  │   height)     │
│               │ [VOL]    [TREB]  │               │
│               │                  │               │
│               │     Tommy        │               │
│               │    [BYPASS]      │               │
│               └──────────────────┘               │
├──────────────────────────────────────────────────┤
│  Oversampling:  [1x]  [2x]  [4x✓]  [8x]        │
└──────────────────────────────────────────────────┘
```

**Column widths (at base 420×458, `currentScale = 1.0` — all values scale via the `i()` helper,
see Plugin Window below):**
- Outer padding: 12 px each side
- Left side panel (Input): 74 px
- Gap: 8 px
- Pedal face: remainder of the row
- Gap: 8 px
- Right side panel (Output): 74 px

**Row heights:**
- Main row (side panels + pedal): 400 px
- Gap: 10 px
- Oversampling strip: 24 px
- Outer padding: 12 px top + bottom

Layout is computed with manual `juce::Rectangle` splitting (`removeFromLeft`/`removeFromTop`/etc.
in `PluginEditor::resized()`), not `juce::FlexBox` — no FlexBox/FlexItem is used anywhere in
the codebase.

## Plugin Window

- Base size: **420 × 458 px** (`PluginEditor::kBaseW` / `kBaseH`)
- **Resizable**, 0.5×–2.5× of base, locked to the base aspect ratio (`setResizable` +
  `setFixedAspectRatio` + `setSizeLimits` in the constructor). A "UI SIZE" button in the
  oversampling strip opens a preset-scale menu (50%–250%) and can save the current scale as the
  default (`ApplicationProperties`); the per-session scale is also persisted in `apvts.state`.
- All layout in `resized()` is computed from `currentScale = getWidth() / kBaseW` via a local
  `i(px)` helper (`roundToInt(px * currentScale)`) — never hardcode pixel values outside that helper.

## Side Panels — Input (left) and Output (right)

Each side panel is identical in structure. Top-to-bottom:

1. **Section label** — "INPUT" or "OUTPUT", 8 px, 700 weight, letter-spacing 2 px, blue-tinted (`cTrimLabel`)
2. **Halo trim knob** — 70×70 px rotary. An outer arc track (drawn procedurally, `cTrimArcTrack`)
   shows the full range; a filled value arc (`cTrimArc`) shows the current value. The knob cap
   itself is the `vol_trim.png` image (rotated per `drawRotatedImage`), same image-based approach
   as the pedal knobs — not a procedurally drawn gradient disc.
3. **"TRIM" sub-label** — 7.5 px, muted blue
4. **Trim value label** (`inputTrimValueLabel`/`outputTrimValueLabel`) — fixed (always-visible, not
   a popup) `juce::Label` showing the current trim as `"<value> dB"` to 1 decimal place (e.g.
   `"+3.0 dB"`), range -12.0–+12.0. Updated live via the slider's `onValueChange` callback, not an
   APVTS listener — purely a display convenience, the trim knob itself still owns the parameter via
   `SliderParameterAttachment`. 8.5 px font, same blue (`cTrimLabel`) as the section title.
5. **VU bar meter** — fills all remaining height (flex:1). 22 segments, `flex-direction: column` (index 0 = top = loud/red), `gap: 2 px`. Segment colours: red (top ~14%), yellow (next ~21%), green (lower ~65%); lit vs unlit variants for each zone. Updated by `juce::Timer`.

JUCE implementation: plain `juce::Slider` members directly on `PluginEditor` (`inputTrimKnob`/
`outputTrimKnob`, componentID `"trim"` so `TommyLookAndFeel::drawRotarySlider` renders the halo
style) plus a `VUMeter` (`inputVU`/`outputVU`) — no separate panel or `HaloKnob` component class.
The trim knobs do NOT get the pedal-knob drag-tooltip (see Controls — Knobs) since the fixed value
label already shows the dB value at all times.

## Pedal Face

Background: a photographed/rendered texture image (`assets/ui/tommy_texture.png`, embedded via the
`TommyUIAssets` binary-data CMake target; raw original preserved in `ui/Tommy_Texture.png`), drawn
in `TommyLookAndFeel::paintPedalBackground()`. **"Cover" fit**: scale to fill both dimensions of the
pedal-face rect with no stretching (`scale = max(W/srcW, H/srcH)`), centred, overflow cropped by the
rounded-rect clip — never stretch the image to an aspect ratio it wasn't shot at. Processed once
offline from the original (resize → `-brightness-contrast -3x-3` → `pngquant`/`optipng`); don't
re-derive it from the already-processed `assets/ui/` copy if it needs reprocessing.

Border: 2 px stroke, `cPedalBorder`. Border-radius: 16 px. No drop shadow.

### Supply-voltage selector (interactive power label)

Small text "(+) 9V (-)" centred at top — an INTERACTIVE control (`SupplyControl`, header-only
component), not a static label. Click "(+)" (raise 9→12→18 V) or "(-)" (lower); the centre shows
the current voltage. "(+)"/"(-)" are lit (`cPowerLabelLit`) only when that direction is available;
otherwise dim (`cPowerLabel`). The three pieces are packed **tightly together and centred** as one
group (computed from actual text widths, not divided into equal thirds — equal thirds left large,
ugly gaps around the short text at most window widths). Font is 25% larger than the base 8px.
Click hit-testing uses the same tight layout (with a small invisible margin) so it tracks the
visible text, not arbitrary thirds. Bound to the `supply_voltage` choice parameter via a
`ParameterAttachment` (same pattern as the SW1 switch). Thin separator line below. (Raises the
op-amp rail headroom in the DSP — pure headroom, diode clip thresholds unchanged.)

### Row 1 — Bass · SW1 · Gain

Pedal width split into three equal sections (left/centre/right via `removeFromLeft`/
`removeFromRight`):
- **Bass knob** (left section)
- **SW1 3-position toggle switch** (centre section, horizontally centred within it — see below)
- **Gain knob** (right section)

### SW1 — 3-Position Clipping Switch

Rendered as a photographed toggle switch image (`switch_up.png` / `switch_mid.png` /
`switch_down.png`, via `TommyLookAndFeel::getSwitchImage(position)`), swapped per position rather
than drawn procedurally — the lever angle is baked into each image. `SW1Switch` (in
`src/ui/SW1Switch.h`) draws the image horizontally centred in its own bounds (so it sits on the
pedal's centre line, not in the old left-third/right-third FlexLayout split) with single-letter
labels: **A** above the image, **O** beside it (right), **S** below — replacing the old
"Asym"/"Open"/"Sym" text. The bottom margin (for "S") is deliberately tighter than the top margin
(for "A") so "S" reads as sitting closer to the switch body. Active label colour:
`cSWLabelActive`; inactive: `cSWLabelInactive`. `mouseDown`/`mouseDrag` both update the position
from Y so it can be dragged like a real toggle.

**Position → mode mapping (do not flip this — it must match the DSP):** position **0 = top =
"A" = Hard** (single diode, asymmetric) → position **1 = middle = "O" = Medium** (one diode
pair) → position **2 = bottom = "S" = Soft** (all four diodes, symmetric). This is the ground
truth from `PluginProcessor.cpp`'s `kClipModes[]` array (`// pClip index 0/1/2 maps to ClipMode
Hard/Medium/Soft respectively`) and `Stage1.h`'s `ClipMode` enum — it is the OPPOSITE of an
earlier (wrong) version of this doc that had top=Soft/bottom=Hard.

### LED indicator

Image swap (`blue_led_on.png` / `blue_led_off.png` via `LEDIndicator`), not a procedurally drawn
circle. The glow is baked into the "on" art, so the component is given bounds noticeably larger
than the physical LED footprint (28 px box vs. an ~9 px LED) — JUCE clips all painting to a
component's own bounds, so the glow needs the extra room at the `setBounds()` call site, not just
in `paint()`. Driven by `isBypassed()` atomic.

### Row 2 — Volume · LED · Treble

Same three-section split as Row 1:
- **Volume knob** (left section)
- **LED indicator** (centre section)
- **Treble knob** (right section)

### Tommy logo

Italic script (`"Brush Script MT"`), base size 93.2 px (scales with `currentScale`), white at
90% opacity (`cLabelText.withAlpha(0.9f)`). Centred. Sits below knob Row 2, above the bypass
footswitch.

### Bypass footswitch

Image swap (`footswitch_up.png` / `footswitch_down.png` via `drawImageCentredAspect`, keyed off
the button's `down` mouse state), not a procedurally drawn dome + box-shadow ring. The image
swap is a **press animation only** — it does not itself indicate bypass on/off; that's the
separate LED. ~52 px diameter, centred. Small "BYPASS" label below in `cBypassLabel` (muted
blue). Toggles the `bypass` parameter; LED and processing update accordingly.

## Controls — Knobs

All four pedal knobs (Bass, Gain, Volume, Treble) and both trim knobs (Input/Output) are rendered
as a single rotated image (`T_Knob.png` for pedal knobs, `vol_trim.png` for trim knobs) via
`TommyLookAndFeel::drawRotarySlider()` → `drawRotatedImage()`, not procedurally drawn discs.
Source art is pre-rendered pointing at noon (so image angle 0 = JUCE's rotary slider default);
each frame is drawn with an `AffineTransform` (`translate to origin → scale → rotate by
valAngle → translate to centre`) — no separate gradient cap, indicator line, or drop shadow is
drawn behind/over the image (a drop shadow was tried and explicitly removed — a dark shadow
against the near-black pedal face read as transparency on the knob rim rather than as a shadow).
Pedal knobs are 66 px diameter (`i(66)`); trim knobs are 70 px. Text label below: 8.5 px, 600
weight, 1.5 px letter-spacing, uppercase, white.

Audio taper applied in DSP. APVTS attachment via `juce::SliderParameterAttachment`.

**Drag tooltip (pedal knobs only):** Bass/Gain/Volume/Treble use `Slider::setPopupDisplayEnabled(true,
false, this)` to show a small bubble with the raw 0.0–1.0 parameter value while dragging. The bubble
text is set via an explicit `textFromValueFunction` (`juce::String(v, 2)`, e.g. `"0.50"`) rather than
relying on `setNumDecimalPlacesToDisplay` alone, so the format is always exactly two decimal places
regardless of the slider's range/interval settings. The two trim knobs do not use this popup — they
have their own always-visible value label instead (see Side Panels above).

**Defaults:** Bass/Gain/Treble default to `0.0` (fully counter-clockwise / minimum). Volume defaults
to `0.5 + 30/288 ≈ 0.6042`, which visually lands the knob image at 1 o'clock given the LookAndFeel's
default JUCE rotary sweep (1.2π→2.8π, 288° total, with `0.5` = noon). See `architecture.md`'s
parameter table for the authoritative defaults.

## Oversampling Strip

Full-width panel below pedal, separate background (`cOSBackground`). Left-to-right (not the old
single "OVERSAMPLING" label + four 1x/2x/4x/8x segmented buttons — there are now two independent
oversampling rates plus a UI-scale control):
- **"OS"** label
- **"LIVE"** label + `osRealtimeBox` (`juce::ComboBox`, `ComboBoxParameterAttachment` to the
  `oversampling` parameter) — the factor used during real-time playback
- **"RENDER"** label + `osRenderBox` (separate `ComboBox` + attachment) — the factor used for
  offline rendering/export, independent of LIVE
- **"HQ"** toggle (`hqButton`, `juce::TextButton`, componentID `"ostoggle"`, `ButtonParameterAttachment`
  to the `hq` parameter) — grouped at the right with the UI-size controls. **Lit when on, dim when
  off**, default on. Hover tooltip (`setTooltip`, shown via a `juce::TooltipWindow` member on the
  editor): "HQ: most accurate diode modelling. Turn off to save CPU." Toggles the accurate vs fast
  diode solver (see `architecture.md` `hq` / `dsp.md` Omega accuracy).
- **"UI SIZE"** label (`sizeLabel`) + `scaleBtn` (`juce::TextButton`, componentID `"os"`, shows
  the current scale e.g. `"100%"`) at the far right — opens `showScaleMenu()`, a preset picker
  (50%–250% in 25% steps) for `currentScale` (see Plugin Window)

`drawButtonBackground` has two text-button branches: `"os"` (always-lit OS-combo styling, used by
`scaleBtn` since it's a menu trigger, not a toggle) and `"ostoggle"` (lit background+border when
`getToggleState()`, dim when off — used by `hqButton`). The ComboBoxes use
`TommyLookAndFeel::drawComboBox` (dark background, thin border, small chevron arrow).

## Colour Palette

All colours defined as `uint32` named constants on `TommyLookAndFeel` (use as
`juce::Colour(TommyLookAndFeel::cFoo)` — avoids `constexpr Colour` portability issues). Do not
hardcode hex values in component code. `cKnobMid`/`cKnobShadow`/`cKnobIndicator` are dead/unused
now that knobs are drawn from `T_Knob.png` (no procedural cap/shadow/indicator line) — kept for
now but candidates for removal.

```cpp
static constexpr juce::uint32 cBackground      = 0xFF050912u; // very dark navy-black
static constexpr juce::uint32 cPedalFace       = 0xFF070D1Au; // dark navy pedal base
static constexpr juce::uint32 cPedalBorder     = 0xFF18293Fu; // pedal border
static constexpr juce::uint32 cKnobHighlight   = 0xFFF5F5F5u; // PopupMenu highlighted-text colour only
static constexpr juce::uint32 cKnobMid         = 0xFFD8D8D8u; // unused — knobs are image-drawn
static constexpr juce::uint32 cKnobShadow      = 0xFF949494u; // unused — knobs are image-drawn
static constexpr juce::uint32 cKnobIndicator   = 0xFF1A1A30u; // unused — knobs are image-drawn
static constexpr juce::uint32 cLEDActive       = 0xFF00DD55u; // unused now (LED is image-drawn)
static constexpr juce::uint32 cLEDInactive     = 0xFF091A09u; // unused now (LED is image-drawn)
static constexpr juce::uint32 cLabelText       = 0xFFFFFFFFu; // white labels (Tommy logo at 90% alpha)
static constexpr juce::uint32 cPowerLabel      = 0xFF2E4A60u; // muted dark blue, inactive (+)/(-)/9V text
static constexpr juce::uint32 cPowerLabelLit   = 0xFF6FA8D8u; // active (+)/(-) on the supply selector
static constexpr juce::uint32 cTrimLabel       = 0xFF5588AAu; // blue section titles (INPUT/OUTPUT)
static constexpr juce::uint32 cTrimArc         = 0xFF2A5898u; // halo knob value arc
static constexpr juce::uint32 cTrimArcTrack    = 0xFF101E30u; // halo knob background track
static constexpr juce::uint32 cSWLabelActive   = 0xFFC0E4FFu; // SW1 active position label (A/O/S)
static constexpr juce::uint32 cSWLabelInactive = 0xFF5C84ACu; // SW1 inactive labels
static constexpr juce::uint32 cBypassLabel     = 0xFF4878A0u; // BYPASS sub-label
static constexpr juce::uint32 cMeterLow        = 0xFF44CC44u; // VU green (lit)
static constexpr juce::uint32 cMeterMid        = 0xFFCCBA00u; // VU yellow (lit)
static constexpr juce::uint32 cMeterHigh       = 0xFFDD2222u; // VU red (lit)
static constexpr juce::uint32 cMeterLowDim     = 0xFF091A09u; // VU green (unlit)
static constexpr juce::uint32 cMeterMidDim     = 0xFF1E1700u; // VU yellow (unlit)
static constexpr juce::uint32 cMeterHighDim    = 0xFF220808u; // VU red (unlit)
static constexpr juce::uint32 cOSBackground    = 0xFF080E1Au; // oversampling panel
static constexpr juce::uint32 cOSBorder        = 0xFF101C2Eu; // oversampling panel border
static constexpr juce::uint32 cOSLabel         = 0xFF3A6080u; // "OVERSAMPLING" label / inactive OS text
static constexpr juce::uint32 cOSBtnActive     = 0xFF70A8D8u; // OS button active text
static constexpr juce::uint32 cOSBtnActiveBg   = 0xFF0C2040u; // OS button active background
static constexpr juce::uint32 cOSBtnActiveBdr  = 0xFF2A5890u; // OS button active border
```

## VU Meter Spec

- 22 segments, `flex-direction: column` (segment 0 at top = loudest = red)
- Segment height: equal division of available height (flex:1 each), 2 px gap
- Zone thresholds (by fractional position from bottom, 0.0=bottom, 1.0=top):
  - Red: top 14% (fraction > 0.86)
  - Yellow: next 21% (fraction 0.65–0.86)
  - Green: bottom 65% (fraction < 0.65)
- Calibration: 0 VU = -12 dBu nominal → lit to ~60% of bar at nominal signal
- Ballistics: peak hold off; release ~300 ms (exponential decay in Timer callback)
- Input meter: reads `getInputLevel(ch)` — post input-trim, pre DSP
- Output meter: reads `getOutputLevel(ch)` — post DSP, post output-trim
- Timer interval: 30 ms (≈33 fps)
- Mono: sum L+R in processor, expose single `getInputLevel(0)` / `getOutputLevel(0)` — acceptable for v1

## Threading in UI

- `juce::Timer` on message thread reads `getInputLevel`, `getOutputLevel`, `isBypassed` — no locks
- Parameter changes go through APVTS `SliderParameterAttachment` / `ComboBoxParameterAttachment`
- No direct DSP calls from UI components
