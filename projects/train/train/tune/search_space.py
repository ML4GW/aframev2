from ray import tune

space = {
    "model.learning_rate": tune.loguniform(1e-4, 1e-1),
    "model.pct_lr_ramp": tune.uniform(0.1, 0.8),
    "model.arch.layers": tune.choice(
        [[2, 3, 4, 5], [3, 4, 6, 3], [4, 6, 6, 4]]
    ),
    "data.kernel_length": tune.choice([1.5, 2.5]),
    "data.swap_frac": tune.uniform(0.0, 0.2),
    "data.mute_frac": tune.uniform(0.0, 0.2),
    "data.waveform_prob": tune.uniform(0.2, 0.8),
}
