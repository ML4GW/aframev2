"""
Train multiple models with different seeds
for comparing performance variability
"""
import os

import luigi
import numpy as np

from aframe.base import AframeWrapperTask
from aframe.pipelines.config import paths
from aframe.tasks import ExportLocal, TimeslideWaveforms, Train
from aframe.tasks.infer import InferLocal
from aframe.tasks.plots.sv import SensitiveVolume


class SeedVarExport(ExportLocal):
    train_seed = luigi.IntParameter()

    def requires(self):
        return Train.req(
            self,
            data_dir=paths().train_datadir,
            run_dir=os.path.join(paths().train_rundir, str(self.train_seed)),
            seed=self.train_seed,
            train_remote=True,
        )


class SeedVarInfer(InferLocal):
    train_seed = luigi.IntParameter()

    def requires(self):
        reqs = {}
        reqs["model_repository"] = SeedVarExport.req(
            self,
            repository_directory=os.path.join(
                paths().results_dir, "model_repo"
            ),
            train_seed=self.train_seed,
        )
        ts_waveforms = TimeslideWaveforms.req(
            self,
            output_dir=paths().test_datadir,
        )
        fetch = ts_waveforms.requires().workflow_requires()["test_segments"]

        reqs["data"] = fetch
        reqs["waveforms"] = ts_waveforms
        return reqs


class SeedVarSV(SensitiveVolume):
    train_seed = luigi.IntParameter()

    def requires(self):
        reqs = {}
        reqs["ts"] = TimeslideWaveforms.req(
            self, output_dir=paths().test_datadir
        )

        reqs["infer"] = SeedVarInfer.req(
            self,
            output_dir=os.path.join(paths().results_dir, "infer"),
            train_seed=self.train_seed,
        )
        return reqs


class SeedVariability(AframeWrapperTask):
    num_seeds = luigi.IntParameter(
        default=2,
        description="Number of training jobs with unique seeds to launch",
    )

    def requires(self):
        seeds = np.random.randint(0, 1e5, size=self.num_seeds)
        for seed in seeds:
            yield SeedVarSV.req(
                self,
                train_seed=seed,
                output_dir=os.path.join(
                    paths().results_dir, str(seed), "plots"
                ),
            )
