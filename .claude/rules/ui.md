# UI Rules

## General

- Custom `LookAndFeel` subclass — no default JUCE styling anywhere
- All drawing code in LookAndFeel overrides only — zero drawing in component or DSP logic
- No foleys_gui_magic or XML-driven UI builders
- Gin library (github.com/FigBug/Gin) may be used for supplementary components
- UI fully decoupled from DSP — visual design must be replaceable without touching DSP

## Layout — Tommy Pedal Face

Reference: `Timmy_pedal.jpg` (silver enclosure, wooden background)

```
┌─────────────────────────────────────┐
│  [INPUT TRIM]              [OUTPUT TRIM]  ← plugin-only controls, visually distinct
├─────────────────────────────────────┤
│    [BASS]    [SW1-3way]    [GAIN]    │  ← row 1 knobs + switch
│    [VOLUME]    [●LED]    [TREBLE]    │  ← row 2 knobs + LED
│            Tommy                    │  ← pedal name
│           [BYPASS]                  │  ← footswitch toggle
│  [OVERSAMPLING]                     │  ← plugin-only control
│  [IN METER] ▐▐▐▐▐▐▐▐▐              │  ← VU meters (bar style)
│  [OUT METER] ▐▐▐▐▐▐▐▐▐             │
└─────────────────────────────────────┘
```

## Controls

### Knobs
- Four rotary knobs: Bass, Gain, Volume, Treble
- Labels match original pedal: "Bass", "Gain" (not "Drive"), "Volume", "Treble"
- All audio taper — taper applied in DSP, not UI
- JUCE `Slider` (rotary) with custom LookAndFeel paint

### SW1 — 3-Position Clipping Switch
- Visual: vertical 3-way toggle switch
- Three positions labelled by sonic character: **Soft** / **Medium** / **Hard**
- Maps to `clipping_mode` parameter (0/1/2) = Soft/Medium/Hard
- Physical switch direction on the plugin need not match the original pedal — labels are authoritative

### Bypass
- Large footswitch-style toggle button at bottom centre
- Behaviour: LED ON = active (processing), LED OFF = bypassed

### LED
- Small circular LED indicator, between the two knob rows, centre
- ON (lit, green or amber) = pedal active; OFF = bypassed
- State driven by `std::atomic<bool> bypassed`

### Input Trim / Output Trim
- Clearly labelled "Input Trim" and "Output Trim"
- Visually distinct from the four pedal knobs (different size, placement, or styling)
- Range: -12 to +12 dB
- Placed at top of UI, outside the "pedal face" area

### Oversampling Control
- Labelled "Oversampling"
- 4 options: 1x, 2x, 4x, 8x
- ComboBox or segmented button — clearly readable
- Placed at bottom of UI, outside the pedal face area

## Plugin Window

- Fixed size: **520 × 480 px** (placeholder — adjust once layout is refined, but pick a size before building UI components so nothing is relative to an undefined dimension)
- Not resizable in v1 — add resize support later if needed
- Set via `setSize(520, 480)` in `PluginEditor` constructor

## Colour Scheme (placeholder — replaceable later)

All colours defined as named constants in `TommyLookAndFeel.h`. Do not hardcode hex values in component code.

```cpp
// Placeholder palette — functional but neutral, replace with final design later
static constexpr juce::Colour colourBackground    { 0xFF1A1A1A }; // near-black body
static constexpr juce::Colour colourPanelFace     { 0xFF8A8FA8 }; // silver-grey pedal face
static constexpr juce::Colour colourKnob          { 0xFF2A2A2A }; // dark knob cap
static constexpr juce::Colour colourKnobIndicator { 0xFFFFFFFF }; // white indicator line
static constexpr juce::Colour colourLEDActive     { 0xFF00DD44 }; // green LED on
static constexpr juce::Colour colourLEDInactive   { 0xFF1A3322 }; // dim green LED off
static constexpr juce::Colour colourLabelText     { 0xFFFFFFFF }; // white labels
static constexpr juce::Colour colourMeterLow      { 0xFF44CC44 }; // meter green
static constexpr juce::Colour colourMeterMid      { 0xFFDDCC00 }; // meter yellow
static constexpr juce::Colour colourMeterHigh     { 0xFFDD2222 }; // meter red
static constexpr juce::Colour colourTrimControl   { 0xFF4488CC }; // blue tint for plugin-only controls
```

- Bar-style VU meters, input and output
- Calibrated to -12 dBu nominal (0 VU = -12 dBu)
- VU ballistics: ~300ms integration (attack fast, release ~300ms)
- Input meter: post input-trim, pre DSP
- Output meter: post DSP, post output-trim
- Updated via `juce::Timer` on message thread, reading `std::atomic<float>` levels
- Stereo or mono display (mono summed is acceptable for v1)

## Threading in UI

- UI timer reads `std::atomic` meter values and bypass state — no direct DSP access
- Parameter changes go through APVTS listeners — no direct DSP calls from UI
