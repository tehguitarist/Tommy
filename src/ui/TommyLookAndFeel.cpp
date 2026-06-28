#include "TommyLookAndFeel.h"
#include <BinaryData.h>

// ── Image loading ─────────────────────────────────────────────────────────────
// All images are PNG with alpha, pre-rotated to "noon" (knobs/switch-up) where relevant.
// Loaded once (function-local statics) and cached for the process lifetime.

namespace
{
    juce::Image loadImg(const void* data, int size)
    {
        return juce::ImageCache::getFromMemory(data, size);
    }

    // Draws `img` centred at (cx, cy), scaled so its larger dimension equals `diameter`, rotated by
    // `angleRadians` about its centre. Source art is pre-rendered pointing at noon (angle = 0).
    void drawRotatedImage(juce::Graphics& g, const juce::Image& img, float cx, float cy,
                           float diameter, float angleRadians)
    {
        if (img.isNull()) return;

        const float srcW = (float) img.getWidth(), srcH = (float) img.getHeight();
        const float scale = diameter / juce::jmax(srcW, srcH);

        const auto transform = juce::AffineTransform::translation(-srcW * 0.5f, -srcH * 0.5f)
                                    .scaled(scale)
                                    .rotated(angleRadians)
                                    .translated(cx, cy);
        g.drawImageTransformed(img, transform, false);
    }
}

const juce::Image& TommyLookAndFeel::getKnobImage()
{
    static const juce::Image img = loadImg(BinaryData::T_Knob_png, BinaryData::T_Knob_pngSize);
    return img;
}

const juce::Image& TommyLookAndFeel::getTrimKnobImage()
{
    static const juce::Image img = loadImg(BinaryData::vol_trim_png, BinaryData::vol_trim_pngSize);
    return img;
}

const juce::Image& TommyLookAndFeel::getLedOnImage()
{
    static const juce::Image img = loadImg(BinaryData::blue_led_on_png, BinaryData::blue_led_on_pngSize);
    return img;
}

const juce::Image& TommyLookAndFeel::getLedOffImage()
{
    static const juce::Image img = loadImg(BinaryData::blue_led_off_png, BinaryData::blue_led_off_pngSize);
    return img;
}

const juce::Image& TommyLookAndFeel::getFootswitchUpImage()
{
    static const juce::Image img = loadImg(BinaryData::footswitch_up_png, BinaryData::footswitch_up_pngSize);
    return img;
}

const juce::Image& TommyLookAndFeel::getFootswitchDownImage()
{
    static const juce::Image img = loadImg(BinaryData::footswitch_down_png, BinaryData::footswitch_down_pngSize);
    return img;
}

const juce::Image& TommyLookAndFeel::getSwitchImage(int position)
{
    static const juce::Image up   = loadImg(BinaryData::switch_up_png,   BinaryData::switch_up_pngSize);
    static const juce::Image mid  = loadImg(BinaryData::switch_mid_png,  BinaryData::switch_mid_pngSize);
    static const juce::Image down = loadImg(BinaryData::switch_down_png, BinaryData::switch_down_pngSize);
    if (position <= 0) return up;
    if (position == 1) return mid;
    return down;
}

void TommyLookAndFeel::drawImageCentredAspect(juce::Graphics& g, const juce::Image& image,
                                               juce::Rectangle<float> bounds)
{
    if (image.isNull()) return;

    const float srcW = (float) image.getWidth(), srcH = (float) image.getHeight();
    const float scale = juce::jmin(bounds.getWidth() / srcW, bounds.getHeight() / srcH);
    const float drawW = srcW * scale, drawH = srcH * scale;

    g.drawImage(image, juce::Rectangle<float>(bounds.getCentreX() - drawW * 0.5f,
                                               bounds.getCentreY() - drawH * 0.5f, drawW, drawH));
}

TommyLookAndFeel::TommyLookAndFeel()
{
    setColour(juce::Label::textColourId, juce::Colour(cLabelText));
    setColour(juce::TextButton::textColourOffId, juce::Colour(cOSLabel));
    setColour(juce::TextButton::textColourOnId,  juce::Colour(cOSBtnActive));

    // ComboBox colours
    setColour(juce::ComboBox::backgroundColourId, juce::Colour(cOSBtnActiveBg));
    setColour(juce::ComboBox::outlineColourId,    juce::Colour(cOSBtnActiveBdr));
    setColour(juce::ComboBox::textColourId,       juce::Colour(cOSBtnActive));
    setColour(juce::ComboBox::arrowColourId,      juce::Colour(cOSLabel));
    setColour(juce::PopupMenu::backgroundColourId,   juce::Colour(0xFF0A1628u));
    setColour(juce::PopupMenu::textColourId,         juce::Colour(cOSBtnActive));
    setColour(juce::PopupMenu::highlightedBackgroundColourId, juce::Colour(cOSBtnActiveBg));
    setColour(juce::PopupMenu::highlightedTextColourId,       juce::Colour(cKnobHighlight));
}

// ── Pedal background ──────────────────────────────────────────────────────────

void TommyLookAndFeel::paintPedalBackground(juce::Graphics& g, juce::Rectangle<int> bounds)
{
    auto fb = bounds.toFloat();
    const float W = fb.getWidth(), H = fb.getHeight();

    // Rounded base fill (shows at the rounded corners if the texture doesn't quite reach them)
    g.setColour(juce::Colour(cPedalFace));
    g.fillRoundedRectangle(fb, 16.0f);

    // Clip subsequent drawing to inside the rounded rect
    g.saveState();
    juce::Path clip;
    clip.addRoundedRectangle(fb.reduced(2.0f), 14.0f);
    g.reduceClipRegion(clip);

    // Texture — "cover" fit: scale to fill both dimensions (no stretch), crop the overflow.
    {
        static const juce::Image texture = loadImg(BinaryData::tommy_texture_png, BinaryData::tommy_texture_pngSize);
        if (! texture.isNull())
        {
            const float srcW = (float) texture.getWidth(), srcH = (float) texture.getHeight();
            const float scale = juce::jmax(W / srcW, H / srcH);
            const float drawW = srcW * scale, drawH = srcH * scale;
            g.drawImage(texture, juce::Rectangle<float>(fb.getCentreX() - drawW * 0.5f,
                                                          fb.getCentreY() - drawH * 0.5f, drawW, drawH));
        }
    }

    g.restoreState();

    // Border (drawn over clip)
    g.setColour(juce::Colour(cPedalBorder));
    g.drawRoundedRectangle(fb.reduced(1.0f), 16.0f, 2.0f);
}

// ── Rotary slider ─────────────────────────────────────────────────────────────

void TommyLookAndFeel::drawRotarySlider(juce::Graphics& g, int x, int y, int w, int h,
                                         float sliderPos, float startAngle, float endAngle,
                                         juce::Slider& slider)
{
    const bool isTrim = (slider.getComponentID() == "trim");
    const auto bounds = juce::Rectangle<float>((float) x, (float) y, (float) w, (float) h);
    const auto cx = bounds.getCentreX(), cy = bounds.getCentreY();
    const float valAngle = startAngle + sliderPos * (endAngle - startAngle);

    if (isTrim)
    {
        // Halo-style trim knob: outer arc track + value arc + small knob cap
        const float outer = juce::jmin(bounds.getWidth(), bounds.getHeight()) * 0.5f - 3.0f;
        const float arcW  = 5.0f;
        const float knobR = outer * 0.60f;

        // Track arc
        {
            juce::Path arc;
            arc.addCentredArc(cx, cy, outer, outer, 0.0f, startAngle, endAngle, true);
            g.setColour(juce::Colour(cTrimArcTrack));
            g.strokePath(arc, juce::PathStrokeType(arcW, juce::PathStrokeType::curved,
                                                    juce::PathStrokeType::rounded));
        }
        // Value arc
        {
            juce::Path arc;
            arc.addCentredArc(cx, cy, outer, outer, 0.0f, startAngle, valAngle, true);
            g.setColour(juce::Colour(cTrimArc));
            g.strokePath(arc, juce::PathStrokeType(arcW, juce::PathStrokeType::curved,
                                                    juce::PathStrokeType::rounded));
        }
        // Knob cap — rotated image only (pre-rendered art, noon = angle 0).
        drawRotatedImage(g, getTrimKnobImage(), cx, cy, knobR * 2.0f, valAngle);
    }
    else
    {
        // Standard pedal knob — rotated image only.
        const float knobR = juce::jmin(bounds.getWidth(), bounds.getHeight()) * 0.5f - 2.0f;
        drawRotatedImage(g, getKnobImage(), cx, cy, knobR * 2.0f, valAngle);
    }
}

// ── Buttons ───────────────────────────────────────────────────────────────────

void TommyLookAndFeel::drawButtonBackground(juce::Graphics& g, juce::Button& button,
                                              const juce::Colour&,
                                              bool /*highlighted*/, bool down)
{
    auto b = button.getLocalBounds().toFloat();

    if (button.getComponentID() == "bypass")
    {
        // Footswitch image swap — position is a press ANIMATION only (mouse-down state), it does
        // NOT indicate bypass on/off (that's the separate LED).
        const auto& img = down ? TommyLookAndFeel::getFootswitchDownImage()
                               : TommyLookAndFeel::getFootswitchUpImage();
        TommyLookAndFeel::drawImageCentredAspect(g, img, b);
    }
    else if (button.getComponentID() == "os")
    {
        // Styled to match the OS ComboBoxes (same brightness/colours), not a toggle state.
        const float corner = 4.0f;

        g.setColour(juce::Colour(cOSBtnActiveBg));
        g.fillRoundedRectangle(b, corner);
        g.setColour(juce::Colour(cOSBtnActiveBdr));
        g.drawRoundedRectangle(b.reduced(0.5f), corner, 1.0f);
    }
}

void TommyLookAndFeel::drawButtonText(juce::Graphics& g, juce::TextButton& button,
                                       bool, bool down)
{
    const bool isOSButton = button.getComponentID() == "os";
    const bool active = isOSButton || button.getToggleState();
    const juce::Colour col = active ? juce::Colour(cOSBtnActive) : juce::Colour(cOSLabel);
    g.setColour(col);
    const float fontPx = isOSButton ? juce::jmax(7.0f, (float) button.getHeight() * 0.38f) : 8.0f;
    g.setFont(juce::Font(juce::FontOptions(fontPx, juce::Font::bold)));

    auto area = button.getLocalBounds();
    if (down) area = area.translated(0, 1);
    g.drawText(button.getButtonText(), area, juce::Justification::centred, false);
}

// ── Labels ────────────────────────────────────────────────────────────────────

void TommyLookAndFeel::drawLabel(juce::Graphics& g, juce::Label& label)
{
    // Transparent background, text only — pedal background shows through.
    if (! label.isBeingEdited())
    {
        g.setColour(label.findColour(juce::Label::textColourId));
        g.setFont(label.getFont());
        g.drawText(label.getText(), label.getLocalBounds(),
                   label.getJustificationType(), true);
    }
}

// ── ComboBox ──────────────────────────────────────────────────────────────────

void TommyLookAndFeel::drawComboBox(juce::Graphics& g, int width, int height,
                                     bool isButtonDown,
                                     int /*buttonX*/, int /*buttonY*/,
                                     int /*buttonW*/, int /*buttonH*/,
                                     juce::ComboBox& /*box*/)
{
    const float corner = 4.0f;
    const auto bounds  = juce::Rectangle<float>(0.0f, 0.0f, (float)width, (float)height);

    // Background
    g.setColour(isButtonDown ? juce::Colour(cOSBtnActiveBdr).withAlpha(0.4f)
                             : juce::Colour(cOSBtnActiveBg));
    g.fillRoundedRectangle(bounds, corner);

    // Border
    g.setColour(juce::Colour(cOSBtnActiveBdr));
    g.drawRoundedRectangle(bounds.reduced(0.5f), corner, 1.0f);

    // Arrow — small downward chevron at right
    const float arrowW  = 5.0f;
    const float arrowH  = 3.0f;
    const float arrowCX = bounds.getRight() - 8.0f;
    const float arrowCY = bounds.getCentreY();
    juce::Path arrow;
    arrow.startNewSubPath(arrowCX - arrowW * 0.5f, arrowCY - arrowH * 0.5f);
    arrow.lineTo(arrowCX,                           arrowCY + arrowH * 0.5f);
    arrow.lineTo(arrowCX + arrowW * 0.5f,           arrowCY - arrowH * 0.5f);
    g.setColour(juce::Colour(cOSLabel));
    g.strokePath(arrow, juce::PathStrokeType(1.2f, juce::PathStrokeType::curved,
                                              juce::PathStrokeType::rounded));
}

juce::Font TommyLookAndFeel::getComboBoxFont(juce::ComboBox& box)
{
    return juce::Font(juce::FontOptions(juce::jmax(7.0f, (float)box.getHeight() * 0.38f),
                                        juce::Font::bold));
}

void TommyLookAndFeel::positionComboBoxText(juce::ComboBox& box, juce::Label& label)
{
    // Full-width label so centred justification (set on the ComboBox instance)
    // truly centres the text. The arrow is drawn over the far right by drawComboBox.
    label.setBounds(0, 0, box.getWidth(), box.getHeight());
    label.setFont(getComboBoxFont(box));
}
