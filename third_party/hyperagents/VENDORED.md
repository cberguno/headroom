# Vendored: HyperAgents

This directory is a vendored copy of the [HyperAgents](https://github.com/facebookresearch/HyperAgents)
research codebase from Meta FAIR, vendored at upstream commit
`59a68f672dfb92c74aeb7e61535d776fb36e172d` on 2026-09-22.

## License — read before using or modifying this code

Everything under this directory is licensed under
**CC BY-NC-SA 4.0 (Attribution-NonCommercial-ShareAlike)**, per the upstream
`LICENSE.md` in this same directory. This is **different from, and
incompatible with, headroom's own Apache-2.0 license**:

- **Non-commercial only.** This code may not be used commercially.
- **Share-alike.** Any adaptation must be redistributed under the same
  CC BY-NC-SA 4.0 terms.

Because of this, code in this directory:

- Is **not** part of the distributed `headroom-ai` package (PyPI/npm). It
  is not imported by, built into, or shipped with any headroom package
  artifact.
- Must **not** be imported from headroom's own source (`headroom/`,
  `crates/`, `sdk/`) or copied into it.
- Is kept here purely for reference and research purposes — to study the
  HyperAgents self-referential/self-improving agent architecture described
  in the accompanying paper.

## Why it's here

HyperAgents (Zhang, Zhao, Yang, Foerster, Clune, Jiang, Devlin, Shavrina —
Meta FAIR / Vector Institute / UBC / Edinburgh / NYU, March 2026) introduces
self-referential agents that unify a task agent and a meta agent into a
single editable program, extending the Darwin Gödel Machine with
metacognitive self-modification. It's kept in this repo as reference
material.

- Paper: https://arxiv.org/abs/2603.19461
- Blog: https://ai.meta.com/research/publications/hyperagents/
- Upstream source: https://github.com/facebookresearch/HyperAgents
