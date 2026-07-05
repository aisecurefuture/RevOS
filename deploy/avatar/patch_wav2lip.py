"""Patch Wav2Lip's inference.py for the modern PyTorch stack (Phase 3 M3).

Applies the three fixes validated during the CPU feasibility spike:

1. PyTorch >= 2.6 defaults torch.load to weights_only=True; these older
   checkpoints need weights_only=False.
2. The community ``*-SD-GAN.pt`` mirror is a TorchScript archive, which routes
   through torch.jit.load — that only accepts a string/torch.device
   map_location, not the lambda the stock code passes. Use "cpu".
3. That same TorchScript checkpoint is a ready-to-use ScriptModule, not a
   ``{"state_dict": ...}`` dict, so load_model must use it directly when it
   isn't a dict.

Idempotent: safe to run more than once. Usage: python patch_wav2lip.py <path/to/inference.py>
"""

from __future__ import annotations

import sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else "inference.py")
src = path.read_text()

# (1) + (2): the CPU branch's torch.load call.
if "map_location=lambda storage, loc: storage)" in src:
    src = src.replace(
        "map_location=lambda storage, loc: storage)",
        'map_location="cpu", weights_only=False)',
    )
# (1): the CUDA branch.
if "checkpoint = torch.load(checkpoint_path)\n" in src:
    src = src.replace(
        "checkpoint = torch.load(checkpoint_path)\n",
        "checkpoint = torch.load(checkpoint_path, weights_only=False)\n",
    )

# (3): load_model handles a scripted module (not a state_dict dict).
old_block = '''def load_model(path):
	model = Wav2Lip()
	print("Load checkpoint from: {}".format(path))
	checkpoint = _load(path)
	s = checkpoint["state_dict"]
	new_s = {}
	for k, v in s.items():
		new_s[k.replace('module.', '')] = v
	model.load_state_dict(new_s)

	model = model.to(device)
	return model.eval()'''

new_block = '''def load_model(path):
	print("Load checkpoint from: {}".format(path))
	checkpoint = _load(path)
	if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
		model = Wav2Lip()
		s = checkpoint["state_dict"]
		new_s = {}
		for k, v in s.items():
			new_s[k.replace('module.', '')] = v
		model.load_state_dict(new_s)
	else:
		# TorchScript-exported module — ready to use directly.
		model = checkpoint

	model = model.to(device)
	return model.eval()'''

if old_block in src:
    src = src.replace(old_block, new_block)
elif "TorchScript-exported module" not in src:
    print("WARNING: load_model block not found and not already patched — "
          "the repo layout may have changed.", file=sys.stderr)

path.write_text(src)
print(f"Patched {path}")
