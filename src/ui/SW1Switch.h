#pragma once
#include <juce_gui_basics/juce_gui_basics.h>
#include "TommyLookAndFeel.h"

// 3-position toggle switch for the SW1 clipping mode.
// Positions: 0 = Asym (top, single diode), 1 = Open (middle, one pair), 2 = Sym (bottom, all diodes).
// The body is a narrow (20px) toggle bar; labels sit 4px to its right.
// The body+labels block is centred within the component.
// Both mouseDown and mouseDrag update position so the lever can be dragged.
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

        // All dimensions proportional to component height (base = 65px at 1x scale)
        const float sc     = b.getHeight() / 65.0f;
        const float kBodyW = 20.0f * sc;
        const float kGap   =  4.0f * sc;
        const float kLabelW = 30.0f * sc;

        // Body centred in component; labels extend to the right
        const float bodyH  = 60.0f * sc;
        const float bodyX  = (b.getWidth() - kBodyW) * 0.5f;
        const float bodyY  = (b.getHeight() - bodyH) * 0.5f;
        const float labelX = bodyX + kBodyW + kGap;

        // Switch body
        g.setColour(juce::Colour(0xFF0A1422u));
        g.fillRoundedRectangle(bodyX, bodyY, kBodyW, bodyH, 4.0f * sc);
        g.setColour(juce::Colour(0xFF1C3050u));
        g.drawRoundedRectangle(bodyX + 0.5f, bodyY + 0.5f, kBodyW - 1.0f, bodyH - 1.0f, 4.0f * sc, 1.0f);

        // Centre groove
        const float grooveX = bodyX + kBodyW * 0.5f;
        g.setColour(juce::Colour(0xFF060F1Au));
        g.fillRect(grooveX - 1.5f * sc, bodyY + 5.0f * sc, 3.0f * sc, bodyH - 10.0f * sc);
        g.setColour(juce::Colour(0xFF243550u));
        g.drawLine(grooveX - 0.5f, bodyY + 5.0f * sc, grooveX - 0.5f, bodyY + bodyH - 5.0f * sc, 1.0f);

        // Lever
        const float section = bodyH / 3.0f;
        const float leverH  = 14.0f * sc;
        const float leverW  = kBodyW - 4.0f * sc;
        const float leverX  = bodyX + 2.0f * sc;
        const float leverY  = bodyY + (float)position * section + (section - leverH) * 0.5f;

        g.setColour(juce::Colours::black.withAlpha(0.35f));
        g.fillRoundedRectangle(leverX + sc, leverY + 2.0f * sc, leverW, leverH, 3.0f * sc);

        juce::ColourGradient leverGrad(juce::Colour(0xFFB8C4D0u), leverX, leverY,
                                        juce::Colour(0xFF6E7C8Au), leverX, leverY + leverH, false);
        leverGrad.addColour(0.45, juce::Colour(0xFF9AAAB8u));
        g.setGradientFill(leverGrad);
        g.fillRoundedRectangle(leverX, leverY, leverW, leverH, 3.0f * sc);
        g.setColour(juce::Colour(0xFF4A5A70u));
        g.drawRoundedRectangle(leverX + 0.5f, leverY + 0.5f, leverW - 1.0f, leverH - 1.0f, 3.0f * sc, 1.0f);

        // Labels to the right of the body
        static const char* const labels[] = { "Asym", "Open", "Sym" };
        g.setFont(juce::Font(juce::FontOptions(7.0f * sc)));

        for (int n = 0; n < 3; ++n)
        {
            const float cy    = bodyY + (float)n * section + section * 0.5f;
            const bool active = (n == position);
            g.setColour(active ? juce::Colour(TommyLookAndFeel::cSWLabelActive)
                               : juce::Colour(TommyLookAndFeel::cSWLabelInactive));
            g.drawText(labels[n],
                       juce::Rectangle<float>(labelX, cy - 6.0f * sc, kLabelW, 12.0f * sc),
                       juce::Justification::centredLeft, false);
        }
    }

    void mouseDown(const juce::MouseEvent& e) override  { updateFromMouse(e.position.y); }
    void mouseDrag(const juce::MouseEvent& e) override  { updateFromMouse(e.position.y); }

private:
    int position { 0 };

    void updateFromMouse(float mouseY)
    {
        const auto b  = getLocalBounds().toFloat();
        const float sc    = b.getHeight() / 65.0f;
        const float bodyH = 60.0f * sc;
        const float bodyY = (b.getHeight() - bodyH) * 0.5f;
        const float relY  = mouseY - bodyY;

        if (relY >= 0.0f && relY < bodyH)
        {
            const int newPos = juce::jlimit(0, 2, (int)(relY / (bodyH / 3.0f)));
            if (newPos != position)
            {
                position = newPos;
                repaint();
                if (onChange) onChange(position);
            }
        }
    }
};
