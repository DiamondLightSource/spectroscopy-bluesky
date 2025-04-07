import math
from typing import Any

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import numpy as np
from dodal.common import MsgGenerator, inject
from dodal.plan_stubs.data_session import attach_data_session_metadata_decorator
from ophyd_async.core import Device, StandardDetector

# todo or is it a tetramm?
I_ZERO: StandardDetector = inject("i0")
I_TRANSMISSION: StandardDetector = inject("it")


def transmission_denoise(
    acceptable_noise: float = 0.05,
    i0: StandardDetector = I_ZERO,
    iT: StandardDetector = I_TRANSMISSION,
    metadata: dict[str, Any] | None = None,
) -> MsgGenerator:
    detectors: set[StandardDetector] = {i0, iT}
    plan_args = {
        "exposure": 0.01,
    }
    _md = {
        "detectors": {device.name for device in detectors},
        "plan_args": plan_args,
        "hints": {},
    }
    _md.update(metadata or {})

    devices: list[Device] = [*detectors]

    yield from bps.open_run()

    @attach_data_session_metadata_decorator()
    @bpp.stage_decorator(devices)
    @bpp.run_decorator(md=_md)
    def inner_plan():
        values: list[float] = []
        max_samples = 20
        min_samples = 3
        while True:
            zero_readout = yield from bps.rd(i0)
            transmission_readout = yield from bps.rd(iT)
            # todo need to make this a vector
            y = math.log(zero_readout - transmission_readout)
            if (
                zero_readout <= 0
                or transmission_readout <= 0
                or transmission_readout > zero_readout
            ):
                print(
                    f"⚠️ Invalid values: I0={zero_readout}, IT={transmission_readout}. Skipping."
                )
                continue

            y = math.log(zero_readout / transmission_readout)
            values.append(y)

            if len(values) < min_samples:
                continue

            arr = np.array(values)
            mean = arr.mean()
            std = arr.std(ddof=1)
            rel_std = std / mean if mean != 0 else float("inf")

            print(
                f"📊 Samples: {len(values)} | Mean: {mean:.5f} | Std: {std:.5f} | RSD: {rel_std:.3%}"
            )

            if rel_std < acceptable_noise or len(values) >= max_samples:
                print("✅ Noise threshold met. Proceeding.")
                break

    yield from inner_plan()
    yield from bps.close_run()
