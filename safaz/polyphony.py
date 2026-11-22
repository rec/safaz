"""Batch-size validation shared by SFZ polyphony import and export."""

from ufor.samples.instrument import SampleSlot


def oversized_batch(slots: list[SampleSlot], maximum: int) -> bool:
    if len(slots) <= maximum:
        return False
    for trigger in {s.trigger for s in slots}:
        for key in range(128):
            for velocity in range(128):
                if (
                    sum(
                        s.trigger == trigger
                        and s.mapping.lowest_key <= key <= s.mapping.highest_key
                        and s.mapping.minimum_velocity
                        <= velocity / 127
                        <= s.mapping.maximum_velocity
                        for s in slots
                    )
                    > maximum
                ):
                    return True
    return False
