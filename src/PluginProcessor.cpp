#include "PluginProcessor.h"
#include "PluginEditor.h"
#include "utils/TaperUtils.h"

#include <cmath>

TommyAudioProcessor::TommyAudioProcessor()
    : AudioProcessor (BusesProperties()
                           .withInput ("Input", juce::AudioChannelSet::stereo(), true)
                           .withOutput ("Output", juce::AudioChannelSet::stereo(), true)),
      apvts (*this, nullptr, "PARAMETERS", createParameterLayout())
{
    pBass = apvts.getRawParameterValue ("bass");
    pDrive = apvts.getRawParameterValue ("drive");
    pTreble = apvts.getRawParameterValue ("treble");
    pVolume = apvts.getRawParameterValue ("volume");
    pClip = apvts.getRawParameterValue ("clipping_mode");
    pInTrim = apvts.getRawParameterValue ("input_trim");
    pOutTrim = apvts.getRawParameterValue ("output_trim");
    pOversampling  = apvts.getRawParameterValue ("oversampling");
    pRenderOs      = apvts.getRawParameterValue ("render_oversampling");
    pBypass        = apvts.getRawParameterValue ("bypass");
    pSupply        = apvts.getRawParameterValue ("supply_voltage");
}

TommyAudioProcessor::~TommyAudioProcessor() = default;

juce::AudioProcessorValueTreeState::ParameterLayout TommyAudioProcessor::createParameterLayout()
{
    std::vector<std::unique_ptr<juce::RangedAudioParameter>> params;

    params.push_back (std::make_unique<juce::AudioParameterFloat> ("bass", "Bass",
        juce::NormalisableRange<float> (0.0f, 1.0f), 0.0f)); // default: knob at minimum

    params.push_back (std::make_unique<juce::AudioParameterFloat> ("drive", "Gain",
        juce::NormalisableRange<float> (0.0f, 1.0f), 0.0f)); // default: knob at minimum

    params.push_back (std::make_unique<juce::AudioParameterFloat> ("treble", "Treble",
        juce::NormalisableRange<float> (0.0f, 1.0f), 0.0f)); // default: knob at minimum

    // Default: knob at 1 o'clock. The JUCE default rotary sweep runs 1.2pi -> 2.8pi (216 deg ->
    // 504 deg, a 288 deg total sweep) with normalised 0.5 landing on 12 o'clock; 1 o'clock is 30
    // deg further clockwise, i.e. 0.5 + 30/288.
    params.push_back (std::make_unique<juce::AudioParameterFloat> ("volume", "Volume",
        juce::NormalisableRange<float> (0.0f, 1.0f), 0.5f + 30.0f / 288.0f));

    // Choices ordered to match physical switch (top→bottom): Asym / Open / Sym.
    // Index 0 = top lever (asymmetric, single diode), 1 = middle (high-headroom symmetric),
    // 2 = bottom (heavy symmetric saturation, all diodes). See TaperUtils mode mapping.
    params.push_back (std::make_unique<juce::AudioParameterChoice> ("clipping_mode", "Clipping",
        juce::StringArray { "Asymmetric", "Open", "Symmetric" }, 1)); // default: middle (Open)

    params.push_back (std::make_unique<juce::AudioParameterFloat> ("input_trim", "Input Trim",
        juce::NormalisableRange<float> (-12.0f, 12.0f), 0.0f));

    params.push_back (std::make_unique<juce::AudioParameterFloat> ("output_trim", "Output Trim",
        juce::NormalisableRange<float> (-12.0f, 12.0f), 0.0f));

    params.push_back (std::make_unique<juce::AudioParameterChoice> ("oversampling", "Oversampling",
        juce::StringArray { "1x", "2x", "4x", "8x" }, 2));

    params.push_back (std::make_unique<juce::AudioParameterChoice> ("render_oversampling", "Render Oversampling",
        juce::StringArray { "1x", "2x", "4x", "8x" }, 3)); // default 8x for offline bouncing

    params.push_back (std::make_unique<juce::AudioParameterBool> ("bypass", "Bypass", false));

    params.push_back (std::make_unique<juce::AudioParameterChoice> ("supply_voltage", "Supply",
        juce::StringArray { "9V", "12V", "18V" }, 0)); // default 9V (the stock pedal)

    return { params.begin(), params.end() };
}

const std::array<TommyAudioProcessor::FactoryPreset, 5> TommyAudioProcessor::factoryPresets { {
    { "Bluesy OD",        5.0f, 3.0f, 5.0f, 6.0f,   2 },
    { "Rhythm Crunch",    4.0f, 4.5f, 4.5f, 7.0f,   1 },
    { "Rock Lead",        3.5f, 6.5f, 4.5f, 7.5f,   1 },
    { "High Gain",        7.5f, 8.0f, 4.0f, 6.5f,   0 },
    { "Edge-of-Breakup",  5.5f, 4.0f, 4.5f, 6.5f,   1 },
} };

void TommyAudioProcessor::prepareToPlay (double sampleRate, int samplesPerBlock)
{
    currentSampleRate = sampleRate;
    maxBlock = samplesPerBlock;
    currentFactorLog2 = (int) (pOversampling != nullptr ? pOversampling->load() : 2.0f);

    for (auto& ch : dsp)
    {
        ch.prepare (sampleRate, samplesPerBlock, currentFactorLog2);
        ch.setAdaaEnabled (true); // ADAA on both op-amp rail clips (dsp.md) — in addition to OS
        ch.reset();
    }

    scratch.setSize (2, samplesPerBlock);

    const double smoothSec = 0.01; // 10 ms — no zipper on level controls
    inputGain.reset (sampleRate, smoothSec);
    outputGain.reset (sampleRate, smoothSec);
    bypassMix.reset (sampleRate, 0.005); // ~5 ms bypass crossfade

    inputGain.setCurrentAndTargetValue (1.0f);
    outputGain.setCurrentAndTargetValue (kOutputMakeup);
    const bool startBypassed = pBypass != nullptr && pBypass->load() > 0.5f;
    bypassMix.setCurrentAndTargetValue (startBypassed ? 1.0f : 0.0f);

    setLatencySamples ((int) std::lround (dsp[0].getLatencySamples()));
}

void TommyAudioProcessor::releaseResources()
{
}

bool TommyAudioProcessor::isBusesLayoutSupported (const BusesLayout& layouts) const
{
    const auto& in  = layouts.getMainInputChannelSet();
    const auto& out = layouts.getMainOutputChannelSet();

    if (in  != juce::AudioChannelSet::mono() && in  != juce::AudioChannelSet::stereo())
        return false;
    if (out != juce::AudioChannelSet::mono() && out != juce::AudioChannelSet::stereo())
        return false;

    // Allow mono→mono, mono→stereo, stereo→stereo. Not stereo→mono.
    return in.size() <= out.size();
}

void TommyAudioProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer&)
{
    juce::ScopedNoDenormals noDenormals;

    const int numSamples = buffer.getNumSamples();
    const int numCh = juce::jmin (buffer.getNumChannels(), 2);

    for (int channel = getTotalNumInputChannels(); channel < getTotalNumOutputChannels(); ++channel)
        buffer.clear (channel, 0, numSamples);

    // 1. Oversampling factor — choose realtime or render parameter depending on context.
    const int wantFactor = isNonRealtime()
        ? (pRenderOs != nullptr ? (int) pRenderOs->load() : 3)
        : (int) pOversampling->load();
    if (wantFactor != currentFactorLog2)
    {
        currentFactorLog2 = wantFactor;
        for (auto& ch : dsp)
            ch.setFactor (currentFactorLog2);
        setLatencySamples ((int) std::lround (dsp[0].getLatencySamples()));
    }

    // 2. Read params; map pot rotations to WDF resistances / gains (block-rate WDF update).
    const auto bassR = tommy::taper::bassResistance (pBass->load());
    const auto driveR = tommy::taper::driveResistance (pDrive->load());
    const auto trebR = tommy::taper::trebleResistance (pTreble->load());
    const auto volGain = tommy::taper::volumeGain (pVolume->load());
    // Physical switch top→bottom: Asym (single diode) / Open (one pair) / Sym (all diodes).
    // pClip index 0/1/2 maps to ClipMode Hard/Medium/Soft respectively.
    static constexpr tommy::dsp::Stage1::ClipMode kClipModes[] = {
        tommy::dsp::Stage1::ClipMode::Hard,   // 0 = top = asymmetric, single diode D1
        tommy::dsp::Stage1::ClipMode::Medium, // 1 = middle = high-headroom symmetric, one pair
        tommy::dsp::Stage1::ClipMode::Soft,   // 2 = bottom = heavy symmetric, all four diodes
    };
    const auto mode = kClipModes[juce::jlimit (0, 2, (int) pClip->load())];

    inputGain.setTargetValue ((float) tommy::taper::dbToGain (pInTrim->load()));
    // 1/kInputRef converts the circuit's volt-domain output back to DAW full-scale; it cancels the
    // kInputRef applied at the input for the linear path, leaving kOutputMakeup as the level trim.
    outputGain.setTargetValue (
        (float) (kOutputMakeup * volGain * tommy::taper::dbToGain (pOutTrim->load()) / kInputRef));
    const bool wantBypass = pBypass->load() > 0.5f;
    bypassMix.setTargetValue (wantBypass ? 1.0f : 0.0f);
    bypassed.store (wantBypass);

    // Supply voltage: choice index 0/1/2 -> 9/12/18 V (scales the op-amp output rails / headroom).
    static constexpr double kSupplyVolts[] = { 9.0, 12.0, 18.0 };
    const double supplyV = kSupplyVolts[juce::jlimit (0, 2, (int) pSupply->load())];

    for (auto& ch : dsp)
    {
        ch.setControls (bassR, driveR, trebR, mode);
        ch.setSupplyVoltage (supplyV);
    }

    // 3. Per channel: input trim + meter, run the WDF chain in double, crossfade bypass, out meter.
    // Process only actual input channels; if mono-in/stereo-out we copy ch0 to ch1 afterward.
    const int numInputCh = getMainBusNumInputChannels();
    const int channelsToProcess = juce::jmin (numInputCh, 2);

    float inPeak[2] = { 0.0f, 0.0f }, outPeak[2] = { 0.0f, 0.0f };
    for (int c = 0; c < channelsToProcess; ++c)
    {
        auto* in = buffer.getWritePointer (c);
        auto* work = scratch.getWritePointer (c);

        // Input trim + dry copy (for bypass crossfade) + input metering.
        // The meter and bypass dry path stay in DAW (full-scale) domain; only the signal handed
        // to the WDF chain is scaled to real volts by kInputRef (undone by 1/kInputRef at output).
        auto inG = inputGain;
        for (int i = 0; i < numSamples; ++i)
        {
            const float g = inG.getNextValue();
            const float dry = in[i];
            const float wet = dry * g;
            work[i] = (double) wet * kInputRef;
            inPeak[c] = juce::jmax (inPeak[c], std::abs (wet));
        }

        dsp[(size_t) c].processBlock (work, numSamples);

        // Hard-gate sub-threshold DSP output to prevent inaudible WDF residuals leaking.
        // If every sample is below ~-140 dBFS the whole block is zeroed; early-exit avoids
        // checking every sample for a normally-active block.
        {
            bool hasSig = false;
            for (int n = 0; n < numSamples && !hasSig; ++n)
                hasSig = (work[n] * work[n] > 1e-14);
            if (!hasSig)
                std::fill (work, work + numSamples, 0.0);
        }

        // Output makeup * volume * output trim, then crossfade against the dry input.
        auto outG = outputGain;
        auto mix = bypassMix;
        for (int i = 0; i < numSamples; ++i)
        {
            const float processed = (float) work[i] * outG.getNextValue();
            const float m = mix.getNextValue();
            const float y = processed * (1.0f - m) + in[i] * m;
            in[i] = y;
            outPeak[c] = juce::jmax (outPeak[c], std::abs (y));
        }
    }

    // Mono-in / stereo-out: copy the processed mono channel to the second output channel.
    if (numInputCh == 1 && numCh == 2)
        buffer.copyFrom (1, 0, buffer, 0, 0, numSamples);

    // Mirror the smoothers' consumed state across channels by advancing once for real (above we
    // copied the smoothers per channel so each channel ramps identically from the same start).
    inputGain.skip (numSamples);
    outputGain.skip (numSamples);
    bypassMix.skip (numSamples);

    inputLevelL.store (inPeak[0]);
    inputLevelR.store (channelsToProcess > 1 ? inPeak[1] : inPeak[0]);
    outputLevelL.store (outPeak[0]);
    outputLevelR.store (channelsToProcess > 1 ? outPeak[1] : outPeak[0]);
}

juce::AudioProcessorEditor* TommyAudioProcessor::createEditor()
{
    return new TommyAudioProcessorEditor (*this);
}

bool TommyAudioProcessor::hasEditor() const
{
    return true;
}

const juce::String TommyAudioProcessor::getName() const
{
    return JucePlugin_Name;
}

bool TommyAudioProcessor::acceptsMidi() const
{
    return false;
}

bool TommyAudioProcessor::producesMidi() const
{
    return false;
}

double TommyAudioProcessor::getTailLengthSeconds() const
{
    return 0.0;
}

int TommyAudioProcessor::getNumPrograms()
{
    return (int) factoryPresets.size();
}

int TommyAudioProcessor::getCurrentProgram()
{
    return currentProgramIndex;
}

void TommyAudioProcessor::setCurrentProgram (int index)
{
    if (index < 0 || index >= (int) factoryPresets.size())
        return;

    currentProgramIndex = index;
    const auto& preset = factoryPresets[(size_t) index];

    auto setNorm = [this] (const char* paramId, float normalised)
    {
        if (auto* param = apvts.getParameter (paramId))
            param->setValueNotifyingHost (normalised);
    };

    setNorm ("bass", preset.bass / 10.0f);
    setNorm ("drive", preset.drive / 10.0f);
    setNorm ("treble", preset.treble / 10.0f);
    setNorm ("volume", preset.volume / 10.0f);
    setNorm ("clipping_mode", (float) preset.clipMode / 2.0f); // 3 choices -> normalised index/2
}

const juce::String TommyAudioProcessor::getProgramName (int index)
{
    if (index < 0 || index >= (int) factoryPresets.size())
        return {};

    return factoryPresets[(size_t) index].name;
}

void TommyAudioProcessor::changeProgramName (int, const juce::String&)
{
    // Factory presets are read-only; hosts that allow renaming have nothing to persist here.
}

void TommyAudioProcessor::getStateInformation (juce::MemoryBlock& destData)
{
    if (auto state = apvts.copyState(); true)
    {
        juce::MemoryOutputStream stream (destData, true);
        state.writeToStream (stream);
    }
}

void TommyAudioProcessor::setStateInformation (const void* data, int sizeInBytes)
{
    if (auto tree = juce::ValueTree::readFromData (data, (size_t) sizeInBytes); tree.isValid())
        apvts.replaceState (tree);
}

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new TommyAudioProcessor();
}
