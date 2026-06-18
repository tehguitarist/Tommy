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
                  nullptr)
{
    setLookAndFeel(&laf);

    // ── Side panel: Input ────────────────────────────────────────────────────
    configureLabel(inputPanelLabel, 8.0f, TommyLookAndFeel::cTrimLabel);
    inputPanelLabel.setFont(
        juce::Font(juce::FontOptions(8.0f, juce::Font::bold)).withExtraKerningFactor(0.2f));

    configureTrimKnob(inputTrimKnob);
    inputTrimKnob.setRange(-12.0, 12.0);

    configureLabel(inputTrimLabel, 7.5f, TommyLookAndFeel::cTrimLabel - 0x001A0000u);

    addAndMakeVisible(inputVU);

    // ── Side panel: Output ───────────────────────────────────────────────────
    configureLabel(outputPanelLabel, 8.0f, TommyLookAndFeel::cTrimLabel);
    outputPanelLabel.setFont(
        juce::Font(juce::FontOptions(8.0f, juce::Font::bold)).withExtraKerningFactor(0.2f));

    configureTrimKnob(outputTrimKnob);
    outputTrimKnob.setRange(-12.0, 12.0);

    configureLabel(outputTrimLabel, 7.5f, TommyLookAndFeel::cTrimLabel - 0x001A0000u);

    addAndMakeVisible(outputVU);

    // ── Pedal face: power label ──────────────────────────────────────────────
    configureLabel(powerLabel, 8.0f, TommyLookAndFeel::cPowerLabel);

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
        configureKnob(*s);

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
    tommyLogo.setColour(juce::Label::textColourId, juce::Colour(TommyLookAndFeel::cLabelText));
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
    // DSP processing of silence produces denormals / tiny residuals that would otherwise
    // light the lowest segment permanently. ~-66 dBFS floor is well below any real signal.
    static constexpr float kNoiseFl = 5e-4f;
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
        lp.removeFromTop(i(6));
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
        rp.removeFromTop(i(6));
        outputVU.setBounds(rp.withSizeKeepingCentre(i(24), rp.getHeight()));
    }

    // ── Pedal face ────────────────────────────────────────────────────────
    {
        auto pp = pedalBounds.reduced(i(10), i(10));

        powerLabel.setBounds(pp.removeFromTop(i(18)));
        sepLineY = powerLabel.getBottom() + i(5);
        pp.removeFromTop(i(6));

        // Row 1: Bass · SW1 · Gain
        auto row1 = pp.removeFromTop(i(72));
        pp.removeFromTop(i(8));
        {
            const int secW = row1.getWidth() / 3;
            auto bassSection = row1.removeFromLeft(secW);
            auto gainSection = row1.removeFromRight(secW);
            auto sw1Section  = row1;

            bassKnob.setBounds(bassSection.removeFromTop(i(55)).withSizeKeepingCentre(i(50), i(50)));
            bassLabel.setBounds(bassSection.withSizeKeepingCentre(bassSection.getWidth(), i(12)));
            gainKnob.setBounds(gainSection.removeFromTop(i(55)).withSizeKeepingCentre(i(50), i(50)));
            gainLabel.setBounds(gainSection.withSizeKeepingCentre(gainSection.getWidth(), i(12)));
            sw1Switch.setBounds(sw1Section.withSizeKeepingCentre(sw1Section.getWidth(), i(65)));
        }

        // Row 2: Volume · LED · Treble
        auto row2 = pp.removeFromTop(i(72));
        pp.removeFromTop(i(8));
        {
            const int secW = row2.getWidth() / 3;
            auto volSection  = row2.removeFromLeft(secW);
            auto trebSection = row2.removeFromRight(secW);
            auto ledSection  = row2;

            volumeKnob.setBounds(volSection.removeFromTop(i(55)).withSizeKeepingCentre(i(50), i(50)));
            volumeLabel.setBounds(volSection.withSizeKeepingCentre(volSection.getWidth(), i(12)));
            trebleKnob.setBounds(trebSection.removeFromTop(i(55)).withSizeKeepingCentre(i(50), i(50)));
            trebleLabel.setBounds(trebSection.withSizeKeepingCentre(trebSection.getWidth(), i(12)));
            led.setBounds(ledSection.withSizeKeepingCentre(i(18), i(18)));
        }

        // Tommy logo + bypass (built bottom-up)
        pp.removeFromBottom(i(8));
        bypassLabel.setBounds(pp.removeFromBottom(i(13)));
        pp.removeFromBottom(i(5));
        bypassButton.setBounds(pp.removeFromBottom(i(52)).withSizeKeepingCentre(i(52), i(52)));
        pp.removeFromTop(i(4));
        tommyLogo.setBounds(pp.withSizeKeepingCentre(pp.getWidth(), juce::jmin(i(72), pp.getHeight())));
    }

    // ── Oversampling strip ────────────────────────────────────────────────
    {
        auto op = osRow.reduced(i(10), 0);

        // "OS" label on far left
        osLabel.setBounds(op.removeFromLeft(i(20)));
        op.removeFromLeft(i(8));

        // Scale preset button + "UI SIZE" label at far right
        scaleBtn.setBounds(op.removeFromRight(i(48)).withSizeKeepingCentre(i(48), i(16)));
        op.removeFromRight(i(5));
        sizeLabel.setBounds(op.removeFromRight(i(42)).withSizeKeepingCentre(i(42), i(14)));
        op.removeFromRight(i(8)); // breathing room before the OS controls end

        // Left-aligned: LIVE [gap] liveBox [sep] RENDER [gap] renderBox
        // RENDER label is wider than LIVE to avoid truncation
        const int liveW = i(26), renderW = i(40), innerGap = i(5), boxW = i(36), sep = i(12);
        osLiveLabel.setBounds(op.removeFromLeft(liveW));
        op.removeFromLeft(innerGap);
        osRealtimeBox.setBounds(op.removeFromLeft(boxW));
        op.removeFromLeft(sep);
        osBncLabel.setBounds(op.removeFromLeft(renderW));
        op.removeFromLeft(innerGap);
        osRenderBox.setBounds(op.removeFromLeft(boxW));
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
    powerLabel      .setFont(bold(8.0f  * sc));
    bypassLabel     .setFont(bold(7.0f  * sc).withExtraKerningFactor(0.20f));
    osLabel         .setFont(bold(8.0f  * sc).withExtraKerningFactor(0.18f));
    osLiveLabel     .setFont(bold(7.0f  * sc).withExtraKerningFactor(0.15f));
    osBncLabel      .setFont(bold(7.0f  * sc).withExtraKerningFactor(0.15f));
    sizeLabel       .setFont(bold(7.0f  * sc).withExtraKerningFactor(0.15f));

    auto kFont = bold(8.5f * sc).withExtraKerningFactor(0.15f);
    for (auto* l : { &bassLabel, &gainLabel, &volumeLabel, &trebleLabel })
        l->setFont(kFont);

    tommyLogo.setFont(juce::Font(juce::FontOptions("Brush Script MT", 81.0f * sc, juce::Font::italic)));
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
            static constexpr float kScales[] = { 0.50f, 0.75f, 1.00f, 1.25f, 1.50f,
                                                  1.75f, 2.00f, 2.25f, 2.50f };
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
