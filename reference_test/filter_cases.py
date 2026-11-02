"""Positive filter profiles with independently authored settings and notes."""

from filter_oracle import FilterProfile, FilterSpec
from harness import Case, Note

STATIC_CASES = [
    Case(
        name=f'filter-static-{s}-{r}',
        notes=[Note(tick=11)],
        end_tick=6000,
        source_channels=1,
        filter_profile=FilterProfile(filters=[FilterSpec(response=s, resonance=r)]),
    )
    for s in ('lpf_2p', 'hpf_2p', 'bpf_2p', 'brf_2p')
    for r in (0, 6)
] + [
    Case(
        name='filter-cascade',
        notes=[Note(tick=11)],
        end_tick=6000,
        source_channels=1,
        filter_profile=FilterProfile(
            filters=[
                FilterSpec(response='lpf_2p', cutoff=2400, resonance=6),
                FilterSpec(response='hpf_2p', cutoff=400),
            ]
        ),
    ),
    Case(
        name='filter-amplitude-order',
        notes=[Note(tick=11)],
        end_tick=6000,
        source_channels=1,
        filter_profile=FilterProfile(
            filters=[FilterSpec(response='lpf_2p', cutoff=1000, resonance=20)],
            attack=0.01,
        ),
    ),
]

TRACKING_CASES = [
    Case(
        name=f'filter-tracking-{n}',
        notes=[
            Note(tick=11, key=k[0], velocity=v[0]),
            Note(tick=5001, key=k[1], velocity=v[1]),
            Note(tick=10001, key=k[2], velocity=v[2]),
        ],
        end_tick=14000,
        source_channels=1,
        filter_profile=FilterProfile(filters=f),
    )
    for n, f, k, v in [
        ('key', [FilterSpec(response='lpf_2p', keytrack=100)], [48, 60, 72], [127] * 3),
        (
            'velocity-up',
            [FilterSpec(response='lpf_2p', veltrack=1200)],
            [60] * 3,
            [32, 64, 127],
        ),
        (
            'velocity-down',
            [FilterSpec(response='lpf_2p', veltrack=-1200)],
            [60] * 3,
            [32, 64, 127],
        ),
        (
            'combined',
            [FilterSpec(response='lpf_2p', keytrack=100, veltrack=600)],
            [48, 60, 72],
            [32, 64, 127],
        ),
        (
            'second',
            [
                FilterSpec(response='lpf_2p', cutoff=4000),
                FilterSpec(response='hpf_2p', cutoff=400, keytrack=100, veltrack=1200),
            ],
            [48, 60, 72],
            [32, 64, 127],
        ),
    ]
]

LFO_CASES = [
    Case(
        name=f'filter-lfo-{f}-{d}',
        notes=[Note(tick=11), Note(tick=5001)],
        end_tick=10000,
        source_channels=1,
        filter_profile=FilterProfile(
            filters=[FilterSpec(response='lpf_2p', lfo_frequency=f, lfo_depth=d)]
        ),
    )
    for f, d in [(2, 1200), (2, -1200), (5, 600)]
] + [
    Case(
        name='filter-lfo-combined',
        notes=[Note(tick=11), Note(tick=5001, key=62, velocity=64)],
        end_tick=10000,
        source_channels=1,
        filter_profile=FilterProfile(
            filters=[
                FilterSpec(
                    response='lpf_2p',
                    keytrack=100,
                    veltrack=-600,
                    lfo_frequency=3,
                    lfo_depth=900,
                ),
                FilterSpec(response='hpf_2p', cutoff=300),
            ]
        ),
    ),
]
