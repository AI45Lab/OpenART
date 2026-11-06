dependencies = ["torch"]

import torch


class DummyUTMOS(torch.nn.Module):
    def forward(self, waveform, sample_rate):
        return torch.tensor([4.2], dtype=torch.float32)


def utmos22_strong(*args, **kwargs):
    return DummyUTMOS()
