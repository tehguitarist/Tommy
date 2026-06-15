# Circuit Reference — Tommy (Timmy Clone)

> Source of truth: `updated_schematic_-_timmy.png` (red schematic).
> Cross-reference `older_schematic_-_Timmy.webp` only where the updated one is ambiguous.
> `timmy_switch_refernce.jpg` is authoritative for SW1 topology.

## Signal Path Summary

```
IN → Input Buffer/Bias → [Stage 1: Drive + Bass] → [SW1 Clipping] → [Treble Cut] → [Stage 2: Output Buffer] → [Volume] → OUT
```

VREF = VCC/2 virtual ground. All stages modelled bipolar (VREF = 0V signal ground).
Power supply section excluded — no confirmed audible supply sag in this circuit.

---

## Component Values (from updated schematic — do not approximate)

### Input Network
| Ref  | Value | Function |
|------|-------|----------|
| R1   | 2m2   | Input series resistor |
| C2   | 39n   | Input coupling cap |
| C12  | 47p   | HF shunt (RF filter) |
| R2   | 510k  | Bias resistor to VREF |

### Stage 1 — IC1_A (JRC4559 op-amp, inverting)
| Ref  | Value  | Function |
|------|--------|----------|
| R3   | 3k3    | Input resistor to IC1_A pin 2 (–, inverting input) |
| R7   | 3k3    | Feedback resistor, node_C to DRIVE pot pin 3 |
| C4   | 1µ     | Shunt cap from BASS pot pin 3 / node_C junction to VREF/GND |
| C3   | 39n    | Shunt cap from node_C (IC1_A pin 2) to GND |
| C1   | 100p   | Compensation cap directly across feedback (node_C to node_D) |
| BASS | A50k   | Audio taper 50k — pin 3 to node_C, pin 1 to VREF, wiper (pin 2) back to node_C |

**BASS network:** BASS pot pin 3 connects to node_C (the junction of R3 output, R7 top, IC1_A pin 2). C4 (1µ) shunts BASS pin 3 to VREF — it is a bass-cut shunt at node_C, not a series coupling cap. The BASS wiper (pin 2) reconnects back into node_C. As BASS decreases (wiper toward pin 1/VREF), more of node_C is shunted through the pot resistance to VREF, cutting bass. C3 (39n) also shunts node_C to GND independently. C3 and C4/BASS all interact at node_C — **model as a single coupled network, not independent**.

**DRIVE pot:** A1m audio taper — pin 3 to node_C (R7 junction), pin 1 to node_D (IC1_A output), wiper (pin 2) to node_F (output to treble/clipping network). The full pot resistance (0–1M) sits in the feedback path between node_C and node_D. As DRIVE increases, feedback impedance increases, raising closed-loop gain and driving more signal into the clippers. The wiper taps a point along this resistance — at max DRIVE, node_F ≈ node_C (minimal output); at min DRIVE, node_F ≈ node_D (full output).

### Clipping Stage — SW1 (3-position, three ganged on/off/on SPSTs)
Three topologies — use precomputed scattering matrices, switch at R-type adaptor.
Physical switch is three ganged SPSTs. Positions are defined here by sonic character — UI labels must match these descriptions regardless of which physical direction is "up":

| SW1 Mode | Label in UI | Active Diodes | Character |
|---|---|---|---|
| Mode A | "Soft" | D5+D6 AND D3+D4 (all four, two antiparallel pairs in parallel) | Softest, most symmetrical clipping |
| Mode B | "Medium" | D5+D6 only (one antiparallel pair) | Medium clipping threshold |
| Mode C | "Hard" | D1 only (single diode) | Hardest clip, asymmetric — positive peaks only |

All diodes: **1N4148**
Shockley parameters for 1N4148 (must use these exact values):
- Is = 2.52e-9 A
- Vt = 25.85 mV (thermal voltage at room temp, 300K)
- n (ideality factor) = 1.752
- Rs (series resistance) = 0.568 Ω

### Treble Network (between stages)
| Ref  | Value | Function |
|------|-------|----------|
| TREB | A50k  | Audio taper 50k — treble cut pot |
| R5   | 1k5   | Series resistor |
| C5   | 10n   | Treble cut cap |

### Stage 2 — IC1_B (JRC4559 op-amp, **non-inverting**)
| Ref  | Value | Function |
|------|--------|----------|
| R4   | 3k3    | Gain-set resistor: IC1_B pin 6 (–) to VREF/GND |
| R6   | 3k3    | DC feedback resistor: node_J (pin 7 output) to node_I (pin 6, –) |
| R8   | 10k    | HF feedback branch resistor: node_I (pin 6, –) side of C11+R8 series branch |
| C11  | 2n2    | HF feedback branch cap: node_J (pin 7 output) side of C11+R8 series branch |
| C6   | 1µ     | Output AC coupling cap |
| R11  | 10k    | Output load resistor to GND after C6 |

R9 (8k2), R10 (10k), C7 (47µ), C8 (47µ) are power supply / VREF generation components — **not in signal path, exclude from DSP model entirely.**

**Stage 2 is non-inverting.** IC1_B pin 5 (+, non-inverting input) = node_H (from treble network, after R5/C5). Pin 6 (–, inverting input) = node_I (feedback node). Pin 7 (output) = node_J.

### Output Volume
| Ref  | Value | Function |
|------|-------|----------|
| VOL  | A10k  | Audio taper 10k — output volume pot |

---

## Op-Amp Model

IC1_A and IC1_B are both **JRC4559** (= NJM4559, equivalent to RC4559).
- Dual op-amp, ±18V supply capable, unity-gain stable
- Use **ideal op-amp WDF model** for both stages
- Neither stage is confirmed to clip against rails or slew-limit under normal use
- If future testing shows rail clipping is audible, revisit with nonlinear op-amp model

---

## Pot Tapers (all must be correct — wrong taper = wrong feel/sound)

| Control | Designation | Taper |
|---------|------------|-------|
| BASS    | A50k       | Audio (log) |
| DRIVE   | A1m        | Audio (log) |
| TREB    | A50k       | Audio (log) |
| VOL     | A10k       | Audio (log) |

Audio taper approximation: `R = R_max * pow(10.0, 2.0 * x - 2.0)` where x ∈ [0,1].

---

## Interactive Controls

BASS and DRIVE share the Stage 1 feedback network. They **must not** be modelled as independent controls — they form a coupled RC network inside the WDF tree. Any change to either must update the coupled adaptor parameters together.

TREB interacts with R5/C5 as a passive voltage divider / filter network feeding Stage 2. Model as a coupled WDF network, not an independent shelving EQ.

---

## Nonlinear vs Linear Stage Classification

| Stage | Type | Notes |
|-------|------|-------|
| Input buffer/bias network | Linear | Pure RC, no NL elements |
| Stage 1 (IC1_A, inverting) | Linear (op-amp) | Ideal op-amp; the op-amp stage itself is linear |
| SW1 clipping diodes | **Nonlinear** | Newton-Raphson required; 8x oversampling; ADAA applied here |
| Treble network | Linear | Passive RC, no NL elements |
| Stage 2 (IC1_B, non-inverting) | Linear | Ideal op-amp, no NL elements |
| Volume pot | Linear | Passive attenuator |

---

## Circuit Topology — Node Graphs

This section describes how components connect at each stage. Use these directly to construct WDF trees. Node names are signal nodes; `GND` = signal ground (VREF treated as 0V).

### Stage 0 — Input Network

```
IN ──R1(2m2)──┬── node_A
              C12(47p)
              │
             GND

node_A ──C2(39n)──┬── node_B
                  R2(510k)
                  │
                 GND (VREF)

node_B → IC1_A non-inverting input (+)
```

WDF tree: R1 and C12 form a series-parallel network at the input. C2 is AC coupling. R2 pulls non-inverting input to VREF. Since IC1_A non-inverting input is high impedance and driven to virtual ground by the feedback, this network primarily sets the input impedance and HF rolloff. Model as a linear WDF tree terminated at the op-amp's non-inverting port.

**Key point:** IC1_A non-inverting input (+) is biased to VREF via R2. In the bipolar model this pin is at 0V, so R2 connects to GND. The signal rides on top of this bias.

---

### Stage 1 — IC1_A Drive Stage (inverting amplifier with variable feedback)

IC1_A pin 3 (+) = node_B (from input network, biased to VREF via R2).
IC1_A pin 2 (–) = node_C (inverting input, virtual ground when in closed-loop).
IC1_A pin 1 (output) = node_D.

```
node_B ──R3(3k3)──── node_C (IC1_A pin 2, –)
                          │
              ┌───────────┼───────────────┐
              │           │               │
           C3(39n)    [Feedback]       BASS pot
              │        network            │
             GND                      (see below)
```

**node_C shunt elements** (both directly from node_C to GND):
- C3 (39n): shunt to GND — HF rolloff / input filtering at the inverting node
- BASS pot pin 3 also connects here (with C4 shunting pin 3 to VREF — see BASS detail)

**Feedback network** (between node_C and node_D):
```
node_C ──R7(3k3)──── node_D      (main feedback resistor)
node_C ──C1(100p)─── node_D      (HF compensation cap, directly across R7)
```

**DRIVE pot** (in the feedback path between node_C and node_D):
```
node_C ──R7(3k3)── [DRIVE pin 3]
                   [DRIVE wiper (pin 2)] ── node_F (output to clipping/treble network)
                   [DRIVE pin 1] ── node_D (IC1_A output)
```
R7 feeds into DRIVE pin 3. DRIVE pin 1 connects to node_D (op-amp output). DRIVE wiper is the signal output of Stage 1. As DRIVE increases from 0 to max, more resistance sits between node_C and node_D — raising closed-loop gain and increasing signal amplitude at node_F.

**BASS pot detail:**
```
BASS pin 3 ── node_C
BASS pin 1 ── VREF/GND
BASS wiper (pin 2) ── back to node_C
C4 (1µ) ── from BASS pin 3 (= node_C) to VREF/GND
```
C4 shunts node_C to GND at low frequencies. The BASS pot resistance between pin 3 and pin 1 (in parallel with C4's shunt path) controls how much of this shunting is active. At max BASS (wiper at pin 3), the pot contributes minimal additional loading. At min BASS (wiper at pin 1/GND), the wiper connects node_C to GND through the pot's full resistance, cutting bass more aggressively. The interaction of C4, BASS pot, C3, R3, and R7 all at node_C means they must be modelled as a single coupled WDF network — not independent.

**WDF implication:** Stage 1 has a feedback topology. R-type adaptor required at node_C, incorporating R3, C3, C4/BASS, R7, C1, and the DRIVE pot (treated as a variable series resistance in the R7→node_D path). Op-amp modelled as ideal VCVS.

---

### Stage 1 → Clipping: SW1 Network

The SW1 diode network sits in the feedback path of IC1_A — connected between node_D (IC1_A pin 1, output) and node_C (IC1_A pin 2, –, inverting input), in parallel with the R7+DRIVE feedback resistors. The DRIVE wiper (node_F) taps the signal for passing to the treble stage.

```
node_C ─────────────────────────── node_D
            [SW1 diodes]
        (in parallel with R7+DRIVE feedback)
```

**Diode orientations confirmed from schematic comparison:**
All orientations are stated as anode→cathode in the direction of conventional current flow.

**Mode A — all diodes (softest, symmetric clipping):**
```
node_C ──┬── D6(anode)→D6(cathode) ──┬── node_D   ← D6 conducts on positive node_D swing
         │   D5(cathode)→D5(anode)   │             ← D5 conducts on negative node_D swing
         │   (D5+D6: antiparallel)   │
         └── D3(anode)→D3(cathode) ──┘   ← D3 conducts on positive node_D swing
             D4(cathode)→D4(anode)       ← D4 conducts on negative node_D swing
             (D3+D4: antiparallel, in parallel with D5+D6)
```
Four diodes total. Both polarities clipped symmetrically. Softest threshold (parallel pairs share current).

**Mode B — one antiparallel pair (medium clipping):**
```
node_C ── D6(anode)→D6(cathode) ── node_D
          D5(cathode)→D5(anode)
          (D5+D6 antiparallel pair only)
```

**Mode C — single diode D1 (hardest, asymmetric clipping):**
```
node_C ── D1(anode)→D1(cathode) ── node_D
```
D1 anode is on the node_C (inverting input) side, cathode on the node_D (op-amp output) side. D1 therefore conducts when node_D swings **positive** relative to node_C — clipping positive output peaks only. Negative peaks pass unclipped. This produces asymmetric clipping with even-harmonic content. **Confirmed from updated schematic diode symbol direction and cross-checked against switch reference schematic.**

Each mode is a distinct sub-circuit. Use three precomputed R-type scattering matrices and switch at the R-type adaptor level — no WDF tree reconstruction at runtime.

---

### Treble Network (passive, between Stage 1 and Stage 2)

The TREB pot input (pin 3) connects to node_F (DRIVE wiper / Stage 1 output). TREB pin 1 connects to GND. TREB wiper (pin 2) = node_G.

From node_G, R5 (1k) leads to node_H. From node_H: C5 (10n) shunts to GND, and the wire continues to IC1_B pin 5 (+). C5 is at node_H (after R5), not at the wiper. **Confirmed from updated and older schematic comparison.**

```
node_F ──TREB_upper(0–50k)── node_G
                              │
                         TREB_lower(50k–0)
                              │
                             GND

node_G ──R5(1k)── node_H ── IC1_B pin 5 (+)
                      │
                   C5(10n)
                      │
                     GND
```

**How it works:** TREB_lower shunts node_G toward GND as TREB decreases (wiper toward pin 1), attenuating the signal before it reaches R5. R5+C5 then form a low-pass RC shunt at node_H: at high frequencies C5 is low impedance, shunting HF signal to GND before it reaches pin 5 (+). The corner frequency of the C5 shunt is set by the source impedance driving node_H (TREB_upper ∥ TREB_lower) in series with R5 — as TREB changes, the source impedance changes, shifting the treble-cut corner. **TREB, R5, and C5 are a coupled network — not independent.**

**Corrected WDF tree for treble network:**
```
Series adaptor:
  ├── TREB_upper (variable R, 0→50k)
  └── Parallel adaptor (at node_G):
        ├── TREB_lower (variable R, 50k→0) ── GND
        └── Series adaptor:
              ├── R5 (1k5)
              └── Parallel adaptor (at node_H):
                    ├── C5 (10n) ── GND
                    └── [output port → IC1_B pin 5]
```
Output voltage measured at node_H (after R5, the parallel adaptor junction). TREB_upper + TREB_lower = 50k always.
HF shunt corner (max TREB, TREB_lower≈0, source impedance ≈ R5): f = 1/(2π × 1k5 × 10n) ≈ **10.6 kHz**

---

### Stage 2 — IC1_B Output Stage (non-inverting)

IC1_B pin 5 (+, non-inverting input) = node_H (from treble network — after R5 and C5).
IC1_B pin 6 (–, inverting input) = node_I (feedback node).
IC1_B pin 7 (output) = node_J.

```
node_H ──────────────── IC1_B pin 5 (+)
                              │
                        IC1_B (ideal op-amp)
                              │
                         pin 6 (–) = node_I
                         pin 7 (out) = node_J
```

**Feedback and gain-set network at node_I — confirmed topology:**
```
node_I ──R6(3k3)───────────────────────── node_J   (DC feedback resistor)
node_I ──R8(10k)──C11(2n2)─────────────── node_J   (HF branch: R8 toward node_I, C11 toward node_J)
node_I ──R4(3k3)──────────────────────── VREF/GND  (gain-set resistor to ground)
```

R6 is the plain feedback path, active at all frequencies. R8+C11 in series is a second parallel feedback branch: at LF, C11 is high impedance and this branch is open; at HF, C11 becomes low impedance and R8 parallels R6, increasing feedback and rolling off gain. **C11 is on the node_J (output) side; R8 is on the node_I (inverting input) side.**

DC closed-loop gain = 1 + R6/R4 = 1 + 3k3/3k3 = **+2 (+6 dB)**
HF gain (C11 → short) = 1 + (R6∥R8)/R4 = 1 + (3k3∥10k)/3k3 = 1 + 2k48/3k3 ≈ **1.75 (+4.9 dB)**
HF rolloff corner: f = 1/(2π × R8 × C11) = 1/(2π × 10k × 2n2) ≈ **7.2 kHz**

**Output network:**
```
node_J ──C6(1µ)── node_K
node_K ──R11(10k)── GND
node_K → VOL pot input (pin 3)
```
C6 is AC coupling. R11 (10k) is the DC load to ground after the coupling cap.

**WDF tree for Stage 2:**
Non-inverting op-amp. R-type adaptor at node_I incorporating R4 (3k3, to GND), R6 (3k3, to node_J), and the C11+R8 branch (to node_J). Op-amp modelled as ideal VCVS. All linear — no NR iteration.

---

### Output Volume

```
node_K ──VOL_upper(0–10k)── node_L (output)
          VOL_lower(10k–0) ── GND
```

VOL pot (A10k) as a voltage divider. Output taken at wiper (node_L). VOL_upper + VOL_lower = 10k always.

---

## WDF Adaptor Summary

| Stage | Adaptor Type | Reason |
|-------|-------------|--------|
| Input network | Series/Parallel tree | No feedback loops, purely passive RC |
| Stage 1 feedback network | **R-type** | Feedback topology; multiple branches at node_C (R3, C3, C4/BASS, R7/C1, DRIVE) |
| SW1 clipping (each position) | **R-type** (precomputed ×3) | Nonlinear diodes in feedback path; three distinct topologies |
| Treble network | Series/Parallel tree | No feedback loops, purely passive RC pot divider |
| Stage 2 feedback network | **R-type** | Feedback topology at node_I (R4 to GND, R6 feedback, C11+R8 branch) |
| Volume pot | Parallel tree | Simple resistive voltage divider |

---

## Validation Notes

- All pot tapers are audio (log) for all four controls. The Tayda kit uses linear as a cost substitution — do not follow it. Validate taper subjectively during Step 9.
- C11 (2n2) in Stage 2 HF feedback branch is absent from some traced versions of the circuit. If Stage 2 HF response seems wrong during validation, check this component first.
- C12 (47p) input RF filter is a later revision addition — not present in all traced versions, but present in the updated schematic and retained.
