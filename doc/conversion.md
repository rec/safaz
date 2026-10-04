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
