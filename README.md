# Tommy

Tommy is an overdrive plugin (AU/VST3) inspired by the classic "transparent overdrive"
pedal circuit popularized by boutique builders in the 2000s. It uses circuit-accurate
Wave Digital Filter (WDF) modelling to capture the feel and tone of that style of
analog drive, with a few modern conveniences layered on top.

> Tommy is an original implementation built from circuit analysis and is not
> affiliated with or endorsed by any pedal manufacturer.

![image](image.png)

## Features

- Circuit-modelled drive stage with coupled Bass/Gain interaction, just like the
  analog original
- Three-position clipping switch (Soft / Medium / Hard) for a range of clipping
  characters, from smooth and symmetric to hard and asymmetric
- Treble control with an interactive passive filter response
- Selectable oversampling (1x/2x/4x/8x) with antiderivative anti-aliasing (ADAA)
  on the nonlinear clipping stage
- Input and output trim controls with VU-style metering, calibrated to -12 dBu
- True bypass with click-free crossfade

## Controls

| Control | Description |
|---|---|
| Bass | Low-frequency content into the drive stage (interacts with Gain) |
| Gain | Drive amount / clipping stage input level |
| Treble | High-frequency cut after the clipping stage |
| Volume | Output level |
| Clipping (Soft/Medium/Hard) | Selects the diode clipping topology |
| Input Trim / Output Trim | ±12 dB trims with metering, for level matching |
| Oversampling | 1x / 2x / 4x / 8x, applied to the nonlinear clipping stage |
| Bypass | True bypass with crossfade |

## Building

Requires CMake 3.15+, a C++17 compiler, and the JUCE and chowdsp_wdf submodules.

```bash
git clone --recurse-submodules <repo-url>
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --target Tommy_AU    # AU
cmake --build build --target Tommy_VST3  # VST3
```

## Status

This project is under active development. See `CLAUDE.md` for the current
build step and implementation notes.

## License

Tommy is licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPLv3).

## Credits

Built by Leigh Pierce using [JUCE](https://juce.com/) and
[chowdsp_wdf](https://github.com/Chowdhury-DSP/chowdsp_wdf).
