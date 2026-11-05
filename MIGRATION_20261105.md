# Migration guide: `20251204-davide-rebase` → `20261105-rebase`

Internal reference. The branch `20261105-rebase` is `20251204-davide-rebase` rebased onto
`aiidateam/main` (merge base `63fee4db`). The preliminary-analysis commit that added
`REBASE_20261104.md` (`14b18c93b`) was intentionally **not** carried over.

## TL;DR for users of the old branch

- Rebase your local work onto `20261105-rebase` instead of `20251204-davide-rebase`.
- `NebCalculation` no longer accepts `first_structure`/`last_structure` (removed upstream in
  `c4da42ac8`): pass the full `images` trajectory. The branch's tests and fixtures that used
  `first_structure`/`last_structure` were removed with them.
- The `ADDITIONAL_RETRIEVE_LIST` setting is gone (removed upstream in `23072e17b`); retrieve
  lists are fixed per calculation class.
- `NebCalculation` gained a `parallelization` input (flags `npool`, `nband`, `ntg`, `ndiag`,
  `nimage`), and `num_of_images` is now **mandatory** in the `PATH` namelist. Invalid
  parallelization fails with new exit codes (see below).
- New exit codes: calculation `340` `ERROR_NEB_INTERRUPTED_WITHOUT_PARTIAL_TRAJECTORY`,
  `481`–`484` (parallelization errors), work chain `320` `ERROR_PARALLELIZATION_SETTINGS`.
- The pbc workaround in `NebBaseWorkChain` was dropped: upstream
  `create_kpoints_from_distance` respects `structure.pbc` (and aiida-core ≥ 2.8 supports `pbc`
  in `TrajectoryData.set_trajectory`), verified by tests — see "pbc workaround" below.
- Requires `aiida-core ~=2.8` (latest 2.x, e.g. 2.9.4, tested) and Python ≥ 3.10.

## What happened to the old branch commits

### Dropped — already upstream (no action needed)

| Old commit | Why dropped | Upstream counterpart |
|---|---|---|
| `7b505a23d`, `1b7a06331`, `3b6b7c41a`, `02944a028`, `b43c51c8a`, `2f0cb3219` | patch-identical, git auto-skipped | `5c14b46b3`, `b0b63c1c2`, `20ac738c4`, `eff30d2e3`, `3c2ba3054`, `7568266b3` |
| `9624c77cd` (pbc to `set_trajectory`) | content-identical, dropped by hand | `2d26c649f` |
| `71ceab6e0` (`qes_260128.xsd`) | byte-identical file already upstream; commit became empty and was skipped | `b37f45a6c` (superset, incl. fixtures) |
| `7c0960cfd` (cutoff-less pseudo families) | superseded by the more general upstream implementation | `d3df9add7` (#1281) |
| `db39a3d5b` (`z_valence` only for spin) | superseded | `7a6c1204b` |
| `63d1c13f0`, `a75685b17` | empty commits | — |
| `4b04bd020` | merge commit, linearized away | — |
| `c68e6b225`, `50b04af2c` (pbc workaround) | dropped after empirical verification: identical test results without them; upstream `create_kpoints_from_distance` respects `pbc` | `9fa84b7f6`, `5f71a0296`, `2d26c649f` |

### Kept — replayed on `20261105-rebase`

| Old commit | New commit | Feature |
|---|---|---|
| `82d3b121d` | `41fc2ff34` | NEB parser: interrupted initial stages, exit code 340 |
| `1cc56983a` | `e60169e52` | NEB `parallelization` input incl. `nimage`, exit codes 481–484, workchain 320 |
| `4c7c51bf3` | `f71528000` | parallelization robustness (merged into upstream's `parallelization` handling) |
| `9f9e1b02d` | `0843eb1e1` | scheduler exit code reported before XML parse error in `NebParser` |
| `d1d3bfe5d` | `b8b7abd6f` | NEB parser robustness for `****` / Fortran-format lines |
| `62becd3a2` | `bbba067e8` | `cls.inputs` class-variable fix; `num_of_images` mandatory; NEB input-generation tests (images-only) |
| `41fc5003a` | `581c616aa` | guard missing `output_structure` in partial-trajectory handler |
| `6aa85e911` | `9b35a70c3` | MD: electronic convergence handling, nstep reduction on restart |
| `34357e0d7` | `9993d036b` | `PwRelaxWorkChain`: `cell_dofree` no longer overrides user value |
| `f37ddc5b9` | `10db22a40` | spin-polarization validation in `BasePwCpInputGenerator` (re-ordered after upstream's port-exclusion check) |

Plus one commit `65e9844f0` applying ruff lint/format to the files touched by the rebased
commits (upstream now uses Ruff; the old yapf/isort/pylint pre-commit config is gone).

## Upstream breaking changes you inherit (since the merge base)

- `aiida-core` lower bound `~=2.8`; Python ≥ 3.10; pytest `~=8.4` for tests.
- `NebCalculation`: `first_structure`/`last_structure` inputs removed (`c4da42ac8`) — use `images`.
- `ADDITIONAL_RETRIEVE_LIST` setting removed (`23072e17b`).
- Parser internals: `parse_xml(xml_file)` signature/location changed (`661cda4cd`);
  `_lowercase_dict` removed from `calculations/__init__.py`.
- `parameters` input enforces UPPERCASE namelist keys (`10e10f6c1`).
- `PpCalculation`: `keep_plot_file` removed; `PwRelaxWorkChain`: `volume_convergence` removed
  (`a31934eda`); `get_starting_magnetization` removed from protocol utils (`673a970f2`).
- Whole-repo Ruff reformatting (`cb8a5445a`, `474123e23`) — expect textual diffs everywhere.

## Testing

Full `pytest tests` runs (aiida-core 2.9.4, pytest 8.4.2, `AIIDA_WARN_v3=1`; fresh venv per Python version):

| Side | Python 3.13 | Python 3.14 | Python 3.15 (bonus) |
|---|---|---|---|
| `aiidateam/main` | 611 passed / 48 failed / 2 skipped | 611 / 48 / 2 | 466 / 193 / 2 |
| `20251204-davide-rebase` (old tip, informational) | 449 / 83 / 2 | — | — |
| `20261105-rebase` | 618 / 50 / 2 | 618 / 50 / 2 | 472 / 196 / 2 |

Acceptance bar — met on all three Python versions: **no test that passes on `aiidateam/main`
fails on `20261105-rebase`** (zero regressions in the junit comparison). The rebased branch has
9 branch-only tests; of these, 2 fail (`test_failed_empty_stdout`, `test_failed_first_step_interrupted`
on 3.13/3.14; plus `test_fortran_format_in_path_length` on 3.15) — all fail identically on the old
branch / are environment-caused, i.e. pre-existing, not rebase regressions. Versus the old branch
on 3.13, the rebased branch fixes 33 previously failing tests and introduces none.
The 3.15 failures on both sides are a stack issue (`elementpath`/xmlschema cannot read Python
3.15's Unicode 17.0 database), not a code issue.
Raw junit XML reports and the full comparison are kept outside the repo (session scratchpad).
