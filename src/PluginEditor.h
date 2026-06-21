#pragma once

#include "PluginProcessor.h"
#include "ui/TommyLookAndFeel.h"
#include "ui/VUMeter.h"
#include "ui/SW1Switch.h"
#include "ui/SupplyControl.h"
#include "ui/LEDIndicator.h"

#include <juce_audio_processors/juce_audio_processors.h>

class TommyAudioProcessorEditor : public juce::AudioProcessorEditor,
                                   public juce::Timer
{
public:
    explicit TommyAudioProcessorEditor(TommyAudioProcessor&);
    ~TommyAudioProcessorEditor() override;

    void paint(juce::Graphics&) override;
    void resized() override;
    void timerCallback() override;

    static constexpr int kBaseW = 420;
    static constexpr int kBaseH = 458;

private:
    TommyAudioProcessor& audioProcessor;
    TommyLookAndFeel laf;

    float currentScale       { 1.0f };  // physical_width / kBaseW; updated each resized()
    int   sepLineY           { 0 };     // separator below power label, set in resized()

    juce::ApplicationProperties appProps;

    void refreshFonts(float sc);
    void showScaleMenu();

    // ── Side panels ──────────────────────────────────────────────────────────
    juce::Label  inputPanelLabel  { {}, "INPUT"  };
    juce::Slider inputTrimKnob;
    juce::Label  inputTrimLabel   { {}, "TRIM"   };
    VUMeter      inputVU;

    juce::Label  outputPanelLabel { {}, "OUTPUT" };
    juce::Slider outputTrimKnob;
    juce::Label  outputTrimLabel  { {}, "TRIM"   };
    VUMeter      outputVU;

    // ── Pedal face ───────────────────────────────────────────────────────────
    SupplyControl supplyControl;
    juce::Slider bassKnob, gainKnob, volumeKnob, trebleKnob;
    juce::Label  bassLabel    { {}, "BASS"   };
    juce::Label  gainLabel    { {}, "GAIN"   };
    juce::Label  volumeLabel  { {}, "VOLUME" };
    juce::Label  trebleLabel  { {}, "TREBLE" };
    SW1Switch    sw1Switch;
    LEDIndicator led;
    juce::Label  tommyLogo    { {}, "Tommy"  };
    juce::TextButton bypassButton { "" };
    juce::Label  bypassLabel  { {}, "BYPASS" };

    // ── Oversampling strip ───────────────────────────────────────────────────
    juce::Label    osLabel      { {}, "OS"     };
    juce::Label    osLiveLabel  { {}, "LIVE"   };
    juce::Label    osBncLabel   { {}, "RENDER" };
    juce::ComboBox osRealtimeBox, osRenderBox;
    std::unique_ptr<juce::ComboBoxParameterAttachment> osRealtimeAttach, osRenderAttach;
    juce::Label    sizeLabel    { {}, "UI SIZE" };
    juce::TextButton scaleBtn;

    // ── APVTS attachments ────────────────────────────────────────────────────
    juce::SliderParameterAttachment bassAttach, gainAttach, volumeAttach, trebleAttach;
    juce::SliderParameterAttachment inTrimAttach, outTrimAttach;
    juce::ButtonParameterAttachment bypassAttach;
    juce::ParameterAttachment       clipAttach;
    juce::ParameterAttachment       supplyAttach;

    // Stored in resized(), used in paint()
    juce::Rectangle<int> pedalBounds;
    juce::Rectangle<int> osPanelBounds;

    void configureKnob(juce::Slider& s);
    void configureTrimKnob(juce::Slider& s);
    void configureLabel(juce::Label& l, float fontSize, juce::uint32 colour,
                        juce::Justification just = juce::Justification::centred);

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(TommyAudioProcessorEditor)
};
