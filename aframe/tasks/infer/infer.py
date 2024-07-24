import socket
from pathlib import Path

import law
import luigi
import numpy as np
import psutil
from luigi.util import inherits

from aframe.tasks.infer.base import InferBase, InferParameters
from hermes.aeriel.serve import serve


@inherits(InferParameters)
class DeployInferLocal(InferBase):
    """
    Launch inference on local gpus
    """

    triton_image = luigi.Parameter()

    @staticmethod
    def get_ip_address() -> str:
        """
        Get the local nodes cluster-internal IP address
        """
        for _, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if (
                    addr.family == socket.AF_INET
                    and not addr.address.startswith("127.")
                ):
                    return addr.address
        raise ValueError("No valid IP address found")

    @property
    def model_repo_dir(self):
        return self.input()["model_repository"].path

    def workflow_run_context(self):
        """
        Law hook that provides a context manager
        in which the whole workflow is run
        """
        server_log = self.output_dir / "server.log"
        return serve(
            self.model_repo_dir, self.image, log_file=server_log, wait=True
        )


@inherits(DeployInferLocal)
class Infer(law.Task):
    """
    Aggregate inference results
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.foreground_output = self.output_dir / "foreground.hdf5"
        self.background_output = self.output_dir / "background.hdf5"
        self.zero_lag_output = self.output_dir / "0lag.hdf5"

    def output(self):
        output = {}
        output["foreground"] = law.LocalFileTarget(self.foreground_output)
        output["background"] = law.LocalFileTarget(self.background_output)
        if self.zero_lag:
            output["zero_lag"] = law.LocalFileTarget(self.zero_lag_output)
        return output

    def requires(self):
        return DeployInferLocal.req(self)

    @property
    def targets(self):
        return list(self.input().collection.targets.values())

    @property
    def background_files(self):
        return list(map(Path, [targets[0].path for targets in self.targets]))

    @property
    def foreground_files(self):
        return list(map(Path, [targets[1].path for targets in self.targets]))

    def run(self):
        from infer.utils import get_shifts
        from ledger.events import EventSet, RecoveredInjectionSet

        # separate 0lag and background events into different files
        shifts = get_shifts(self.background_files)
        zero_lag = np.array(
            [all(shift == [0] * len(self.ifos)) for shift in shifts]
        )

        zero_lag_files = self.background_files[zero_lag]
        back_files = self.background_files[~zero_lag]

        EventSet.aggregate(
            back_files, self.background_output, clean=self.clean
        )
        RecoveredInjectionSet.aggregate(
            self.foreground_files, self.foreground_output, clean=self.clean
        )
        if len(zero_lag_files) > 0:
            EventSet.aggregate(
                zero_lag_files, self.zero_lag_output, clean=self.clean
            )
