from typing import Tuple

import torch
import torch.nn.functional as F


class SimPOTrainer:
    def __init__(self, model=None, args=None, **kwargs):
        self.model = model
        self.args = args
        self.beta = getattr(args, "beta", 2.0)
        self.gamma_beta_ratio = getattr(args, "gamma_beta_ratio", 0.25)
        self.label_smoothing = getattr(args, "label_smoothing", 0.0)
        self.loss_type = getattr(args, "loss_type", "sigmoid")

    def simpo_loss(
        self,
        policy_chosen_logps: torch.FloatTensor,
        policy_rejected_logps: torch.FloatTensor,
    ) -> Tuple[torch.FloatTensor, torch.FloatTensor, torch.FloatTensor]:
        pi_logratios = policy_chosen_logps - policy_rejected_logps
        logits = pi_logratios - self.gamma_beta_ratio

        if self.loss_type == "sigmoid":
            losses = (
                -F.logsigmoid(self.beta * logits) * (1 - self.label_smoothing)
                - F.logsigmoid(-self.beta * logits) * self.label_smoothing
            )
        elif self.loss_type == "hinge":
            losses = torch.relu(1 - self.beta * logits)
        else:
            raise ValueError(
                f"Unknown loss type: {self.loss_type}. Should be one of ['sigmoid', 'hinge']"
            )

        chosen_rewards = self.beta * policy_chosen_logps
        rejected_rewards = self.beta * policy_rejected_logps
        return losses, chosen_rewards, rejected_rewards
