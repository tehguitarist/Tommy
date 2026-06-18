# Circuit Reference — <PEDAL NAME>  (TEMPLATE — fill in from the schematic)

> This file is the **source of truth** for component values and topology. Fill every `<...>`
> placeholder by reading the schematic directly. Do NOT approximate or copy values from a build
> kit / forum trace without confirming against the primary schematic.

## Schematics

List every image in `schematics/` and its role (which is authoritative for what):

| File | Role |
|------|------|
| `<primary>.png` | Primary source of truth for values + topology |
| `<switch_ref>.jpg` | Authoritative for switch/diode network |
| `<older>.png` | Cross-reference only — values may differ |

---

## ⚠ Schematic-reading gotchas (these caused real bugs)

- **Resistor value notation:** `2m2` / `2M2` means **2.2 MΩ**, `2k2` = 2.2 kΩ, `2R2` = 2.2 Ω. The
  letter is the decimal point AND the multiplier. Misreading `2m2` as 2.2 Ω (or 2.2 mΩ) is an easy
  ~6-orders-of-magnitude error. Double-check every R against its neighbours' magnitudes.
- **Series vs pulldown:** a large resistor (e.g. 2.2 MΩ) at the input is usually a **pulldown to
  ground** (bias/pop suppression), not a series element. A 2.2 MΩ *series* resistor would attenuate
  ~14 dB and roll off treble hard — if your model does that, you've mis-traced the topology.
- **Pot wiring:** confirm pin1/pin3/wiper → node mapping for every pot. "Rheostat" (wiper jumpered
  to an end, no ground leg) behaves very differently from a "divider". Trace it; don't assume.
- **Taper:** note the designation (A = audio/log, B = linear). Kits sometimes substitute — follow
  the schematic, not the kit.
- **Op-amp inverting vs non-inverting:** verify which input the signal enters. Confirm output
  polarity later with a DC-step test per stage.
- **Power section parts in the signal columns:** supply-filter R/C (and any series Schottky) can be
  mislabelled as signal-path parts. Exclude VREF-divider and supply-filter components from the DSP
  model.

---

## Signal path summary

```
IN → <input/bias> → <stage 1 ...> → <clip?> → <tone?> → <recovery> → <volume> → OUT
```
VREF = VCC/2 virtual ground; model bipolar (VREF = 0 V signal ground). Note the supply (e.g. single
9 V, no charge pump) since it sets op-amp output headroom — see calibration doc §6.

## Component values (from `<primary>` — do not approximate)

### <Stage / network name>
| Ref | Value | Function |
|-----|-------|----------|
| `<R?>` | `<value>` | `<role>` |
| `<C?>` | `<value>` | `<role>` |
| `<pot>` | `<A/B + value>` | `<taper + role>` |

(Repeat a table per network: input, each gain stage, clipping/diode network, tone, recovery,
output volume.)

### Nonlinear devices
- Diode/transistor type: `<e.g. 1N4148>`. **Use exact datasheet/Shockley params** (Is, Vt, n, Rs).
  `nDiodes` in chowdsp = ideality factor n, NOT a count.

## Topology — node graphs

Describe each stage's connections at the node level (use these directly to build the WDF tree).
Mark each stage **Linear** or **Nonlinear**, and which adaptor type it needs (series/parallel tree
vs R-type for feedback). For switched sub-circuits, list each position as a distinct topology →
precomputed scattering matrix.

## Op-amp model

- Part + supply; not rail-to-rail → model asymmetric output saturation (calibration doc §6).
- Ideal op-amp for the gain/feedback solve; rails as a separate output clamp.

## Interactive / coupled controls

List any controls that share a network and MUST be modelled coupled (not independent), e.g. a tone
control inside a feedback web. Note `ScopedDeferImpedancePropagation` when updating them together.

## Validation notes

Record anything that differs between schematic versions, any component absent from some traces, and
any value you had to resolve by measurement/judgement (with the reasoning).
