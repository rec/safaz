# SFZ conversion contract

The canonical format, models, examples and schema now live in uFor:

- [Instrument format](https://github.com/rec/ufor/blob/main/doc/instrument-format.md)
- [Envelope and LFO semantics](https://github.com/rec/ufor/blob/main/doc/modulation-format.md)
- [Native conversion fixture](../conformance/instrument.json)
- [Score schema](https://github.com/rec/ufor/blob/main/schema/scores.json)

`ufor.samples.instrument.SampleInstrumentScore` is the common root. It owns sealed
audio assets, native timebases, output layout and a typed sample-instrument body.
Slots reference named slices and explicit channel maps. `ufor.samples` owns the
musical declarations; `ufor.envelope`, `ufor.lfo` and `ufor.modulation` provide
their shared control definitions. The old Recsam classes and `format_version`
root are removed, with no forwarding modules or compatibility reader.

## SFZ and application ownership

Use `safaz.parser.parse`, `safaz.parser.sample_paths`,
`safaz.compiler.compile_instrument`, and `safaz.exporter.write`.
`parser.py` handles source text
and metadata, `compiler.py` builds the native instrument, `exporter.py` writes
representable SFZ, and `model.py` holds their shared result and diagnostic
types. This split does not change the SFZ conversion rules below.

`safaz.parser.parse(text)` produces parsed regions and diagnostics.
`sample_paths(source)` lists safe relative sample references.
`compile_instrument(source, name=..., title=..., assets=..., output_timebase=...,
output_channels=...)` accepts `ufor.samples.metadata.AudioMetadata` facts
supplied by the caller and produces a `SampleInstrumentScore` where possible.
All of these operations are pure. Unsupported opcodes retain source locations;
missing or malformed required data fails explicitly.

SFZ's DAHDSR becomes four on-segments and a captured release stage. Delay/attack/
hold curves are 0; decay retains curve -5. Release captures the observed level,
approaches zero with time constant `ampeg_release/9` (positive values have a
`0.006/9` second floor), stops at `1e-4`, then fades linearly over 50 ms.
A starting level below `1e-4` skips the approach and shortens the fade in
proportion to that level. Zero release skips the approach but retains the fade.
Derived durations round once to nanoseconds, as defined by the shared stage;
native event/sample conventions remain unchanged. The mapping implements the
frozen sfizz release law, not its block-sensitive event placement or float
recurrence. Existing attack and decay conventions are unchanged.
`ampeg_vel2release` targets the stage's latched time constant before its positive
floor, preserving zero at either velocity endpoint. Other velocity-envelope
times retain their existing duration targets.
Export accepts this representable shape and reports other native release laws
as unsupported, including the former normalized release curve. Other SFZ decimal
durations remain exact fractions. Velocity response becomes the shared typed
multiplier route.
SFZ inclusive endpoints become exclusive native slice/loop ends and reverse on
export. Imported channel maps are identity or the standard mono-to-stereo law.
Each imported instrument selects `body.pan_law="sfizz"`. Mono `pan` and stereo
`stereo_balance` positions retain SFZ `pan / 100`; the selected law supplies the
audited cosine/sine gains and +3/+6 dB compensation once at rendering. Static
channel routes remain the canonical maps, not baked copies of the pan gain.
Export diagnoses `pan_law="native"` rather than silently changing its law.
The convention does not include sfizz's lookup quantization, SIMD differences,
master volume, time-varying spatial controls or client timing.

Static stereo `width` and `position` use the same mathematical convention.
The compiler applies input pan first, then mixes the stereo signals, then
applies output position. Width -100 swaps the inputs, +100 keeps them
independent, and 0 sends the same mix to both outputs. Gains come from the
unquantized equal-power curves. Where necessary the compiler bakes all three
stages into the channel map, since uFor requires the canonical map when
using its balance parameter. Mono sources ignore width and position.
Export reconstructs SFZ controls when it can verify the resulting matrix,
including hard pan, hard position and width endpoints. Several settings can
produce the same matrix. Export preserves the gains and may choose a different
set of equivalent controls. Custom matrices outside this law retain diagnostics.
SFZ `off_by` identifies the existing voice to stop when a new region in the
named `group` starts. Import maps this victim-side rule to native trigger-side
`chokes`; export reverses that mapping and diagnoses graphs SFZ cannot express.

`safaz.exporter.write(score)` returns text and diagnostics without opening files.
Unsafe sample syntax, custom channel maps, named controls/generators, selections,
nonrepresentable routes/envelopes and other losses are reported. Diagnostics
use native `body.slots[...]` / `body.settings...` paths. A partial export must
not be treated as complete. The historical `recs` metadata comment namespace
remains understood. Its version-2 metadata uses the native name/title fields.

`safaz.reader.read(path)` is the application adapter. It checks resolved path
containment, reads/decodes metadata, inspects embedded WAV loops, hashes the
existing file, and passes those facts to the compiler. Its explicit file-reader default
is 48 kHz stereo output; callers may select another supported output layout/rate.
It does not generate audio. `safaz.reader` and `safaz.assets` own file acquisition
and asset inspection.

## Static filter responses

`read()` and `compile_instrument()` accept
`filter_response="diagnose"` (the default) or `filter_response="sfizz_rbj"`.
The default omits active filters and reports a located diagnostic requiring
an explicit response choice. Accepting the latter imports static `lpf_2p`,
`hpf_2p`, `bpf_2p`, and `brf_2p` responses into native `processing.filters`.
The first filter uses `fil_type`, `cutoff`, and `resonance`; the second uses
`fil2_type`, `cutoff2`, and `resonance2`. They retain that serial order and
stable local names `sfz-filter-1` and `sfz-filter-2` after inheritance and
region overrides. A missing type defaults to `lpf_2p` and a missing resonance
to 0 dB. Declared filters without explicit cutoff remain omitted and diagnosed,
including the implicit first filter when only the second is declared.
The documented disabled default and sfizz's initialized zero-cutoff filter
do not establish one verified interpretation. Regions with no filter
declarations have no filters and acquire no filter diagnostics.

The verified static transfer profile comes from sfizz revision
`f5c6e29f23b8057867c08e88f5f6ac6738baa30b`:
[filter definitions](https://github.com/sfztools/sfizz/blob/f5c6e29f23b8057867c08e88f5f6ac6738baa30b/src/sfizz/dsp/filters/sfz_filters.dsp)
and [RBJ coefficients](https://github.com/sfztools/sfizz/blob/f5c6e29f23b8057867c08e88f5f6ac6738baa30b/src/sfizz/dsp/filters/rbj_filters.dsp).
Resonance maps as `Q = 10^(resonance/20)`, so 0 dB becomes Q=1,
rather than the native model's default Q. Import accepts the standard
0–40 dB resonance range. Cutoff must be within
`[1, min(20000, 0.999 * output_sample_rate / 2)]` Hz to avoid sfizz's
internal clipping and the native filter boundary. Values outside this
interval, explicit `cutoff=0`, and unrepresented filter types are diagnosed
without clamping or approximating. Malformed numeric values fail explicitly.

Accepted static responses select native `filter_order=after_amplitude` to match
sfizz's [voice pipeline](https://github.com/sfztools/sfizz/blob/f5c6e29f23b8057867c08e88f5f6ac6738baa30b/src/sfizz/Voice.cpp).
The amplitude envelope, velocity gain, volume, and changing amplitude controls
precede the complete filter chain; native pan and channel routing follow it.
sfizz places stereo pan before filtering; the supported static linear routing
commutes with identical per-channel filters. No extra
filter tail extends the native voice lifetime. This resolves the ordering
diagnostic, so supported static regions can return `complete=True`. The option
still accepts only the declared static transfer profile, not equivalence to
the whole player.

### Keyboard tracking

With the same `sfizz_rbj` choice, `fil_keytrack` and `fil_keycenter` import
keyboard tracking for the first filter; `fil2_keytrack` and `fil2_keycenter`
configure the second independently. Tracking defaults to 0 cents per key and
center to MIDI key 60. Center keys accept the existing numeric and note-name
syntax. The verified standard subset uses integral tracking from 0 to 1200.
The cutoff at an integer note key is
`cutoff * 2^(fil_keytrack * (key - fil_keycenter) / 1200)`.
This formula follows the pinned sfizz
[filter setup](https://github.com/sfztools/sfizz/blob/f5c6e29f23b8057867c08e88f5f6ac6738baa30b/src/sfizz/FilterPool.cpp).

Native multiplication routes contain one point per playable integer key and
share the existing note-key binding with amplitude and pitch tracking. The
original note key determines the ratio, independently of pitch tuning. The
range check uses each region's inclusive key mapping, not notes that cannot
select it. Values outside the verified cutoff interval at any playable key,
unverified tracking amounts, and controller-triggered voices with no note key
retain the static filter with a located diagnostic. No clamping is introduced.
Malformed tracking or center values fail explicitly. A zero track value creates
no route; changing its center does not change the cutoff.

### Velocity tracking

With `sfizz_rbj`, `fil_veltrack` and `fil2_veltrack` independently import
integral depths from -9600 to 9600 cents, defaulting to zero. The continuous
note velocity `v` in [0,1] multiplies the cutoff by `2^(depth*v/1200)`, following
the same pinned sfizz filter setup. uFor's positive-valued `exponential`
interpolation expresses this exactly with two ratio points; it does not
quantize velocity to MIDI integers. Velocity binding is shared with other
velocity-dependent settings. Zero depth creates no route.

Export writes keyboard and velocity tracking for ordinary note-on filters
when their routes and combined bounds match this profile. Release regions
can also export keyboard tracking. A single-key
region can export an equivalent tracking depth and center that yield the
same cutoff for that key. The bounded first-filter envelope can share a
filter with both tracking routes. Re-import with `sfizz_rbj` at the same
output rate and enable the portable envelope profile when used. Other cutoff
routes on the same filter retain diagnostics.

Keyboard and velocity ratios multiply. Bounds cover every playable key and
the full native note-velocity domain [0,1], including output-rate limits.
If individually valid routes exceed the cutoff limits when combined, both
are diagnosed at their declarations and the static filter remains. An
individually unsupported route is diagnosed without discarding another valid
route. No player clamping is approximated. Malformed depths fail explicitly.
Controller and release-triggered velocity tracking remain diagnosed because
their velocity semantics are not verified. The
[velocity fixture](../conformance/filter-velocity-tracking.sfz) demonstrates
inherited, decreasing, combined, and zero-override tracking.

### Basic filter LFO

Import additionally requires a waveform profile alongside
`filter_response="sfizz_rbj"`. Use `filter_lfo_response="sfizz_parabolic"`
to select the pinned player's v1 parabolic waveform. The existing
`filter_lfo_response="sfizz_triangle"` profile preserves the portable triangle
convention. Both `compile_instrument` and `read` accept either choice.

`fillfo_freq` imports fixed frequency from 0 to 20 Hz; `fillfo_depth` imports
signed depth from -1200 to 1200 cents. Both default to zero, which makes the
LFO inactive without creating an envelfo. Both waveforms start at zero rising
after the delay, and the parabolic profile maps the triangle signal `u` to
`u * (2 - abs(u))`. Negative depth inverts its cutoff effect. The cutoff
ratio is `2^(depth * signal / 1200)`, represented
by a positive exponential route. Each new ordinary note-on voice starts its
own oscillator; it runs through release until that voice finishes.

Only the first filter is targeted, following the pinned sfizz legacy
[opcode mapping](https://github.com/sfztools/sfizz/blob/f5c6e29f23b8057867c08e88f5f6ac6738baa30b/src/sfizz/Region.cpp).
LFO, keyboard, and velocity ratios multiply. Bounds cover the full oscillation,
playable keys, and native velocity domain. An individually unsupported LFO
retains valid tracking; a combined out-of-range result diagnoses every active
cutoff route on that filter and retains its static settings. The second filter
remains independent. See the [inheritance fixture](../conformance/filter-lfo.sfz).

Nonzero `fillfo_delay` and `fillfo_fade` compose a phase-offset oscillator and
activation envelope, scaling the signal before cents-to-ratio conversion.
Export recognizes either waveform, delay and fade when it can recreate the
native generator and cutoff routes at the same rate. Re-import with the
original waveform profile and the static filter profile. Controller and
nonordinary note triggers, SFZ 2 LFOs,
and controller/aftertouch modulation remain diagnosed. Malformed or
nonfinite numbers fail explicitly; values outside the verified ranges are
diagnosed without clamping. The [reference findings](../reference_test/findings.md)
record the remaining signed audio residual against pinned sfizz.

Unsupported filter modulation retains its source diagnostic alongside any
accepted static filter. Export writes up to two supported two-pole filters in
serial order after amplitude. Cutoff and resonance must be representable
within the same verified profile and output rate. Other responses, additional
stages remain diagnosed. The [SFZ fixture](../conformance/filters.sfz) and
[native filter settings](../conformance/filters.json) demonstrate inheritance
and the static two-filter mapping without asserting complete playback equivalence.
The [keyboard tracking fixture](../conformance/filter-key-tracking.sfz) covers
inherited tracking, independent centers, and a per-region zero override.

## Static peaking EQ

Select `eq_response="sfizz_rbj"` on import. The profile covers EQ bands 1
through 3 with `eqN_type=peak` (the default), gain from -96 to 96 dB,
bandwidth from 0.001 to 4 octaves (default 1), and an in-range center
frequency. A zero-gain band leaves the signal unchanged.
Pinned sfizz fills a leading run of zero or omitted frequencies with
50, 500, and 5,000 Hz. A subsequent active band with no positive frequency
retains a diagnostic.

The compiler maps octave bandwidth to the digital Q at the declared output
rate. The peaking stage follows amplitude and the resonant filter cascade.
Export writes explicit frequencies and recovers bandwidth from the native Q
at the same rate. Shelves, note and CC modulation, and native pre-amplitude
EQ retain diagnostics.

## Amplifier envelope velocity

The `ampeg_vel2delay`, `ampeg_vel2attack`, `ampeg_vel2hold`,
`ampeg_vel2decay` and `ampeg_vel2release` routes round-trip when their
linear velocity domains and time bounds match the original envelope.
Release targets the exponential time constant before the positive release
floor. Export recovers its seconds value from the native base and delta.

## Filter envelopes

`filter_envelope_response="portable_exponential"`, together with
`filter_response="sfizz_rbj"`, accepts first-filter `fileg_delay`, `fileg_attack`,
`fileg_hold`, `fileg_decay`, `fileg_release`, `fileg_start`, `fileg_sustain` and
`fileg_depth`. Defaults are zero except sustain (100 percent) and release
(0.001 seconds). Times are 0–100 seconds, levels 0–100 percent, and signed depth
is -12000–12000 cents. Zero depth is inactive. Unsupported triggers and richer
modifiers retain diagnostics.

Delay and hold truncate to output frames. Attack has constant unit slope,
so its duration is `attack * (1-start)`. Positive decay/release times use
`max(time, 0.006)/9` as the exponential time constant. Decay approaches zero
until `min(1, sustain+0.001)`, then settles to sustain over 50 ms. Zero decay
jumps directly to sustain. Sustain at or below 0.0032 runs freely into release.
Release approaches `1e-4`, then fades to zero with a 50 ms nominal duration
and a `1e-4` minimum transition-distance rule; zero release retains that fade.

Crossings are continuous and derived durations round once to nearest nanoseconds
before frame conversion. They do not reproduce sfizz's advance-before-output,
previous-sample release capture or block-observed decay threshold. This explicit
convention must not be described as exact sfizz envelope equivalence.

The voice-scoped named Envelope follows the voice release gate. Its cutoff ratio
is `2**(depth * value / 1200)`. Keyboard, velocity, LFO and envelope ratios
multiply. An out-of-range combined cutoff diagnoses every active first-filter
route and retains its static settings. The second filter remains independent.
Export writes `fileg_*` for a single voice-release envelope that shapes the first
filter and can be rebuilt by the importer. Re-import with `sfizz_rbj`,
`portable_exponential` and the same output rate. Delay and hold use canonical
decimal values in the original frame buckets. Positive decay times below the
floor export at the floor, and attack from 100 percent exports as zero because
its native duration is zero. A shape, route, or combination that cannot be
recreated retains a diagnostic. See the
[design and audit](filter-envelope-design.md) and
[qualification findings](../reference_test/findings.md).

Regenerate the support catalog with
`uv run --no-editable python doc/generate-support.py`.

## Performance bindings

SFZ import can return a `ufor.performance_binding.PerformanceBindingScore`
alongside the instrument when the caller supplies
`safaz.model.SfzMidiBindingRequest` with the destination instrument reference,
part, and repeated-key release rule. The import maps SFZ's shared inclusive
`lochan`/`hichan` range, the standard sustain pedal CC 64, and the CCs used by
`loccN`/`hiccN` note-on conditions. Those conditions become inclusive native
control ranges; a missing CC begins at the declared control default of zero.
Without a request, channel opcodes and controller conditions remain
source-located diagnostics. Different channel ranges in
different regions cannot be represented by one instrument-level MIDI channel
filter, so they also remain diagnostics rather than being silently merged.

`<control> set_ccN` imports an initial MIDI CC value (integer 0 through 127)
as a named-control default divided by 127; CC numbers must also be 0 through
127. CC 64 initializes `sustain`. Controllers declared only by `set_ccN` are
also declared and included in the requested MIDI binding. Initial values apply
independently to each part until overridden by an explicit native control event.
They do not send MIDI messages or synthesize controller-triggered voices.
Hosts carrying controller state across instrument loads must emit that state
explicitly.

Without a MIDI binding request, or with mixed per-region channel ranges, initial
values are retained with source-located binding diagnostics. Repeated identical
values are accepted across `<control>` sections. Conflicting values diagnose
every declaration and leave the controller at its existing default rather than
choosing a value. Declarations outside `<control>` are diagnosed and omitted.
Pass the corresponding `PerformanceBindingScore` as
`write(score, midi_binding=...)` to export the shared channel range,
7-bit initial values, note-on controller conditions and the verified
pitch-bend curve. One contiguous channel range and unscaled inputs are
required. Without the binding, named controls retain diagnostics.

## Live CC layer crossfades

`xfin_loccN`/`xfin_hiccN` and `xfout_loccN`/`xfout_hiccN` can
round-trip with `cc_crossfade_response="portable_ramp"` and the shared
MIDI binding. Import requires `xf_cccurve=gain` and two explicit,
strictly increasing 7-bit endpoints for each fade. Controllers used only by
a fade are included in the binding. CC 64 uses the sustain control.

The portable profile ramps each part-local control over 5 ms, maps it to
linear gain across the fade interval, and multiplies the active fade
weights. A silent layer still starts and responds to subsequent CC values.
Initial values come from the named-control defaults, including any
`set_ccN` declarations. The pinned sfizz player smooths the combined gain
after applying its crossfade curves. Its default `power` curve uses
square roots and retains a diagnostic, as do missing or degenerate ranges.

Export requires a matching MIDI binding and the same explicit profile.
Native fades with other smoothing, curve, scope, or endpoint values retain
diagnostics.

## Held and previous-note conditions

`sw_down` requires a physically pressed key and `sw_up` requires a physically
released key. They combine independently with each other and sticky `sw_last`;
all conditions on a region must pass. A shared `sw_lokey`/`sw_hikey` range is
required and consumed. Missing or inconsistent ranges and switch keys outside
the range are not approximated. Overlapping presses are tracked by trigger ID,
and sustain does not keep a key physically pressed. The native state updates
before selection and changing a switch does not alter existing voices.

`sw_previous` selects by the previous note-on in the part, including consumed
switches and unmatched notes. Selection precedes the history update. History
starts empty and survives note releases and silence. Held and previous-note
conditions on `release`/`release_key` regions remain diagnosed until their SFZ
history rules have a verified equivalent. Export writes one shared contiguous
range for consumed latched switches. Each sticky articulation must have one
switch key and appear in an exported region. A note-on region can export one
pressed condition, one released condition and one previous key.

## Controller-triggered regions

`on_loccN`/`on_hiccN` imports one triggering CC per region with both inclusive
endpoints explicitly assigned. Values and controller numbers must be 0 through
127. The first supported subset requires `key=-1`, `loop_mode=one_shot`,
`pitch_keytrack=0`, and `amp_veltrack=0`, with no other note-dependent processing,
selection, or explicit `trigger` declaration. Ordinary `loccN`/`hiccN` conditions
use the updated part-control values. Uncertain combinations are located
diagnostics, and their regions are omitted rather than becoming note regions.
The registry keeps controller triggers classified as `controller_binding`.

Every matching part-scoped control message starts a voice, including repeated
identical values. Initial defaults do not trigger voices. The native trigger
rule records the region's pitch-center frequency and unit velocity, which do
not influence note-independent processing. It creates no note key or note
identity, and does not update physical presses, previous-note history, or
note-on sequence counters. Voices finish naturally; existing chokes and voice
limits can retire them. Note release, sustain, and leaving the controller range
do not release them. The binding request and shared channel-range requirements
match other imported controller conditions. With that binding, export
round-trips the note-independent one-shot profile. Unrepresentable triggers
remain diagnosed and their regions are omitted.

## Sequence counters

SFZ import reports `seq_length` and `seq_position` as unsupported by
default; callers must explicitly request `sequence_counter='all_note_ons'`.
That rule advances once for every note-on in the part, even when no slot is
eligible. Export writes the corresponding opcodes and retains the
player-dependent diagnostic unless the caller selects
`sequence_counter='all_note_ons'`. Re-import with the same profile.

Numeric group polyphony uses the separately selected
`polyphony_overflow='oldest_immediate'` profile on import and export.
Export recognizes stacked-note pools using oldest replacement and one
shared SFZ group per pool. Groups that could reject simultaneous layers
retain diagnostics. The profile does not select a retirement rule for
other SFZ players.

## Seeded variation

`read` and `compile_instrument` accept
`variation_response="portable_seeded"` for ordinary note-on regions.
Omitted or zero depths are inactive. Without the explicit profile, nonzero
declarations retain source diagnostics.

| Opcode | Bounds | Native behavior |
| --- | --- | --- |
| `amp_random` | -24 to 24 dB | Uniform gain in dB over the interval from zero to the declared value. |
| `pitch_random` | -12000 to 12000 cents | Uniform tuning shift over the interval from zero to the declared value. |
| `offset_random` | 0 to 2147483647 frames | Inclusive integer offset for forward, unlooped playback that stays inside the slice. |
| `delay_random` | 0 to 100 seconds | Uniform added delay when the maximum total delay is at most 100 seconds and the note-off rule is verified. |

The compiler recenters gain and pitch in the native base settings because the
variation model draws symmetrically around zero. uFor resolves independent
draws using the caller's seed, part, event identity and slot identity. Native
playback uses the resulting voice values. The focused reference regression
checks pending and active sampler snapshot continuation on enge's NumPy
and native offline backends.

Export uses the same explicit `variation_response="portable_seeded"` profile.
It writes representable distributions and chooses authored gain and pitch
endpoints that reconstruct the exact native midpoints. Either signed interval
orientation may produce the same midpoint and range. The default writer
diagnoses nonzero variation, since SFZ carries no seed or shared random
stream. Re-import with safaz and supply the same seed and event identities
to reproduce native draws. Out-of-range windows and base values retain
diagnostics.
One-shot delayed note-off, release regions and controller triggers are outside
this profile.

## Changes to authored documents

Use the [conversion instructions](https://github.com/rec/ufor/blob/main/doc/instrument-format.md#updating-old-declarations).
Move metadata to the common root, replace sample paths with sealed assets and
slice IDs, and declare output clocks/channels. Envelope overrides are complete
segment definitions. Playback overrides use explicit nullable fields so
inheritance survives serialization. Routes use structured targets and declared
source bindings. Unit strings such as `10ms` are authoring input, not native
data: normalize them before constructing uFor models.

This changes instrument documents, not recording descriptors or production
sessions. Creating instruments from edits and hosting playback belong outside
recs; the sampler engine is in enge.
