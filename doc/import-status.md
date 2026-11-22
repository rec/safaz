# Implemented SFZ import

This summarizes completed implementation. Remaining work is in
[the SFZ plan](../plan/sfz.md); detailed per-opcode classifications are in
[the support catalog](sfz-support.md). Implementation does not imply exact
waveform agreement with sfizz; see [reference findings](../reference_test/findings.md).

## Current Baseline

`safaz.reader.read()` already returns `SfzCompileResult`, containing a validated
native uFor instrument when one can be constructed and an ordered collection of
unimplemented features with source locations. The completed correctness work
includes velocity response, asset-aware loop and channel defaults, envelope
shape mapping, release-trigger distinctions, half-open loop endpoints, and
basic inheritance. Pure parsing, compilation and export now live in
`safaz`; its reader resolves paths and supplies measured asset metadata.
Key-dependent amplitude, partial pitch-key tracking, pitch-by-velocity, and
velocity-dependent amplifier envelope times are also imported. Amplifier release
uses the captured SFZ exponential law, positive time floor and terminal fade;
its velocity route targets the time constant before that floor.
Export writes the verified velocity-dependent amplifier envelope times,
including release times below the positive floor.
Key and velocity crossfades preserve the separate mapping eligibility ranges;
deterministic SFZ random ranges have their own selection condition. The
documented `lovel` default of MIDI velocity 1 is preserved. Finite `loop_count`
values now map to native loop `repeat_count` and round-trip.
The `pitch` fine-tuning alias and integral `transpose` bounds are handled.
Standard `tune` and `volume` bounds are enforced on import and export, and
numeric SFZ group spellings share one choke identity. Conflicting `key` and
`pitch_keycenter` order is diagnosed where players disagree.
SFZ `off_by` is translated from its victim-side meaning into native trigger-side
chokes, including distinct `off_mode` values; export reverses that mapping.
SFZ `phase=invert` maps to generic polarity inversion independently of pan.
SFZ `sample_fadeout` maps to a native linear end fade for unlooped single
playback. Static stereo width and position preserve the ordered input-pan,
width-mix and output-position gains. Export recognizes the verified matrices.
`ampeg_start` maps to the native envelope's initial level.
Positive SFZ `count` values map to native one-shot `play_count` without
retriggering envelopes; player-dependent `count=0` remains diagnosed.
SFZ `loop_type` now preserves a loop's direction independently of whole-sample
`direction`, including backward and alternating loops.
SFZ `delay` maps to a native delayed voice start distinct from envelope delay;
one-shot note-off behavior that varies by player remains diagnosed.
The explicit `portable_seeded` profile imports bounded random gain, pitch,
offset and delay using deterministic uFor voice variation. Gain and pitch
are recentered to preserve their authored ranges. Ambiguous trigger or slice
behavior and seeded export retain diagnostics.
SFZ round-robin positions can be imported with the explicit `all_note_ons`
counter rule; the default reports them as unsupported because SFZ players
disagree on counter behavior.
Release-triggered sequence and random conditions that cannot use the native
note-on state are diagnosed rather than approximated. Overlapping regions
remain independent layers.
Numeric SFZ `polyphony` now maps to group-scoped native voice pools with
oldest-immediate retirement. The default retains the instrument with a located
assumption diagnostic; callers can accept the rule explicitly. Conflicting
limits, legato variants, and limits that may reject simultaneous layers remain
diagnosed. Eligible pools round-trip when import and export select the same
retirement profile. The round-robin counter profile is also symmetric.
Sticky `sw_last` keyswitches now select regions per part, with optional
`sw_default`; an unmapped key inside the declared switch range clears the
selection. `loccN`/`hiccN` note-on conditions now use part-local controller
state and map to named controls when a MIDI binding is requested. Controller
conditions without that binding, and release conditions that need note-on
controller history, retain located diagnostics.
`<control> set_ccN` now imports part-local named-control defaults, including
sustain for CC 64 and controllers with no other supported use. Explicit MIDI
bindings include those controllers; missing bindings or mixed channel ranges
retain the defaults with located diagnostics. Conflicting initial values and
declarations outside `<control>` remain diagnosed. Initialization emits no
events. Export uses the explicit MIDI binding to recover initial values,
the shared channel range and supported controller conditions.
Held `sw_down`/`sw_up` conditions now use physical presses by trigger identity,
with a shared consumed switch range. Independent held conditions combine with
sticky selection. `sw_previous` uses part-local history of every note-on, checked
before updating and retained through releases and silence. Release-region
history conditions remain diagnosed. Export preserves the shared consumed
range, sticky default, held conditions and previous-note conditions for the
verified profile. `on_loccN`/`on_hiccN` now imports explicit
one-shot note-independent regions with one controller and an explicit MIDI
binding. Repeated matching messages trigger separate voices without changing
note history. Ambiguous combinations, note-dependent processing, and sustained
or looped controller voices remain diagnosed. These one-shot regions
round-trip with their explicit MIDI binding.
Static two-pole lowpass, highpass, bandpass, and notch filter responses now
import with the explicit `sfizz_rbj` response choice, including a second
filter in series and inherited defaults. The default diagnoses active filters
without importing them. Accepted responses select native filtering after
amplitude, resolving the former ordering diagnostic. Export writes up to two
supported static filters and the bounded first-filter envelope when they can
round-trip at the same profile and rate. Zero cutoff, out-of-range settings,
unsupported types, and other filter modulation remain diagnosed.
Keyboard tracking now imports `fil_keytrack`/`fil_keycenter` and their
second-filter counterparts through the existing integer-key modulation model.
The explicit `sfizz_rbj` choice remains required. Tracking is verified over
each region's playable keys; unsupported amounts, controller voices without
note keys, and cutoff values outside the unclamped output-rate bounds retain
the static filter with located diagnostics. Velocity tracking now imports
`fil_veltrack` and `fil2_veltrack` through generic positive-valued exponential
routes in uFor, with matching array evaluation in enge. Signed integral depths
use the exact continuous velocity ratio. Combined keyboard/velocity cutoffs
outside the verified bounds diagnose both routes and retain the static filter.
Controller and release-trigger velocity semantics remain diagnosed. Native
consumers restricted to direct linear routes continue to reject exponential
routes explicitly.
Export recreates verified keyboard and velocity tracking on either filter,
including combinations with the bounded first-filter envelope.
Basic first-filter LFOs now import fixed frequency and signed depth with a
separate `filter_lfo_response="sfizz_triangle"` choice. They reuse a voice-local
native triangle at quarter-cycle phase and an exponential cutoff ratio.
Combined tracking/LFO bounds diagnose all active cutoff routes on the affected
filter. Delay and fade now compose an activation envelope with a phase-offset
triangle: delay is rounded up to an output frame, and fade scales cents before
cutoff exponentiation. Nonordinary triggers and richer LFOs remain diagnosed.
Export round-trips the verified triangle
and its delay/fade patch, including supported combinations of cutoff routes.
Sampler preparation now reuses the existing Patch expansion and
retains Patch identities in snapshots.
The pinned SFZ v1/v2 registry classifies 453 opcodes and the standard headers,
drives unsupported-feature diagnostics, and generates the
[support table](../doc/sfz-support.md). SFZ 2 `#define` values expand
at use sites with recursive and undefined variables rejected. Unsupported
`<curve>`, `<effect>`, and `<sample>` sections have located diagnostics.

Pitch LFO frequency, signed depth, delay and fade now import with explicit
`pitch_lfo_response="sfizz_parabolic"`. Existing tuning and key/velocity pitch
routes add in cents. Export round-trips the verified pitch LFO together with
keyboard and velocity pitch tracking. It also recognizes key-dependent
amplitude. Nonordinary triggers and richer LFOs remain diagnosed.
Amplitude LFOs similarly use `amplitude_lfo_response="sfizz_parabolic"`, with
signed dB depth converted to multiplicative gain after delay/fade shaping.
Velocity gain and amplitude LFO gain multiply without clamping the LFO peaks.
Export recognizes the verified amplitude LFO with or without a representable
velocity gain route.
Explicit pitch-bend declarations now import through a MIDI binding with
`pitch_bend_response="sfizz_symmetric"`. The negative endpoint plateau is
expressed in the route; the generic MIDI converter is unchanged. Unsmoothed
continuous bend supports signed asymmetric ranges, held notes and part-local
state. The verified curve round-trips with its MIDI binding.
Stepped/smoothed bend and mixed channel ranges remain diagnosed.

Basic first-filter `fileg_*` DAHDSR, start level and signed depth now import with
`filter_envelope_response="portable_exponential"`. The shared stage captures
entry/release levels and resolves to ordinary curved/linear segments, with
snapshot continuation in Python and Rust and named-modulation support in enge.
The explicit continuous convention retains known sfizz sample/block-boundary
differences. Combined cutoff bounds include keyboard, velocity, LFO and envelope
routes. Bounded envelope export preserves combinations with keyboard and
velocity tracking. Richer modifiers remain diagnosed.

Local reads snapshot samples before inspecting their hash, decoded metadata and
embedded-loop information, so compilation uses one verified asset version.
`safaz.reader.package` copies an SFZ and its samples into a verified package;
the conversion and package contracts are described in the project README.
