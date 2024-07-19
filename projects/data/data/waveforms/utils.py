import logging
import random
import time
from pathlib import Path
from typing import List
from zlib import adler32

import numpy as np
import torch
from gwpy.timeseries import TimeSeriesDict


def convert_to_detector_frame(samples: dict[str, np.ndarray]):
    """Converts mass parameters from source to detector frame"""
    for key in ["mass_1", "mass_2", "chirp_mass", "total_mass"]:
        if key in samples:
            samples[key] = samples[key] * (1 + samples["redshift"])
    return samples


def seed_worker(start: float, stop: float, shifts: List[float], seed: int):
    fingerprint = str((start, stop) + tuple(shifts))
    worker_hash = adler32(fingerprint.encode())
    logging.info(
        "Seeding data generation with seed {}, "
        "augmented by worker seed {}".format(seed, worker_hash)
    )
    np.random.seed(seed + worker_hash)
    random.seed(seed + worker_hash)


def calc_segment_injection_times(
    start: float,
    stop: float,
    spacing: float,
    buffer: float,
    waveform_duration: float,
):
    """
    Calculate the times at which to inject signals into a segment

    Args:
        start:
            The start time of the segment
        stop:
            The stop time of the segment
        spacing:
            The amount of time, in seconds, to leave between the end
            of one signal and the start of the next
        buffer:
            The amount of time, in seconds, on either side of the
            segment within which injection times will not be
            generated
        waveform_duration:
            The duration of the waveform in seconds

    Returns: np.ndarray of injection times
    """

    buffer += waveform_duration // 2
    spacing += waveform_duration
    injection_times = np.arange(start + buffer, stop - buffer, spacing)
    return injection_times


def load_psds(background: Path, ifos: List[str], df: float) -> torch.Tensor:
    """Calculate PSDs from background generated by `background.py`"""
    background = TimeSeriesDict.read(background, path=ifos)
    psds = []
    for ifo in ifos:
        psd = background[ifo].psd(1 / df, window="hann", method="median")
        psds.append(psd.value)
    psds = torch.tensor(np.stack(psds), dtype=torch.float64)
    return psds


def io_with_blocking(f, fname, timeout=10):
    """
    Function that assists with multiple processes writing to the same file
    """
    start_time = time.time()
    while True:
        try:
            return f(fname)
        except BlockingIOError:
            if (time.time() - start_time) > timeout:
                raise
