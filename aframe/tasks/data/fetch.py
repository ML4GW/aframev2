import os

import law
import luigi
from luigi.util import inherits

from aframe.targets import s3_or_local
from aframe.tasks.data.base import AframeDataTask
from aframe.tasks.data.condor.workflows import DynamicMemoryWorklow
from aframe.tasks.data.query import Query


class Fetch(AframeDataTask, law.LocalWorkflow, DynamicMemoryWorklow):
    start = luigi.FloatParameter()
    end = luigi.FloatParameter()
    data_dir = luigi.Parameter()
    sample_rate = luigi.FloatParameter()
    flag = luigi.Parameter()
    ifos = luigi.ListParameter()
    min_duration = luigi.FloatParameter(default=0)
    max_duration = luigi.FloatParameter(default=-1)
    prefix = luigi.Parameter(default="background")
    segments_file = luigi.Parameter(default="")
    channels = luigi.ListParameter()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.data_dir.startswith("s3://"):
            os.makedirs(self.data_dir, exist_ok=True)

        if self.job_log and not os.path.isabs(self.job_log):
            log_dir = os.path.join(self.data_dir, "logs")
            os.makedirs(log_dir, exist_ok=True)
            self.job_log = os.path.join(log_dir, self.job_log)

    @law.dynamic_workflow_condition
    def workflow_condition(self) -> bool:
        return self.workflow_input()["segments"].exists()

    @workflow_condition.create_branch_map
    def create_branch_map(self):
        segments = self.workflow_input()["segments"].load().splitlines()[1:]
        branch_map, i = {}, 1
        for segment in segments:
            segment = segment.split("\t")
            start, duration = map(float, segment[1::2])
            step = duration if self.max_duration == -1 else self.max_duration
            num_steps = (duration - 1) // step + 1

            for j in range(int(num_steps)):
                segstart = start + j * step
                segdur = min(start + duration - segstart, step)
                branch_map[i] = (segstart, segdur)
                i += 1
        return branch_map

    def workflow_requires(self):
        reqs = super().workflow_requires()

        kwargs = {}
        if self.job_log:
            log_file = law.LocalFileTarget(self.job_log)
            log_file = log_file.parent.child("query.log", type="f")
            kwargs["job_log"] = log_file.path
        reqs["segments"] = Query.req(
            self, segments_file=self.segments_file, **kwargs
        )
        return reqs

    @workflow_condition.output
    def output(self):
        start, duration = self.branch_data
        start = int(float(start))
        duration = int(float(duration))
        fname = "{}-{}-{}.hdf5".format(self.prefix, start, duration)
        fname = os.path.join(self.data_dir, fname)
        return s3_or_local(fname, self.client)

    def run(self):
        import h5py
        from data.fetch.fetch import fetch

        start, duration = self.branch_data
        start = int(float(start))
        duration = int(float(duration))

        X = fetch(
            start,
            start + duration,
            self.channels,
            self.sample_rate,
        )

        with self.output().open("w") as f:
            with h5py.File(f, "w") as h5file:
                X.write(h5file, format="hdf5")
