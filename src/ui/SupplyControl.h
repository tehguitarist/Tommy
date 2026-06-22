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
        const auto font = juce::Font(juce::FontOptions(fontPx, juce::Font::bold));
        g.setFont(font);

        const auto layout = computeLayout(font);
        const auto lit    = juce::Colour(TommyLookAndFeel::cPowerLabelLit);
        const auto dim    = juce::Colour(TommyLookAndFeel::cPowerLabel);

        g.setColour(index < 2 ? lit : dim); // "(+)" lit when a higher voltage is available
        g.drawText("(+)", layout.plusBounds, juce::Justification::centred, false);

        g.setColour(dim);
        g.drawText(layout.voltsText, layout.voltsBounds, juce::Justification::centred, false);

        g.setColour(index > 0 ? lit : dim); // "(-)" lit when a lower voltage is available
        g.drawText("(-)", layout.minusBounds, juce::Justification::centred, false);
    }

    void mouseDown(const juce::MouseEvent& e) override
    {
        const auto font   = juce::Font(juce::FontOptions(fontPx, juce::Font::bold));
        const auto layout = computeLayout(font);
        const float padClick = fontPx * 0.6f; // generous invisible click margin either side

        if ((float) e.x < layout.plusBounds.getRight() + padClick && index < 2)
            { setIndex(index + 1); if (onChange) onChange(index); }
        else if ((float) e.x >= layout.minusBounds.getX() - padClick && index > 0)
            { setIndex(index - 1); if (onChange) onChange(index); }
    }

private:
    int   index { 0 };
    float fontPx { 10.0f };

    struct Layout
    {
        const char* voltsText;
        juce::Rectangle<float> plusBounds, voltsBounds, minusBounds; // tight (text-width) rects
    };

    // "(+)", the voltage, and "(-)" packed tightly together and centred in the component — rather
    // than spread across three equal thirds, which left large gaps either side of the short text.
    Layout computeLayout(const juce::Font& font) const
    {
        static const char* const volts[] = { "9V", "12V", "18V" };
        const char* voltsText = volts[index];

        const float wPlus  = juce::GlyphArrangement::getStringWidth(font, "(+)");
        const float wVolts = juce::GlyphArrangement::getStringWidth(font, voltsText);
        const float wMinus = juce::GlyphArrangement::getStringWidth(font, "(-)");
        const float gap    = fontPx * 0.35f;

        const float total = wPlus + gap + wVolts + gap + wMinus;
        const auto r = getLocalBounds().toFloat();
        const float h = r.getHeight();
        float x = r.getCentreX() - total * 0.5f;

        juce::Rectangle<float> plusB(x, 0.0f, wPlus, h);
        x += wPlus + gap;
        juce::Rectangle<float> voltsB(x, 0.0f, wVolts, h);
        x += wVolts + gap;
        juce::Rectangle<float> minusB(x, 0.0f, wMinus, h);

        return { voltsText, plusB, voltsB, minusB };
    }
};
