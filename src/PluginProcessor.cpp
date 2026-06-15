#include "PluginProcessor.h"
#include "PluginEditor.h"

TommyAudioProcessor::TommyAudioProcessor()
    : AudioProcessor (BusesProperties()
                           .withInput ("Input", juce::AudioChannelSet::stereo(), true)
                           .withOutput ("Output", juce::AudioChannelSet::stereo(), true)),
      apvts (*this, nullptr, "PARAMETERS", createParameterLayout())
{
}

TommyAudioProcessor::~TommyAudioProcessor() = default;

juce::AudioProcessorValueTreeState::ParameterLayout TommyAudioProcessor::createParameterLayout()
{
    std::vector<std::unique_ptr<juce::RangedAudioParameter>> params;

    params.push_back (std::make_unique<juce::AudioParameterFloat> ("bass", "Bass",
        juce::NormalisableRange<float> (0.0f, 1.0f), 0.5f));

    params.push_back (std::make_unique<juce::AudioParameterFloat> ("drive", "Gain",
        juce::NormalisableRange<float> (0.0f, 1.0f), 0.5f));

    params.push_back (std::make_unique<juce::AudioParameterFloat> ("treble", "Treble",
        juce::NormalisableRange<float> (0.0f, 1.0f), 0.5f));

    params.push_back (std::make_unique<juce::AudioParameterFloat> ("volume", "Volume",
        juce::NormalisableRange<float> (0.0f, 1.0f), 0.5f));

    params.push_back (std::make_unique<juce::AudioParameterChoice> ("clipping_mode", "Clipping",
        juce::StringArray { "Soft", "Medium", "Hard" }, 0));

    params.push_back (std::make_unique<juce::AudioParameterFloat> ("input_trim", "Input Trim",
        juce::NormalisableRange<float> (-12.0f, 12.0f), 0.0f));

    params.push_back (std::make_unique<juce::AudioParameterFloat> ("output_trim", "Output Trim",
        juce::NormalisableRange<float> (-12.0f, 12.0f), 0.0f));

    params.push_back (std::make_unique<juce::AudioParameterChoice> ("oversampling", "Oversampling",
        juce::StringArray { "1x", "2x", "4x", "8x" }, 2));

    params.push_back (std::make_unique<juce::AudioParameterBool> ("bypass", "Bypass", false));

    return { params.begin(), params.end() };
}

void TommyAudioProcessor::prepareToPlay (double, int)
{
}

void TommyAudioProcessor::releaseResources()
{
}

bool TommyAudioProcessor::isBusesLayoutSupported (const BusesLayout& layouts) const
{
    return layouts.getMainOutputChannelSet() == juce::AudioChannelSet::stereo()
        && layouts.getMainInputChannelSet() == juce::AudioChannelSet::stereo();
}

void TommyAudioProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer&)
{
    juce::ScopedNoDenormals noDenormals;

    for (auto channel = getTotalNumInputChannels(); channel < getTotalNumOutputChannels(); ++channel)
        buffer.clear (channel, 0, buffer.getNumSamples());
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
    return 1;
}

int TommyAudioProcessor::getCurrentProgram()
{
    return 0;
}

void TommyAudioProcessor::setCurrentProgram (int)
{
}

const juce::String TommyAudioProcessor::getProgramName (int)
{
    return {};
}

void TommyAudioProcessor::changeProgramName (int, const juce::String&)
{
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
