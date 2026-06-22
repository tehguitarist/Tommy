#pragma once
#include <juce_gui_basics/juce_gui_basics.h>
#include "TommyLookAndFeel.h"

// Small circular LED — green when on (pedal active), very dark when off (bypassed).
class LEDIndicator : public juce::Component
{
public:
    void setOn(bool on)
    {
        if (on != isOn)
        {
            isOn = on;
            repaint();
        }
    }

    // NOTE: size this component LARGER than the physical LED footprint when laying it out — the
    // glow is baked into the "on" art, and a component can't draw outside its own bounds (JUCE
    // clips paint() to them), so oversizing has to happen at setBounds() time, not in here.
    void paint(juce::Graphics& g) override
    {
        const auto& img = isOn ? TommyLookAndFeel::getLedOnImage() : TommyLookAndFeel::getLedOffImage();
        TommyLookAndFeel::drawImageCentredAspect(g, img, getLocalBounds().toFloat());
    }

private:
    bool isOn { true };
};
