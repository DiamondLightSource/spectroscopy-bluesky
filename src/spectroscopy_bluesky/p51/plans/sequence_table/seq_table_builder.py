from __future__ import annotations  # enable forward declaration of types

from collections.abc import Callable, Iterable
from typing import Any
from itertools import pairwise

from numpy.typing import NDArray
from ophyd_async.fastcs.panda import SeqTable, SeqTrigger

from .spectrum_based_trigger import SpectrumBasedTrigger


class SeqTableBuilder:
    def __init__(self, seq_table: SeqTable | None = None):
        if seq_table is None:
            seq_table = SeqTable()
        
        self.seq_table : SeqTable = seq_table
        self.convert_to_encoder : Callable[[Any], float] = lambda x: -x * 10000

    def add_positions(self, positions: NDArray, **kwargs) -> SeqTableBuilder:
        self.seq_table += create_seqtable(positions, self.convert_to_encoder, **kwargs)
        return self

    def add_start_end_triggers(
        self, start_trig="outb1", end_trig="outc1"
    ) -> SeqTableBuilder:
        """Add start and end triggers to sequence table
        using :func:`~add_start_end_triggers`

        Args:
            start_trig (str, optional): _description_. Defaults to "outb1".
            end_trig (str, optional): _description_. Defaults to "outc1".

        Returns:
            SeqTableBuilder: _description_
        """
        add_start_end_triggers(self.seq_table, start_trig, end_trig)
        return self

    def add_spectrum_based_triggers(
        self, triggers: list[SpectrumBasedTrigger]
    ) -> SeqTableBuilder:
        for t in triggers:
            self.seq_table += t.to_row()
        return self

    def get_seq_table(self) -> SeqTable:
        return self.seq_table


def add_start_end_triggers(table: SeqTable, start_trig="outb1", end_trig="outc1"):
    """Modify SeqTable rows to add triggers to mark start and end of each motor sweep.
    <li> Each change in trigger direction (e.g. POSA<POSITION to POSA>>POSITION)
    corresponds to end of one and start of next sweep
    <li> Assume that first row is start of a sweep, and last row is end of a sweep.

    Args:
        table (SeqTable):The Sequence table to to be modified
        start_trig (str) : output to be used for start of
                        sweep trigger (outa1, outb2 etc)
        end_trig (str) : output to be used for end of
                        sweep trigger (outa1, outb2 etc)

    """

    table_dict = dict(table)
    # check the specified triggers are valid
    for outname in [start_trig, end_trig]:
        if outname not in table_dict.keys():
            raise ValueError(
                f"Found invalid trigger type '{start_trig}' "
                f"when adding sweep start and end triggers"
            )

    # first row is start of a sweep
    table_dict[start_trig][0] = True
    for i in range(len(table) - 1):
        if table.trigger[i] != table.trigger[i + 1]:
            print(table.trigger[i], table.trigger[i + 1])
            # end of a sweep
            table_dict[end_trig][i] = True

            # start of next sweep
            table_dict[start_trig][i + 1] = True
    # assume last row is end of sweep
    table_dict[end_trig][-1] = True


def create_seqtable(
    positions: Iterable[float],
    convert_encoder_counts: Callable[[Any], float],
    **kwargs,
) -> SeqTable:
    """
    Create SeqTable with rows setup to do position based triggering.

    <li> Each position in positions NDArray is converted to a row of the sequence table.
    <li> Position values are converted to encoder counts using
        'get_encoder_counts' function.
    <li> SeqTrigger direction set to GT or LT depending on when encoder values
        increase or decrease.

    :param positions: positions in user coordinates.
    :param kwargs: additional kwargs to be used when generating each
    row of sequence table (e.g. for setting trigger outputs, trigger length etc.)
    :return: SeqTable
    """

    # convert user positions to encoder positions
    enc_count_positions = [int(convert_encoder_counts(x)) for x in positions]

    # determine direction of each segment
    direction = [
        SeqTrigger.POSA_GT if current < next else SeqTrigger.POSA_LT
        for current, next in pairwise(enc_count_positions)
    ]
    direction.append(direction[-1])

    table = SeqTable()
    for d, p in zip(direction, enc_count_positions, strict=True):
        table += SeqTable.row(repeats=1, trigger=d, position=p, **kwargs)
    return table
