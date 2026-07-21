#include "PluginEditor.h"

// ── Helpers ───────────────────────────────────────────────────────────────────

void TommyAudioProcessorEditor::configureKnob(juce::Slider& s)
{
    s.setSliderStyle(juce::Slider::RotaryVerticalDrag);
    s.setTextBoxStyle(juce::Slider::NoTextBox, false, 0, 0);
    s.setLookAndFeel(&laf);
    addAndMakeVisible(s);
}

void TommyAudioProcessorEditor::configureTrimKnob(juce::Slider& s)
{
    configureKnob(s);
    s.setComponentID("trim");
}

void TommyAudioProcessorEditor::configureLabel(juce::Label& l, float fontSize,
                                                juce::uint32 colour,
                                                juce::Justification just)
{
    l.setFont(juce::Font(juce::FontOptions(fontSize, juce::Font::bold)));
    l.setColour(juce::Label::textColourId, juce::Colour(colour));
    l.setJustificationType(just);
    l.setInterceptsMouseClicks(false, false);
    addAndMakeVisible(l);
}

void TommyAudioProcessorEditor::configureTrimValueLabel(juce::Label& l)
{
    configureLabel(l, 8.5f, TommyLookAndFeel::cTrimLabel);

    // Unlike the other labels (decorative, click-through via configureLabel), these two are
    // interactive: double-click to type an exact dB value. Single-click is deliberately NOT an
    // edit trigger — the label sits under the trim knob and a stray click shouldn't open a caret.
    l.setInterceptsMouseClicks(true, false);
    l.setEditable(false, true, false); // (singleClick, doubleClick, lossOfFocusDiscardsChanges)
    l.setTooltip("Double-click to type an exact dB value.");
    l.setColour(juce::Label::backgroundWhenEditingColourId, juce::Colour(TommyLookAndFeel::cOSBtnActiveBg));
    l.setColour(juce::Label::textWhenEditingColourId,       juce::Colour(TommyLookAndFeel::cOSBtnActive));
    l.setColour(juce::Label::outlineWhenEditingColourId,    juce::Colour(TommyLookAndFeel::cOSBtnActiveBdr));
}

// Is `s` a bare decimal number (optional sign, digits, at most a decimal point)? Deliberately
// stricter than String::getFloatValue, which silently yields 0.0 for junk like "abc" — typing
// nonsense should leave the trim where it was, not slam it to 0 dB.
static bool isPlainNumber(const juce::String& s)
{
    if (s.isEmpty())
        return false;

    int i = (s[0] == '+' || s[0] == '-') ? 1 : 0;
    bool sawDigit = false, sawPoint = false;

    for (; i < s.length(); ++i)
    {
        const auto c = s[i];
        if (juce::CharacterFunctions::isDigit(c)) { sawDigit = true; continue; }
        if (c == '.' && ! sawPoint)              { sawPoint = true; continue; }
        return false;
    }
    return sawDigit;
}

void TommyAudioProcessorEditor::commitTrimText(juce::Label& label, const juce::String& paramID,
                                                juce::Slider& knob)
{
    // Accept what the label itself displays ("-3.5 dB") as well as a bare number, so the user can
    // edit in place without deleting the unit.
    auto text = label.getText().trim();
    if (text.endsWithIgnoreCase("dB"))
        text = text.dropLastCharacters(2).trim();

    if (isPlainNumber(text))
    {
        const auto v = (float) juce::jlimit(-kTrimRange, kTrimRange, (double) text.getFloatValue());

        // Route through the PARAMETER, not knob.setValue: that drives the attachment -> slider ->
        // onValueChange -> mirrorTrim chain, so a typed value respects the trim lock exactly like a
        // dragged one, and the host sees a proper gesture.
        if (auto* param = audioProcessor.apvts.getParameter(paramID))
        {
            param->beginChangeGesture();
            param->setValueNotifyingHost(param->convertTo0to1(v));
            param->endChangeGesture();
        }
    }

    // Re-render the canonical "<v> dB" text — this both restores the old value after rejected input
    // and reformats accepted input that was typed bare or out of range. Safe to invoke directly:
    // the knob is already at its final value, so mirrorTrim sees a zero delta and no-ops.
    knob.onValueChange();
}

void TommyAudioProcessorEditor::mirrorTrim(bool sourceIsInput)
{
    const juce::Slider& src = sourceIsInput ? inputTrimKnob  : outputTrimKnob;
    double&         srcLast = sourceIsInput ? lastInputTrim  : lastOutputTrim;
    const double    dstLast = sourceIsInput ? lastOutputTrim : lastInputTrim;

    // Cache the new source value FIRST and unconditionally — the delta must be measured against the
    // previous position even when the lock is off, otherwise the first move after switching it on
    // would be computed from a stale reference and jump the other knob.
    const double delta = src.getValue() - srcLast;
    srcLast = src.getValue();

    // trimLinkBusy: this call is the echo of our own write to the other parameter — its slider's
    // onValueChange has just refreshed that side's cache above, which is all this pass needs to do.
    if (trimLinkBusy || ! trimLockButton.getToggleState() || delta == 0.0)
        return;

    // Equal and opposite CHANGE, relative to where the other knob already sits — so the pair's
    // existing offset is preserved and the starting values don't matter. Clamped at the rails
    // (past which the offset necessarily shifts; nothing sensible to do but stop).
    const auto target = (float) juce::jlimit(-kTrimRange, kTrimRange, dstLast - delta);

    if (auto* param = audioProcessor.apvts.getParameter(sourceIsInput ? "output_trim" : "input_trim"))
    {
        const juce::ScopedValueSetter<bool> guard(trimLinkBusy, true);
        param->beginChangeGesture();
        param->setValueNotifyingHost(param->convertTo0to1(target));
        param->endChangeGesture();
    }
}

// ── Constructor ───────────────────────────────────────────────────────────────

TommyAudioProcessorEditor::TommyAudioProcessorEditor(TommyAudioProcessor& p)
    : AudioProcessorEditor(&p),
      audioProcessor(p),
      // APVTS slider attachments (pedal knobs)
      bassAttach    (*p.apvts.getParameter("bass"),         bassKnob,        nullptr),
      gainAttach    (*p.apvts.getParameter("drive"),        gainKnob,        nullptr),
      volumeAttach  (*p.apvts.getParameter("volume"),       volumeKnob,      nullptr),
      trebleAttach  (*p.apvts.getParameter("treble"),       trebleKnob,      nullptr),
      // Trim knobs
      inTrimAttach  (*p.apvts.getParameter("input_trim"),   inputTrimKnob,   nullptr),
      outTrimAttach (*p.apvts.getParameter("output_trim"),  outputTrimKnob,  nullptr),
      // Bypass button
      bypassAttach  (*p.apvts.getParameter("bypass"),       bypassButton,    nullptr),
      // Clipping mode — ParameterAttachment drives SW1Switch position
      clipAttach (*p.apvts.getParameter("clipping_mode"),
                  [this](float v) { sw1Switch.setPosition(juce::roundToInt(v)); },
                  nullptr),
      // Supply voltage — ParameterAttachment drives the SupplyControl display
      supplyAttach (*p.apvts.getParameter("supply_voltage"),
                    [this](float v) { supplyControl.setIndex(juce::roundToInt(v)); },
                    nullptr)
{
    setLookAndFeel(&laf);

    // Seed the trim-lock deltas from the values the attachments (constructed above) have already
    // pushed into the knobs, so a session restored with non-zero trims doesn't read as a jump the
    // first time either knob moves.
    lastInputTrim  = inputTrimKnob.getValue();
    lastOutputTrim = outputTrimKnob.getValue();

    // ── Side panel: Input ────────────────────────────────────────────────────
    configureLabel(inputPanelLabel, 8.0f, TommyLookAndFeel::cTrimLabel);
    inputPanelLabel.setFont(
        juce::Font(juce::FontOptions(8.0f, juce::Font::bold)).withExtraKerningFactor(0.2f));

    configureTrimKnob(inputTrimKnob);
    inputTrimKnob.setRange(-kTrimRange, kTrimRange);

    configureLabel(inputTrimLabel, 7.5f, TommyLookAndFeel::cTrimLabel - 0x001A0000u);

    configureTrimValueLabel(inputTrimValueLabel);
    inputTrimKnob.onValueChange = [this]
    {
        inputTrimValueLabel.setText(juce::String(inputTrimKnob.getValue(), 1) + " dB",
                                     juce::dontSendNotification);
        mirrorTrim(true);
    };
    inputTrimKnob.onValueChange();
    inputTrimValueLabel.onTextChange = [this]
    {
        commitTrimText(inputTrimValueLabel, "input_trim", inputTrimKnob);
    };

    addAndMakeVisible(inputVU);

    // ── Side panel: Output ───────────────────────────────────────────────────
    configureLabel(outputPanelLabel, 8.0f, TommyLookAndFeel::cTrimLabel);
    outputPanelLabel.setFont(
        juce::Font(juce::FontOptions(8.0f, juce::Font::bold)).withExtraKerningFactor(0.2f));

    configureTrimKnob(outputTrimKnob);
    outputTrimKnob.setRange(-kTrimRange, kTrimRange);

    configureLabel(outputTrimLabel, 7.5f, TommyLookAndFeel::cTrimLabel - 0x001A0000u);

    configureTrimValueLabel(outputTrimValueLabel);
    outputTrimKnob.onValueChange = [this]
    {
        outputTrimValueLabel.setText(juce::String(outputTrimKnob.getValue(), 1) + " dB",
                                      juce::dontSendNotification);
        mirrorTrim(false);
    };
    outputTrimKnob.onValueChange();
    outputTrimValueLabel.onTextChange = [this]
    {
        commitTrimText(outputTrimValueLabel, "output_trim", outputTrimKnob);
    };

    addAndMakeVisible(outputVU);

    // ── Pedal face: supply-voltage selector (interactive "(+) 9V (-)") ───────
    supplyControl.onChange = [this](int idx)
    {
        auto* param = audioProcessor.apvts.getParameter("supply_voltage");
        param->beginChangeGesture();
        param->setValueNotifyingHost(param->convertTo0to1((float) idx));
        param->endChangeGesture();
    };
    addAndMakeVisible(supplyControl);
    supplyAttach.sendInitialUpdate();

    // ── SW1 switch — added BEFORE knobs so knobs render on top of its label overlap area ──
    sw1Switch.onChange = [this](int pos)
    {
        auto* param = audioProcessor.apvts.getParameter("clipping_mode");
        param->beginChangeGesture();
        param->setValueNotifyingHost(param->convertTo0to1((float) pos));
        param->endChangeGesture();
    };
    addAndMakeVisible(sw1Switch);
    clipAttach.sendInitialUpdate();

    // ── Pedal knobs (after sw1Switch so they render on top) ─────────────────
    for (auto* s : { &bassKnob, &gainKnob, &volumeKnob, &trebleKnob })
    {
        configureKnob(*s);
        // Small value popup while dragging, showing the raw 0.0-1.0 parameter value fixed to
        // two decimal places (explicit formatter, not just setNumDecimalPlacesToDisplay, so the
        // popup text is deterministic regardless of the slider's interval/range settings).
        s->textFromValueFunction = [](double v) { return juce::String(v, 2); };
        s->setPopupDisplayEnabled(true, false, this);
    }

    auto kFont = juce::Font(juce::FontOptions(8.5f, juce::Font::bold))
                     .withExtraKerningFactor(0.15f);

    for (auto* l : { &bassLabel, &gainLabel, &volumeLabel, &trebleLabel })
    {
        l->setFont(kFont);
        l->setColour(juce::Label::textColourId, juce::Colour(TommyLookAndFeel::cLabelText));
        l->setJustificationType(juce::Justification::centred);
        l->setInterceptsMouseClicks(false, false);
        addAndMakeVisible(*l);
    }

    // ── LED ──────────────────────────────────────────────────────────────────
    addAndMakeVisible(led);

    // ── Tommy logo — Brush Script MT italic (font set in refreshFonts) ──────
    tommyLogo.setColour(juce::Label::textColourId, juce::Colour(TommyLookAndFeel::cLabelText).withAlpha(0.9f));
    tommyLogo.setJustificationType(juce::Justification::centred);
    tommyLogo.setInterceptsMouseClicks(false, false);
    addAndMakeVisible(tommyLogo);

    // ── Bypass button ────────────────────────────────────────────────────────
    bypassButton.setComponentID("bypass");
    bypassButton.setClickingTogglesState(true);
    bypassButton.setLookAndFeel(&laf);
    addAndMakeVisible(bypassButton);

    configureLabel(bypassLabel, 7.0f, TommyLookAndFeel::cBypassLabel);
    bypassLabel.setFont(
        juce::Font(juce::FontOptions(7.0f, juce::Font::bold)).withExtraKerningFactor(0.2f));

    // ── Oversampling strip ────────────────────────────────────────────────────
    configureLabel(osLabel, 8.0f, TommyLookAndFeel::cOSLabel);
    osLabel.setJustificationType(juce::Justification::centredLeft);

    static const juce::StringArray kOsChoices { "1x", "2x", "4x", "8x" };

    for (auto* lbl : { &osLiveLabel, &osBncLabel })
    {
        lbl->setFont(juce::Font(juce::FontOptions(7.0f, juce::Font::bold)).withExtraKerningFactor(0.15f));
        lbl->setColour(juce::Label::textColourId, juce::Colour(TommyLookAndFeel::cOSLabel));
        lbl->setJustificationType(juce::Justification::centredRight);
        lbl->setInterceptsMouseClicks(false, false);
        addAndMakeVisible(*lbl);
    }

    for (auto* box : { &osRealtimeBox, &osRenderBox })
    {
        box->addItemList(kOsChoices, 1); // items: IDs 1-4 → indices 0-3
        box->setJustificationType(juce::Justification::centred);
        box->setLookAndFeel(&laf);
        addAndMakeVisible(*box);
    }

    // Build ComboBox parameter attachments after items are populated
    osRealtimeAttach = std::make_unique<juce::ComboBoxParameterAttachment>(
        *p.apvts.getParameter("oversampling"), osRealtimeBox);
    osRenderAttach   = std::make_unique<juce::ComboBoxParameterAttachment>(
        *p.apvts.getParameter("render_oversampling"), osRenderBox);

    // ── SIZE label + scale button ─────────────────────────────────────────────
    sizeLabel.setFont(juce::Font(juce::FontOptions(7.0f, juce::Font::bold)).withExtraKerningFactor(0.15f));
    sizeLabel.setColour(juce::Label::textColourId, juce::Colour(TommyLookAndFeel::cOSLabel));
    sizeLabel.setJustificationType(juce::Justification::centredRight);
    sizeLabel.setInterceptsMouseClicks(false, false);
    addAndMakeVisible(sizeLabel);

    scaleBtn.setComponentID("os");
    scaleBtn.setClickingTogglesState(false);
    scaleBtn.setLookAndFeel(&laf);
    scaleBtn.onClick = [this] { showScaleMenu(); };
    addAndMakeVisible(scaleBtn);

    // ── Version stamp (fills the leftover middle gap in the OS strip) ─────────
    versionLabel.setText("v" JucePlugin_VersionString, juce::dontSendNotification);
    versionLabel.setFont(juce::Font(juce::FontOptions(7.0f, juce::Font::plain)).withExtraKerningFactor(0.1f));
    versionLabel.setColour(juce::Label::textColourId, juce::Colour(TommyLookAndFeel::cOSLabel));
    versionLabel.setJustificationType(juce::Justification::centred);
    versionLabel.setInterceptsMouseClicks(false, false);
    addAndMakeVisible(versionLabel);

    // ── HQ toggle (accurate vs fast diode solve) ──────────────────────────────
    hqButton.setComponentID("ostoggle"); // lit when on, dim when off
    hqButton.setClickingTogglesState(true);
    hqButton.setLookAndFeel(&laf);
    hqButton.setTooltip("HQ: most accurate diode modelling. Turn off to save CPU.");
    addAndMakeVisible(hqButton);
    hqAttach = std::make_unique<juce::ButtonParameterAttachment>(*p.apvts.getParameter("hq"), hqButton);

    // ── Trim LOCK toggle (couples the input/output trim knobs) ────────────────
    trimLockButton.setComponentID("ostoggle"); // same lit/dim styling as HQ
    trimLockButton.setClickingTogglesState(true);
    trimLockButton.setLookAndFeel(&laf);
    trimLockButton.setTooltip("LOCK: ties the input and output trims together - raising one lowers "
                              "the other by the same amount.");
    addAndMakeVisible(trimLockButton);
    trimLockAttach = std::make_unique<juce::ButtonParameterAttachment>(*p.apvts.getParameter("trim_lock"),
                                                                      trimLockButton);

    // ── Load UI scale (per-session from APVTS state; falls back to user default) ──
    {
        juce::PropertiesFile::Options opts;
        opts.applicationName     = "TommyPedal";
        opts.filenameSuffix      = ".settings";
        opts.osxLibrarySubFolder = "Application Support";
        appProps.setStorageParameters(opts);

        float defScale = 1.0f;
        if (auto* pf = appProps.getUserSettings())
            defScale = (float) pf->getDoubleValue("defaultScale", 1.0);

        const float sessionScale = (float)(double)
            audioProcessor.apvts.state.getProperty("uiScale", (double) defScale);
        currentScale = juce::jlimit(0.5f, 2.5f, sessionScale);
    }

    // ── Resize constraints ────────────────────────────────────────────────────
    setResizable(true, true);
    if (auto* c = getConstrainer())
    {
        c->setFixedAspectRatio((double) kBaseW / (double) kBaseH);
        c->setSizeLimits(juce::roundToInt(kBaseW * 0.5f), juce::roundToInt(kBaseH * 0.5f),
                         juce::roundToInt(kBaseW * 2.5f), juce::roundToInt(kBaseH * 2.5f));
    }

    setSize(juce::roundToInt(kBaseW * currentScale), juce::roundToInt(kBaseH * currentScale));
    startTimerHz(33);
}

TommyAudioProcessorEditor::~TommyAudioProcessorEditor()
{
    stopTimer();
    setLookAndFeel(nullptr);
    for (auto* s : { &bassKnob, &gainKnob, &volumeKnob, &trebleKnob,
                     &inputTrimKnob, &outputTrimKnob })
        s->setLookAndFeel(nullptr);
    bypassButton.setLookAndFeel(nullptr);
    osRealtimeBox.setLookAndFeel(nullptr);
    osRenderBox.setLookAndFeel(nullptr);
    scaleBtn.setLookAndFeel(nullptr);
    hqButton.setLookAndFeel(nullptr);
    trimLockButton.setLookAndFeel(nullptr);
}

// ── Timer — update meters + LED ───────────────────────────────────────────────

void TommyAudioProcessorEditor::timerCallback()
{
    // VU levels — peak with ~300 ms release (exponential decay at 33 Hz)
    static float inLevel = 0.0f, outLevel = 0.0f;
    const float decayPerFrame = 0.90f;
    inLevel  = juce::jmax(audioProcessor.getInputLevel(0),  inLevel  * decayPerFrame);
    outLevel = juce::jmax(audioProcessor.getOutputLevel(0), outLevel * decayPerFrame);

    // Clamp sub-threshold values to zero so the VU reads clean silence when no audio plays.
    // At the unity volume setting output ≈ input, so the meter shows the source's idle noise
    // floor (guitar hum + interface noise), which the pedal's gain makes visible on the lowest
    // segment. ~-54 dBFS clears typical idle noise yet sits far below any real playing (even soft
    // notes peak well above this), so nothing audible is masked. Raised from -66 dBFS after the
    // output-makeup recalibration lifted the idle floor above the old threshold.
    static constexpr float kNoiseFl = 2e-3f;
    if (inLevel  < kNoiseFl) inLevel  = 0.0f;
    if (outLevel < kNoiseFl) outLevel = 0.0f;

    inputVU.setLevel(inLevel);
    outputVU.setLevel(outLevel);

    // LED: read from the APVTS parameter directly so it reflects button presses immediately,
    // even before processBlock has run (the `bypassed` atomic is only written there).
    const auto* pBypass = audioProcessor.apvts.getRawParameterValue("bypass");
    const bool isByp = (pBypass != nullptr && pBypass->load() > 0.5f);
    led.setOn(! isByp);
}

// ── Paint ─────────────────────────────────────────────────────────────────────

void TommyAudioProcessorEditor::paint(juce::Graphics& g)
{
    g.fillAll(juce::Colour(TommyLookAndFeel::cBackground));
    laf.paintPedalBackground(g, pedalBounds);

    // Separator line below power label (Y set in resized())
    const int margin = juce::roundToInt(14.0f * currentScale);
    g.setColour(juce::Colour(0xFF0D1C2Eu));
    g.fillRect(pedalBounds.getX() + margin, sepLineY, pedalBounds.getWidth() - 2 * margin, 1);

    // Oversampling panel background
    g.setColour(juce::Colour(TommyLookAndFeel::cOSBackground));
    g.fillRoundedRectangle(osPanelBounds.toFloat(), 6.0f);
    g.setColour(juce::Colour(TommyLookAndFeel::cOSBorder));
    g.drawRoundedRectangle(osPanelBounds.toFloat().reduced(0.5f), 6.0f, 1.0f);
}

// ── Layout ────────────────────────────────────────────────────────────────────

void TommyAudioProcessorEditor::resized()
{
    currentScale = (float)getWidth() / (float)kBaseW;
    const float sc = currentScale;
    const auto i = [sc](int v) { return juce::roundToInt((float)v * sc); };

    refreshFonts(sc);

    const int pad   = i(12);
    const int sideW = i(74);
    const int gap   = i(8);
    const int mainH = i(400);
    const int osH   = i(24);
    const int osGap = i(10);

    auto area = getLocalBounds().reduced(pad);
    auto mainRow = area.removeFromTop(mainH);
    area.removeFromTop(osGap);
    auto osRow = area.removeFromTop(osH);

    osPanelBounds = getLocalBounds().reduced(pad);
    osPanelBounds.removeFromTop(mainH + osGap);
    osPanelBounds = osPanelBounds.removeFromTop(osH);

    auto leftPanel  = mainRow.removeFromLeft(sideW);
    mainRow.removeFromLeft(gap);
    auto rightPanel = mainRow.removeFromRight(sideW);
    mainRow.removeFromRight(gap);
    pedalBounds = mainRow;

    // ── Left panel (Input) ────────────────────────────────────────────────
    {
        auto lp = leftPanel;
        inputPanelLabel.setBounds(lp.removeFromTop(i(14)));
        lp.removeFromTop(i(4));
        inputTrimKnob.setBounds(lp.removeFromTop(i(70)).withSizeKeepingCentre(i(70), i(70)));
        lp.removeFromTop(i(2));
        inputTrimLabel.setBounds(lp.removeFromTop(i(12)));
        lp.removeFromTop(i(2));
        inputTrimValueLabel.setBounds(lp.removeFromTop(i(12)));
        lp.removeFromTop(i(4));
        inputVU.setBounds(lp.withSizeKeepingCentre(i(24), lp.getHeight()));
    }

    // ── Right panel (Output) ──────────────────────────────────────────────
    {
        auto rp = rightPanel;
        outputPanelLabel.setBounds(rp.removeFromTop(i(14)));
        rp.removeFromTop(i(4));
        outputTrimKnob.setBounds(rp.removeFromTop(i(70)).withSizeKeepingCentre(i(70), i(70)));
        rp.removeFromTop(i(2));
        outputTrimLabel.setBounds(rp.removeFromTop(i(12)));
        rp.removeFromTop(i(2));
        outputTrimValueLabel.setBounds(rp.removeFromTop(i(12)));
        rp.removeFromTop(i(4));
        outputVU.setBounds(rp.withSizeKeepingCentre(i(24), rp.getHeight()));
    }

    // ── Pedal face ────────────────────────────────────────────────────────
    {
        auto pp = pedalBounds.reduced(i(10), i(10));

        supplyControl.setBounds(pp.removeFromTop(i(18)));
        sepLineY = supplyControl.getBottom() + i(5);
        pp.removeFromTop(i(6));

        // Row 1: Bass · SW1 · Gain (rows grown again to fit the now-66px knobs: 71px box, same 5px
        // margin as before; +17px label area unchanged)
        auto row1 = pp.removeFromTop(i(88));
        pp.removeFromTop(i(8));
        {
            const int secW = row1.getWidth() / 3;
            auto bassSection = row1.removeFromLeft(secW);
            auto gainSection = row1.removeFromRight(secW);
            auto sw1Section  = row1;

            bassKnob.setBounds(bassSection.removeFromTop(i(71)).withSizeKeepingCentre(i(66), i(66)));
            bassLabel.setBounds(bassSection.withSizeKeepingCentre(bassSection.getWidth(), i(12)));
            gainKnob.setBounds(gainSection.removeFromTop(i(71)).withSizeKeepingCentre(i(66), i(66)));
            gainLabel.setBounds(gainSection.withSizeKeepingCentre(gainSection.getWidth(), i(12)));
            // A bit taller (room for the "A"/"S" labels above/below the switch image) and nudged
            // down within row1.
            sw1Switch.setBounds(sw1Section.withSizeKeepingCentre(sw1Section.getWidth(), i(78))
                                           .translated(0, i(10)));
        }

        // Row 2: Volume · LED · Treble
        auto row2 = pp.removeFromTop(i(88));
        pp.removeFromTop(i(8));
        {
            const int secW = row2.getWidth() / 3;
            auto volSection  = row2.removeFromLeft(secW);
            auto trebSection = row2.removeFromRight(secW);
            auto ledSection  = row2;

            volumeKnob.setBounds(volSection.removeFromTop(i(71)).withSizeKeepingCentre(i(66), i(66)));
            volumeLabel.setBounds(volSection.withSizeKeepingCentre(volSection.getWidth(), i(12)));
            trebleKnob.setBounds(trebSection.removeFromTop(i(71)).withSizeKeepingCentre(i(66), i(66)));
            trebleLabel.setBounds(trebSection.withSizeKeepingCentre(trebSection.getWidth(), i(12)));
            // Oversized vs. the physical LED footprint — blue_led_on.png bakes its glow into the
            // art, so the component bounds need the extra room (image drawing is clipped to bounds).
            led.setBounds(ledSection.withSizeKeepingCentre(i(28), i(28)));
        }

        // Tommy logo + bypass (built bottom-up)
        pp.removeFromBottom(i(8));
        bypassLabel.setBounds(pp.removeFromBottom(i(13)));
        pp.removeFromBottom(i(5));
        bypassButton.setBounds(pp.removeFromBottom(i(52)).withSizeKeepingCentre(i(52), i(52)));
        pp.removeFromTop(i(4));
        tommyLogo.setBounds(pp.withSizeKeepingCentre(pp.getWidth(), juce::jmin(i(83), pp.getHeight())));
    }

    // ── Oversampling strip ────────────────────────────────────────────────
    {
        auto op = osRow.reduced(i(10), 0);

        // "OS" label on far left
        osLabel.setBounds(op.removeFromLeft(i(16)));
        op.removeFromLeft(i(6));

        // Far right: [UI SIZE] [scale %]
        scaleBtn.setBounds(op.removeFromRight(i(42)).withSizeKeepingCentre(i(42), op.getHeight()));
        op.removeFromRight(i(5));
        sizeLabel.setBounds(op.removeFromRight(i(42)).withSizeKeepingCentre(i(42), i(14)));
        op.removeFromRight(i(6)); // breathing room before the OS controls end

        // Left-aligned: LIVE [gap] liveBox [sep] RENDER [gap] renderBox [sep] HQ [sep] LOCK
        // RENDER label is wider than LIVE to avoid truncation. The strip was already full, so LOCK's
        // ~38px came out of the over-provisioned elements — the OS/HQ/scale buttons and the combo
        // boxes, all of which held far more width than their short text needs — and NOT out of the
        // text labels, whose original widths were already snug against their strings.
        const int liveW = i(26), renderW = i(40), innerGap = i(5), boxW = i(33), sep = i(8);
        osLiveLabel.setBounds(op.removeFromLeft(liveW));
        op.removeFromLeft(innerGap);
        osRealtimeBox.setBounds(op.removeFromLeft(boxW));
        op.removeFromLeft(sep);
        osBncLabel.setBounds(op.removeFromLeft(renderW));
        op.removeFromLeft(innerGap);
        osRenderBox.setBounds(op.removeFromLeft(boxW));
        // HQ toggle sits just after the OS selectors (it's a quality control, same group)
        op.removeFromLeft(sep);
        hqButton.setBounds(op.removeFromLeft(i(24)).withSizeKeepingCentre(i(24), op.getHeight()));
        // Trim LOCK — not an OS control, but styled/grouped with them as the strip's toggle row.
        // Wider than HQ's box: the button font floors at 7px (drawButtonText's jmax) while the box
        // scales down, so at 0.5x this 4-glyph word needs the extra width HQ's 2 glyphs don't.
        op.removeFromLeft(sep);
        trimLockButton.setBounds(op.removeFromLeft(i(38)).withSizeKeepingCentre(i(38), op.getHeight()));

        // Whatever's left before the UI SIZE controls is free — drop the version stamp there.
        versionLabel.setBounds(op);
    }

    scaleBtn.setButtonText(juce::String(juce::roundToInt(currentScale * 100.0f)) + "%");
    audioProcessor.apvts.state.setProperty("uiScale", (double)currentScale, nullptr);
}

// ── Scale helpers ─────────────────────────────────────────────────────────────

void TommyAudioProcessorEditor::refreshFonts(float sc)
{
    auto bold = [](float sz) { return juce::Font(juce::FontOptions(sz, juce::Font::bold)); };

    inputPanelLabel .setFont(bold(8.0f  * sc).withExtraKerningFactor(0.20f));
    outputPanelLabel.setFont(bold(8.0f  * sc).withExtraKerningFactor(0.20f));
    inputTrimLabel  .setFont(bold(7.5f  * sc));
    outputTrimLabel .setFont(bold(7.5f  * sc));
    inputTrimValueLabel .setFont(bold(8.5f * sc));
    outputTrimValueLabel.setFont(bold(8.5f * sc));
    supplyControl   .setFontSize(10.0f * sc); // 25% bigger than the original 8.0f
    bypassLabel     .setFont(bold(7.0f  * sc).withExtraKerningFactor(0.20f));
    osLabel         .setFont(bold(8.0f  * sc).withExtraKerningFactor(0.18f));
    osLiveLabel     .setFont(bold(7.0f  * sc).withExtraKerningFactor(0.15f));
    osBncLabel      .setFont(bold(7.0f  * sc).withExtraKerningFactor(0.15f));
    sizeLabel       .setFont(bold(7.0f  * sc).withExtraKerningFactor(0.15f));
    versionLabel.setFont(juce::Font(juce::FontOptions(7.0f * sc, juce::Font::plain)).withExtraKerningFactor(0.1f));

    auto kFont = bold(8.5f * sc).withExtraKerningFactor(0.15f);
    for (auto* l : { &bassLabel, &gainLabel, &volumeLabel, &trebleLabel })
        l->setFont(kFont);

    tommyLogo.setFont(juce::Font(juce::FontOptions("Brush Script MT", 93.2f * sc, juce::Font::italic))); // 15% bigger than the original 81.0f
}

void TommyAudioProcessorEditor::showScaleMenu()
{
    static constexpr float kScales[] = { 0.50f, 0.75f, 1.00f, 1.25f, 1.50f,
                                         1.75f, 2.00f, 2.25f, 2.50f };
    static constexpr const char* kLabels[] = { "50%",  "75%",  "100%", "125%", "150%",
                                               "175%", "200%", "225%", "250%" };
    juce::PopupMenu menu;
    for (int n = 0; n < 9; ++n)
        menu.addItem(n + 1, kLabels[n], true, std::abs(currentScale - kScales[n]) < 0.01f);

    menu.addSeparator();
    menu.addItem(100, "Set current scale as default");

    menu.showMenuAsync(juce::PopupMenu::Options().withTargetComponent(scaleBtn),
        [this](int result)
        {
            // kScales (static constexpr above) is referenced directly — no re-declaration needed.
            if (result >= 1 && result <= 9)
            {
                setSize(juce::roundToInt(kBaseW * kScales[result - 1]),
                        juce::roundToInt(kBaseH * kScales[result - 1]));
            }
            else if (result == 100)
            {
                if (auto* pf = appProps.getUserSettings())
                {
                    pf->setValue("defaultScale", (double) currentScale);
                    pf->saveIfNeeded();
                }
            }
        });
}
