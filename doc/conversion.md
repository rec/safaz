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

SFZ's fixed DAHDSR becomes four on-segments and a release segment. Delay/attack/
hold curves are 0; decay/release are -5. SFZ decimal durations become exact
fractions. Export accepts that representable shape and reports general envelopes
as unsupported. Velocity response becomes the shared typed multiplier route.
SFZ inclusive endpoints become exclusive native slice/loop ends and reverse on
export. Imported channel maps are identity or the standard mono-to-stereo law.
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

Unsupported filter modulation retains its source diagnostic alongside any
accepted static filter. Filter export, higher-order and alternate filter
types, key/velocity tracking, controller modulation, envelopes, and LFOs
remain unsupported. The [SFZ fixture](../conformance/filters.sfz) and
[native filter settings](../conformance/filters.json) demonstrate inheritance
and the static two-filter mapping without asserting complete playback equivalence.

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
Initial controller export remains unsupported under the existing named-control
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
history rules have a verified equivalent. Export remains diagnosed.

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
match other imported controller conditions. Export remains diagnosed and omits
control-triggered regions.

## Sequence counters

SFZ import reports `seq_length` and `seq_position` as unsupported by
default; callers must explicitly request `sequence_counter='all_note_ons'`.
That rule advances once for every note-on in the part, even when no slot is
eligible. It is not a claim that all SFZ players count
identically. SFZ export writes the corresponding opcodes but reports that the
player-dependent counter rule cannot be guaranteed by the file.

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
