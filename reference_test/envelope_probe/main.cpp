// Diagnostic client of the unchanged sfizz envelope and filter implementations.
#include "ADSREnvelope.h"
#include "Curve.h"
#include "EGDescription.h"
#include "MidiState.h"
#include "Region.h"
#include "SfzFilter.h"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <vector>

int main(int argc, char** argv)
{
    if (argc != 3) {
        std::cerr << "usage: envelope_probe REQUEST.txt TRACE.txt\n";
        return 2;
    }
    std::ifstream request(argv[1]);
    int rate, block, frames, gate, triggerDelay;
    sfz::EGDescription description;
    float cutoff, depth, amplitudeRelease;
    if (!(request >> rate >> block >> frames >> gate >> triggerDelay
          >> description.delay >> description.attack >> description.hold
          >> description.decay >> description.release >> description.start
          >> description.sustain >> cutoff >> depth >> amplitudeRelease)
        || rate <= 0 || block <= 0 || frames <= 0 || gate < 0) {
        std::cerr << "invalid probe request\n";
        return 2;
    }
    std::vector<float> input(frames), portable(frames), actual(frames), amplitude(frames);
    for (int i = 0; i < frames; ++i) {
        if (!(request >> input[i] >> portable[i])) {
            std::cerr << "missing source or portable envelope sample\n";
            return 2;
        }
    }
    sfz::MidiState midi;
    sfz::CurveSet curves;
    sfz::Region region(0);
    sfz::ADSREnvelope envelope(midi, curves);
    envelope.reset(description, region, triggerDelay, 1.0f, float(rate));
    sfz::EGDescription amplitudeDescription;
    amplitudeDescription.sustain = 1;
    amplitudeDescription.release = amplitudeRelease;
    sfz::ADSREnvelope amplifier(midi, curves);
    amplifier.reset(amplitudeDescription, region, triggerDelay, 1.0f, float(rate));
    for (int at = 0; at < frames; at += block) {
        const int count = std::min(block, frames - at);
        if (at <= gate && gate < at + count) {
            envelope.startRelease(gate - at);
            amplifier.startRelease(gate - at);
        }
        envelope.getBlock(absl::Span<float>(actual.data() + at, count));
        amplifier.getBlock(absl::Span<float>(amplitude.data() + at, count));
    }
    std::vector<float> amplified(frames);
    for (int i = 0; i < frames; ++i)
        amplified[i] = input[i] * amplitude[i];
    std::vector<float> frequencies[3], filtered[3];
    for (int variant = 0; variant < 3; ++variant) {
        const auto& levels = variant == 0 ? portable : actual;
        frequencies[variant].resize(frames);
        filtered[variant].resize(frames);
        for (int i = 0; i < frames; ++i)
            frequencies[variant][i] = cutoff * std::exp2(depth * levels[i] / 1200.0f);
        sfz::Filter filter;
        filter.init(rate);
        filter.setType(sfz::FilterType::kFilterLpf2p);
        filter.setChannels(1);
        filter.prepare(frequencies[variant][0], 0, 0);
        std::vector<float> resonance(block, 0), gain(block, 0);
        for (int at = 0; at < frames; at += block) {
            const int count = std::min(block, frames - at);
            const auto& samples = variant == 2 ? amplified : input;
            const float* source[] = {samples.data() + at};
            float* destination[] = {filtered[variant].data() + at};
            filter.processModulated(source, destination,
                frequencies[variant].data() + at, resonance.data(), gain.data(), count);
        }
    }
    std::ofstream trace(argv[2]);
    trace << std::setprecision(std::numeric_limits<float>::max_digits10);
    for (int i = 0; i < frames; ++i)
        trace << actual[i] << ' ' << filtered[0][i] << ' ' << filtered[1][i]
              << ' ' << amplitude[i] << ' ' << filtered[2][i] << '\n';
    return trace ? 0 : 1;
}
