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
static constexpr double kOutputMakeup = 0.9;

int main (int argc, char** argv)
{
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
    // Optional asym-mode lateral bias override (argv[15]); argv[16] unused (kept for arg layout).
    const double asymBias = (argc > 15) ? std::atof (argv[15]) : -1.0;
    // Optional drive taper override: DRIVE_R = coeff * driveX^exp (argv[17], argv[18]).
    const double driveCoeff = (argc > 17) ? std::atof (argv[17]) : -1.0;
    const double driveExp = (argc > 18) ? std::atof (argv[18]) : 1.0;
    // Optional supply voltage (argv[19]): 9/12/18 V scales the op-amp rails. Default 9 V.
    const double supplyV = (argc > 19) ? std::atof (argv[19]) : 9.0;

    static const Stage1::ClipMode modes[] = { Stage1::ClipMode::Hard, Stage1::ClipMode::Medium,
                                              Stage1::ClipMode::Soft };
    const auto mode = modes[modeIdx < 0 ? 0 : (modeIdx > 2 ? 2 : modeIdx)];

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
    dsp.setSupplyVoltage (supplyV);
    if (asymBias >= 0.0)
        dsp.setAsymBias (asymBias);
    dsp.setAdaaEnabled (true);

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
