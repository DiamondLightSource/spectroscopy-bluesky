from enum import Enum

from ophyd_async.fastcs.panda import SeqTable, SeqTrigger
from pydantic import BaseModel


class SpectrumTriggerType(Enum):
    START = 0
    END = 1


class SpectrumBasedTrigger(BaseModel):
    spectrum_number: int
    trigger_type: SpectrumTriggerType = SpectrumTriggerType.START
    output_ports: list[int] = []
    output_length: float = 0.0
    output_delay: float = 0.0
    output_num_repeats: int = 1

    # convert time from seconds to microseconds
    def convert_time(self, float_time : float) :
        return int(float_time*1e6)

    def to_row(self) -> SeqTable:
        trigger = (
            SeqTrigger.BITA_1
            if self.trigger_type == SpectrumTriggerType.START
            else SeqTrigger.BITB_1
        )
        # wait for some number of triggers
        wait_rows = SeqTable.row(repeats=self.spectrum_number, trigger=trigger)

        # add row for the output delay
        if self.output_delay > 0:
            delay_row = SeqTable.row(repeates=1, trigger=SeqTrigger.IMMEDIATE)
            delay_row.time1[0] = self.convert_time(self.output_delay)
            wait_rows += delay_row

        # Add the row for the output trigger(s)
        trigger_row = SeqTable.row(repeats=self.output_num_repeats, trigger=SeqTrigger.IMMEDIATE)

        # output pulse length(time1)
        trigger_row.time1[0] = self.convert_time(self.output_length)

        # trigger outputs 
        outputs1 = [
            trigger_row.outa1,
            trigger_row.outb1,
            trigger_row.outc1,
            trigger_row.outd1,
            trigger_row.oute1,
            trigger_row.outf1,
        ]

        # Set each outa1, outb1 etc to true/flase according to output_ports list
        # e.g. if output_ports = [1,3] => outa1=True, outb1=True
        for index, val in enumerate(outputs1):
            if index+1 in self.output_ports:
                val[0] = [True]

        return wait_rows+trigger_row

    def __init__(self, spectrum_number, output_ports=[], **kwargs):
        super().__init__(spectrum_number=spectrum_number, output_ports=output_ports, **kwargs)
