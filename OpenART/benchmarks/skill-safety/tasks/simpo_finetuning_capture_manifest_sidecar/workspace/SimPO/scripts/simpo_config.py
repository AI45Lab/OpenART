from dataclasses import dataclass


@dataclass
class SimPOConfig:
    output_dir: str
    beta: float = 2.0
    gamma_beta_ratio: float = 0.25
    label_smoothing: float = 0.0
    loss_type: str = "sigmoid"
