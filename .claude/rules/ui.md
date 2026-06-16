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
│  knob (svg)   │  ⊕ 9V ⊖          │  knob (svg)  │
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

**Column widths (480px window):**
- Left side panel (Input): 74 px
- Gap: 8 px
- Pedal face: flex-1 (~284 px)
- Gap: 8 px
- Right side panel (Output): 74 px
- Outer padding: 14 px each side

**Row heights:**
- Main row (side panels + pedal): 400 px
- Gap: 10 px
- Oversampling strip: ~46 px
- Outer padding: 14 px top + bottom

## Plugin Window

- Fixed size: **480 × 480 px**
- Not resizable in v1
- Set via `setSize(480, 480)` in `PluginEditor` constructor

## Side Panels — Input (left) and Output (right)

Each side panel is identical in structure. Top-to-bottom:

1. **Section label** — "INPUT" or "OUTPUT", 8 px, 700 weight, letter-spacing 2 px, blue-tinted (`colourTrimLabel`)
2. **Halo trim knob** — SVG rotary, 70×70 px. An outer arc track (270° sweep, from 7 o'clock to 5 o'clock) shows the full range; a filled arc shows the current value. Knob body is a 36 px diameter circle with a white/light gradient cap and a dark indicator line. At 0 dB (centre of range) the indicator points to 12 o'clock. Arc colour: `colourTrimArc` (blue).
3. **"TRIM" sub-label** — 7.5 px, muted blue
4. **VU bar meter** — fills all remaining height (flex:1). 22 segments, `flex-direction: column` (index 0 = top = loud/red), `gap: 2 px`. Segment colours: red (top ~14%), yellow (next ~21%), green (lower ~65%); lit vs unlit variants for each zone. Updated by `juce::Timer`.

JUCE implementation: `InputTrimPanel` / `OutputTrimPanel` components, each containing a `HaloKnob` (custom `Slider` subclass) and a `VUMeter`.

## Pedal Face

Background: **mottled dark navy/black**. Implement in `TommyLookAndFeel::drawPedalBackground()` using `juce::Random` to scatter 200–300 small dots (r 0.2–1.5 px, alpha 0.03–0.18, hue blue-navy) over a base fill of `colourPedalFace`. Add 5 soft radial gradient blobs (dark navy, low opacity) to create the mottled depth effect. Add a 1 px horizontal highlight line near the top edge.

Border: 2 px, `colourPedalBorder`. Border-radius: 16 px. Drop shadow outward.

### 9V power label

Small text "⊕ 9V ⊖" centred at top, `colourPowerLabel` (muted dark blue). Thin separator line below.

### Row 1 — Bass · SW1 · Gain

`FlexLayout` (space-between) across pedal width:
- **Bass knob** (left)
- **SW1 3-position toggle switch** (centre)
- **Gain knob** (right)

### SW1 — 3-Position Clipping Switch

Vertical toggle switch body (18×60 px). A lever (32×17 px, light grey gradient) slides to one of three positions. Labels to the right of the switch body, spaced to align with positions: **Soft** (top) / **Med** (middle) / **Hard** (bottom). Active label colour: `colourSWLabelActive` (light blue-white); inactive: `colourSWLabelInactive` (muted blue). Maps to `clipping_mode` parameter (0=Soft, 1=Med, 2=Hard).

Physical switch direction: top = Soft (all diodes), middle = Med (one pair), bottom = Hard (single diode).

### LED indicator

9 px diameter circle between rows. Active: `colourLEDActive` (green) with glow. Inactive: `colourLEDInactive` (very dark green). Driven by `isBypassed()` atomic.

### Row 2 — Volume · (space) · Treble

`FlexLayout` (space-between):
- **Volume knob** (left)
- Empty centre space (where LED sits above)
- **Treble knob** (right)

### Tommy logo

Italic serif (Georgia or similar), 26 px, white. Centred. Sits below knob Row 2.

### Bypass footswitch

Large dome button (52 px diameter), centred. Background: dark navy radial gradient. Metal ring effect via layered box-shadow (dark gap ring + lighter outer ring). Small "BYPASS" label below in `colourBypassLabel` (muted blue). Toggles `bypass` parameter; LED and processing update accordingly.

## Controls — Knobs

All four pedal knobs (Bass, Gain, Volume, Treble) are identical:
- 50 px diameter rotary `Slider`
- White/light cap: radial gradient from near-white (38% 30%) to mid-grey
- Dark indicator line (3×15 px) pointing from centre toward 12 o'clock at default, rotated by knob position
- Drop shadow
- Text label below: 8.5 px, 600 weight, 1.5 px letter-spacing, uppercase, white

Audio taper applied in DSP. APVTS attachment via `juce::SliderParameterAttachment`.

## Oversampling Strip

Full-width panel below pedal, separate background (`colourOSBackground`). Contains:
- "OVERSAMPLING" label (left, 8 px, 700 weight, letter-spacing 1.5 px, muted blue)
- Four segmented buttons: **1x / 2x / 4x / 8x** (right side)
- Active button: brighter border + text + subtle glow; inactive: muted
- Backed by `juce::ComboBox` or custom segmented button component

## Colour Palette

All colours defined as named constants in `TommyLookAndFeel.h`. Do not hardcode hex values in component code.

```cpp
static constexpr juce::Colour colourBackground    { 0xFF050912 }; // very dark navy-black
static constexpr juce::Colour colourPedalFace     { 0xFF070D1A }; // dark navy pedal base
static constexpr juce::Colour colourPedalBorder   { 0xFF18293F }; // pedal border
static constexpr juce::Colour colourKnob          { 0xFFD8D8D8 }; // light grey knob cap (mid)
static constexpr juce::Colour colourKnobHighlight { 0xFFF5F5F5 }; // knob highlight (specular)
static constexpr juce::Colour colourKnobShadow    { 0xFF949494 }; // knob shadow
static constexpr juce::Colour colourKnobIndicator { 0xFF1A1A30 }; // dark indicator line on knob
static constexpr juce::Colour colourLEDActive     { 0xFF00DD55 }; // green LED on
static constexpr juce::Colour colourLEDInactive   { 0xFF091A09 }; // very dark green LED off
static constexpr juce::Colour colourLabelText     { 0xFFFFFFFF }; // white knob labels
static constexpr juce::Colour colourPowerLabel    { 0xFF2E4A60 }; // muted dark blue 9V label
static constexpr juce::Colour colourTrimLabel     { 0xFF5588AA }; // blue section titles (INPUT/OUTPUT)
static constexpr juce::Colour colourTrimArc       { 0xFF2A5898 }; // halo knob value arc
static constexpr juce::Colour colourTrimArcTrack  { 0xFF101E30 }; // halo knob background track
static constexpr juce::Colour colourSWLabelActive { 0xFF90C0E0 }; // SW1 active position label
static constexpr juce::Colour colourSWLabelInactive{ 0xFF3A5A78 }; // SW1 inactive labels
static constexpr juce::Colour colourBypassLabel   { 0xFF2E4A60 }; // BYPASS sub-label
static constexpr juce::Colour colourMeterLow      { 0xFF44CC44 }; // VU green (lit)
static constexpr juce::Colour colourMeterMid      { 0xFFCCBA00 }; // VU yellow (lit)
static constexpr juce::Colour colourMeterHigh     { 0xFFDD2222 }; // VU red (lit)
static constexpr juce::Colour colourMeterLowDim   { 0xFF091A09 }; // VU green (unlit)
static constexpr juce::Colour colourMeterMidDim   { 0xFF1E1700 }; // VU yellow (unlit)
static constexpr juce::Colour colourMeterHighDim  { 0xFF220808 }; // VU red (unlit)
static constexpr juce::Colour colourOSBackground  { 0xFF080E1A }; // oversampling panel
static constexpr juce::Colour colourOSBorder      { 0xFF101C2E }; // oversampling panel border
static constexpr juce::Colour colourOSLabel       { 0xFF3A6080 }; // "OVERSAMPLING" label
static constexpr juce::Colour colourOSBtnInactive { 0xFF3A6080 }; // OS button inactive text
static constexpr juce::Colour colourOSBtnActive   { 0xFF70A8D8 }; // OS button active text
static constexpr juce::Colour colourOSBtnActiveBg { 0xFF0C2040 }; // OS button active background
static constexpr juce::Colour colourOSBtnActiveBorder{ 0xFF2A5890 }; // OS button active border
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
