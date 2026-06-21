#pragma once
#include <juce_gui_basics/juce_gui_basics.h>
#include "TommyLookAndFeel.h"

// Interactive supply-voltage selector, styled as the pedal's "(+) 9V (-)" power label at the top of
// the face. Click "(+)" (left) to raise the supply (9 -> 12 -> 18 V), "(-)" (right) to lower it.
// "(+)" is lit when a higher voltage is available, "(-)" when a lower one is; the centre shows the
// current voltage. Bound to the supply_voltage choice parameter via a ParameterAttachment in the
// editor (same pattern as SW1Switch / clipping_mode).
class SupplyControl : public juce::Component
{
public:
    std::function<void(int)> onChange; // emits the new index 0..2 (9 / 12 / 18 V)

    SupplyControl() { setMouseCursor(juce::MouseCursor::PointingHandCursor); }

    void setIndex(int idx)
    {
        idx = juce::jlimit(0, 2, idx);
        if (idx != index) { index = idx; repaint(); }
    }
    int  getIndex() const { return index; }
    void setFontSize(float px) { fontPx = px; repaint(); }

    void paint(juce::Graphics& g) override
    {
        static const char* const volts[] = { "9V", "12V", "18V" };
        g.setFont(juce::Font(juce::FontOptions(fontPx, juce::Font::bold)));

        const auto r     = getLocalBounds().toFloat();
        const float third = r.getWidth() / 3.0f;
        const auto lit   = juce::Colour(TommyLookAndFeel::cPowerLabelLit);
        const auto dim   = juce::Colour(TommyLookAndFeel::cPowerLabel);

        g.setColour(index < 2 ? lit : dim); // "(+)" lit when a higher voltage is available
        g.drawText("(+)", juce::Rectangle<float>(r.getX(), r.getY(), third, r.getHeight()),
                   juce::Justification::centred, false);

        g.setColour(dim);
        g.drawText(volts[index], juce::Rectangle<float>(r.getX() + third, r.getY(), third, r.getHeight()),
                   juce::Justification::centred, false);

        g.setColour(index > 0 ? lit : dim); // "(-)" lit when a lower voltage is available
        g.drawText("(-)", juce::Rectangle<float>(r.getX() + 2.0f * third, r.getY(), third, r.getHeight()),
                   juce::Justification::centred, false);
    }

    void mouseDown(const juce::MouseEvent& e) override
    {
        const int w = getWidth();
        if (e.x < w / 3 && index < 2)            { setIndex(index + 1); if (onChange) onChange(index); }
        else if (e.x >= 2 * w / 3 && index > 0)  { setIndex(index - 1); if (onChange) onChange(index); }
    }

private:
    int   index { 0 };
    float fontPx { 8.0f };
};
