// Offline renderer: processes a raw float32 mono stream through the REAL Tommy DSP chain +
// the exact PluginProcessor gain staging, so we can A/B against NAM captures of the real pedal.
// Args: in.f32 out.f32 bassX driveX trebX volX modeIdx factorLog2 [sampleRate]
//   *X are 0..1 pot positions; modeIdx 0=Hard(Asym/up) 1=Medium(Open/mid) 2=Soft(Sym/down).
// Mirrors processBlock: work = in*kInputRef -> TommyDSP -> *(kOutputMakeup*volumeGain/kInputRef).

#include "../src/dsp/TommyDSP.h"
#include "../src/utils/TaperUtils.h"

#include <cstdio>
#include <fstream>
#include <vector>

namespace tp = tommy::taper;
using tommy::dsp::Stage1;

// Defaults match PluginProcessor.h; kInputRef overridable via argv[10] for calibration sweeps.
static constexpr double kInputRefDefault = 1.2;
static constexpr double kOutputMakeup = 1.217;

int main (int argc, char** argv)
{
    // Optional overrides beyond argv[9] are documented at their point of use below (argv[10]
    // kInputRef ... argv[24] DriveTilt shelf gain); all are calibration-only and default to shipped.
    if (argc < 9)
    {
        std::fprintf (stderr, "usage: %s in.f32 out.f32 bassX driveX trebX volX modeIdx factorLog2 [sr]\n", argv[0]);
        return 1;
    }
    const char* inPath = argv[1];
    const char* outPath = argv[2];
    const double bassX = std::atof (argv[3]);
    const double driveX = std::atof (argv[4]);
    const double trebX = std::atof (argv[5]);
    const double volX = std::atof (argv[6]);
    const int modeIdx = std::atoi (argv[7]);
    const int factorLog2 = std::atoi (argv[8]);
    const double sr = (argc > 9) ? std::atof (argv[9]) : 48000.0;
    const double kInputRef = (argc > 10) ? std::atof (argv[10]) : kInputRefDefault;
    // Optional treble taper override for fitting: TREB_R = coeff * trebX^exp (argv[11], argv[12]).
    const double trebCoeff = (argc > 11) ? std::atof (argv[11]) : -1.0;
    const double trebExp = (argc > 12) ? std::atof (argv[12]) : 1.43;
    // Optional bass taper override: BASS_R = coeff * bassX^exp (argv[13], argv[14]).
    const double bassCoeff = (argc > 13) ? std::atof (argv[13]) : -1.0;
    const double bassExp = (argc > 14) ? std::atof (argv[14]) : 1.43;
    // Optional asym-mode diode-mismatch override (argv[15]); argv[16] unused (kept for arg layout).
    const double asymBias = (argc > 15) ? std::atof (argv[15]) : -1.0;
    // Optional drive taper override: DRIVE_R = coeff * driveX^exp (argv[17], argv[18]).
    const double driveCoeff = (argc > 17) ? std::atof (argv[17]) : -1.0;
    const double driveExp = (argc > 18) ? std::atof (argv[18]) : 1.0;
    // Optional supply voltage (argv[19]): 9/12/18 V scales the op-amp rails. Default 9 V.
    const double supplyV = (argc > 19) ? std::atof (argv[19]) : 9.0;
    // Optional Soft/Medium diode-mismatch override (argv[20]; <0 = keep shipped kSymMismatch).
    const double symBias = (argc > 20) ? std::atof (argv[20]) : -1.0;
    // Optional Medium-branch diode overrides for the W1 fit (argv[21]=Is, argv[22]=ideality n;
    // <=0 = keep the shipped kIsMedium/kNMedium). Soft is intentionally NOT overridable.
    const double medIs = (argc > 21) ? std::atof (argv[21]) : -1.0;
    const double medN = (argc > 22) ? std::atof (argv[22]) : -1.0;
    // Optional rail-clip ADAA disable (argv[23]: 0 = off, anything else/absent = shipped ON). Exists
    // for v1.4 W3: ADAA band-limits the rail-clip corner, so it is a candidate for the model's
    // top-octave energy deficit at high drive. Off is NOT a shipping configuration (it re-opens the
    // aliasing ADAA exists to suppress) — measurement only.
    const bool adaaOn = (argc > 23) ? (std::atoi (argv[23]) != 0) : true;
    // Optional DriveTilt shelf-gain override (argv[24]; <0 = keep the shipped kMaxGainDB). Exists
    // for v1.4 W2: DriveTilt is fitted against the same low-drive captures the DRIVE taper is, so a
    // taper re-fit has to be able to re-check the shelf jointly instead of assuming it still holds.
    const double tiltGainDB = (argc > 24) ? std::atof (argv[24]) : -1.0;
    // Optional BassTilt strength scale (argv[25]; <0 = shipped 1.0, 0 = correction disabled).
    // Exists for v1.4 W4: the LF correction is an empirical fit, so the harness must be able to
    // A/B it and re-verify the fit without a rebuild. 0.0 reproduces pre-W4 renders exactly.
    const double bassTiltScale = (argc > 25) ? std::atof (argv[25]) : -1.0;
    // Optional BASS-network cap overrides in FARADS (argv[26]=C3, argv[27]=C4; <=0 = shipped
    // 39n/1u). v1.4 W4: these two caps dominate the deep-LF cut and sit PRE-clip, and circuit.md
    // (the only surviving source, schematics removed) is internally inconsistent about this exact
    // network — so the harness must be able to ask whether a component value, rather than an
    // empirical output shelf, is the real explanation. See Stage1T::setBassCaps.
    const double c3Override = (argc > 26) ? std::atof (argv[26]) : -1.0;
    const double c4Override = (argc > 27) ? std::atof (argv[27]) : -1.0;

    // modeIdx 3 = Linear (NO clipping diodes at all; the op-amp rail clip still applies). Not a
    // shipped plugin mode — it exists so the analysis harness can test the hypothesis that SW1's
    // middle position is genuinely OPEN (all three ganged on/off/on gangs off => no diode branch
    // in circuit), which is what the "Open" UI label and the pedal's measured Medium knee suggest.
    static const Stage1::ClipMode modes[] = { Stage1::ClipMode::Hard, Stage1::ClipMode::Medium,
                                              Stage1::ClipMode::Soft, Stage1::ClipMode::Linear };
    const auto mode = modes[modeIdx < 0 ? 0 : (modeIdx > 3 ? 3 : modeIdx)];

    // Read raw float32
    std::ifstream in (inPath, std::ios::binary | std::ios::ate);
    if (! in) { std::fprintf (stderr, "cannot open %s\n", inPath); return 1; }
    const auto bytes = (size_t) in.tellg();
    in.seekg (0);
    std::vector<float> raw (bytes / sizeof (float));
    in.read (reinterpret_cast<char*> (raw.data()), (std::streamsize) bytes);
    const int total = (int) raw.size();

    constexpr int blk = 512;
    tommy::dsp::TommyDSP dsp;
    dsp.prepare (sr, blk, factorLog2);
    const double trebR = (trebCoeff > 0.0) ? trebCoeff * std::pow (trebX, trebExp)
                                           : tp::trebleResistance (trebX);
    const double bassR = (bassCoeff > 0.0) ? bassCoeff * std::pow (bassX, bassExp)
                                           : tp::bassResistance (bassX);
    const double driveR = (driveCoeff > 0.0) ? driveCoeff * std::pow (driveX, driveExp)
                                             : tp::driveResistance (driveX);
    dsp.setControls (bassR, driveR, trebR, mode);
    dsp.setDrivePosition (driveX); // drive-faded top-octave tilt correction (matches PluginProcessor)
    dsp.setSupplyVoltage (supplyV);
    if (asymBias >= 0.0)
        dsp.setAsymMismatch (asymBias);
    if (symBias >= 0.0)
        dsp.setSymMismatch (symBias);
    if (medIs > 0.0 || medN > 0.0)
        dsp.setMediumDiodeParams (medIs, medN);
    dsp.setAdaaEnabled (adaaOn);
    if (tiltGainDB >= 0.0)
        dsp.setDriveTiltGainDB (tiltGainDB);
    if (bassTiltScale >= 0.0)
        dsp.setBassTiltScale (bassTiltScale);
    if (c3Override > 0.0 || c4Override > 0.0)
        dsp.setBassCaps (c3Override, c4Override); // after prepare() — see TommyDSP::setBassCaps

    const double outGain = kOutputMakeup * tp::volumeGain (volX) / kInputRef;

    std::vector<float> outBuf ((size_t) total);
    std::vector<double> work (blk);
    for (int start = 0; start < total; start += blk)
    {
        const int n = std::min (blk, total - start);
        for (int i = 0; i < n; ++i)
            work[(size_t) i] = (double) raw[(size_t) (start + i)] * kInputRef;
        dsp.processBlock (work.data(), n);
        for (int i = 0; i < n; ++i)
            outBuf[(size_t) (start + i)] = (float) (work[(size_t) i] * outGain);
    }

    std::ofstream out (outPath, std::ios::binary);
    out.write (reinterpret_cast<const char*> (outBuf.data()), (std::streamsize) (outBuf.size() * sizeof (float)));
    std::fprintf (stderr, "rendered %d samples -> %s (bass %.2f drive %.2f treb %.2f vol %.2f mode %d os %dx)\n",
                  total, outPath, bassX, driveX, trebX, volX, modeIdx, 1 << factorLog2);
    return 0;
}
