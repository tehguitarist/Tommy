#pragma once
#include <juce_gui_basics/juce_gui_basics.h>
#include "TommyLookAndFeel.h"

// 3-position toggle switch for the SW1 clipping mode.
// Positions: 0 = Asym (top, single diode), 1 = Open (middle, one pair), 2 = Sym (bottom, all diodes).
// Rendered as a photographed toggle switch (lever angle bakes in the position), horizontally
// centred in the component (so it sits on the pedal's centre line). "A" sits above the switch,
// "S" below, "O" beside it. Both mouseDown and mouseDrag update position so it can be dragged like
// a real toggle.
class SW1Switch : public juce::Component
{
public:
    std::function<void(int)> onChange;

    void setPosition(int pos)
    {
        pos = juce::jlimit(0, 2, pos);
        if (pos != position) { position = pos; repaint(); }
    }

    int getPosition() const { return position; }

    void paint(juce::Graphics& g) override
    {
        const auto b = getLocalBounds().toFloat();
        const auto layout = computeLayout(b);

        TommyLookAndFeel::drawImageCentredAspect(g, TommyLookAndFeel::getSwitchImage(position),
            juce::Rectangle<float>(layout.bodyX, layout.bodyY, layout.imgSz, layout.imgSz));

        g.setFont(juce::Font(juce::FontOptions(juce::jmax(6.0f, layout.imgSz * 0.22f), juce::Font::bold)));
        auto labelColour = [this](int n) {
            return juce::Colour(n == position ? TommyLookAndFeel::cSWLabelActive
                                              : TommyLookAndFeel::cSWLabelInactive);
        };

        // "A" above, "S" below — both centred on the image's horizontal centre. "S" sits in a
        // tighter band than "A" so it reads as closer to the switch.
        g.setColour(labelColour(0));
        g.drawText("A", juce::Rectangle<float>(layout.bodyX, 0.0f, layout.imgSz, layout.bodyY),
                   juce::Justification::centred, false);
        g.setColour(labelColour(2));
        g.drawText("S", juce::Rectangle<float>(layout.bodyX, layout.bodyY + layout.imgSz,
                                                layout.imgSz, b.getHeight() - (layout.bodyY + layout.imgSz)),
                   juce::Justification::centred, false);

        // "O" beside the image, vertically centred.
        g.setColour(labelColour(1));
        g.drawText("O", juce::Rectangle<float>(layout.bodyX + layout.imgSz + layout.gap,
                                                layout.bodyY, layout.labelW, layout.imgSz),
                   juce::Justification::centred, false);
    }

    void mouseDown(const juce::MouseEvent& e) override  { updateFromMouse(e.position.y); }
    void mouseDrag(const juce::MouseEvent& e) override  { updateFromMouse(e.position.y); }

private:
    int position { 0 };

    struct Layout { float imgSz, bodyX, bodyY, gap, labelW; };

    // Image is horizontally centred in whatever bounds the editor gives this component (which is
    // itself centred on the pedal's centre line) — vertical space is split so "A"/"S" fit above/
    // below it, and "O" fits in the leftover width to its right. The bottom margin (for "S") is
    // deliberately tighter than the top one (for "A") so "S" reads as closer to the switch.
    static Layout computeLayout(juce::Rectangle<float> b)
    {
        const float labelH    = juce::jmax(9.0f, b.getHeight() * 0.14f);
        const float gap       = juce::jmax(1.0f, b.getHeight() * 0.012f);
        const float topMargin = labelH + gap;
        const float botMargin = labelH * 0.05f;
        const float imgSz     = juce::jmin(b.getWidth() * 0.62f, b.getHeight() - topMargin - botMargin);
        const float bodyX     = (b.getWidth() - imgSz) * 0.5f;
        const float bodyY     = topMargin;
        const float labelW    = juce::jmax(0.0f, b.getWidth() - (bodyX + imgSz + gap));
        return { imgSz, bodyX, bodyY, gap, labelW };
    }

    void updateFromMouse(float mouseY)
    {
        const auto layout = computeLayout(getLocalBounds().toFloat());
        const float relY  = mouseY - layout.bodyY;

        if (relY >= 0.0f && relY < layout.imgSz)
        {
            const int newPos = juce::jlimit(0, 2, (int)(relY / (layout.imgSz / 3.0f)));
            if (newPos != position)
            {
                position = newPos;
                repaint();
                if (onChange) onChange(position);
            }
        }
    }
};
