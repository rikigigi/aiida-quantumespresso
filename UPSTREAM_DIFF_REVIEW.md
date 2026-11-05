# Review: `aiidateam/main` vs `20261105-rebase`

Date: 2026-11-05
Branch under review: `20261105-rebase` (tip `3e35f7621`), a rebase of the private branch
`20251204-davide-rebase` onto `aiidateam/main` (`7568266b3`, merge base `63fee4db`).
Diff reviewed: `git diff aiidateam/main...20261105-rebase` (code diff 11 files, +460/−30; the
remaining ~146k lines are new QE-output test fixtures under `tests/parsers/fixtures/neb/`).

## 1. Commits on the branch (13)

```
3e35f7621 docs: add internal migration guide 20251204-davide-rebase -> 20261105-rebase
65e9844f0 Apply ruff lint fixes and formatting to files touched by the rebased commits
9993d036b Fixed Relax get_builder_from_protocol (cell_dofree no longer overrides user value)
9b35a70c3 Improvements for MD (electronic convergence handling, nstep reduction on restart)
581c616aa Guard missing output_structure in ERROR_IONIC_INTERRUPTED_PARTIAL_TRAJECTORY handler
bbba067e8 fixed global class variable in NebCalculation (+ num_of_images mandatory, NEB input tests)
b8b7abd6f fix neb parser for **** (Fortran-format robustness)
10db22a40 spin-polarization validation in BasePwCpInputGenerator
0843eb1e1 scheduler exit code reported before XML parse error in NebParser
f71528000 NEB parser robustness with image parallelization; parallelization input handling
6e60169e52 ✨ NEB parallelization support (-nimage), exit codes 481-484, workchain 320
41fc2ff34 NEB parser: interrupted in initial stages, exit code 340
```

Dropped during the rebase (already upstream / empty / superseded / proven redundant):
patch-identical `7b505a23d`, `1b7a06331`, `3b6b7c41a`, `02944a028`, `b43c51c8a`, `2f0cb3219`;
content-identical `9624c77cd` (= upstream `2d26c649f`); `71ceab6e0` (xsd = upstream `b37f45a6c`,
commit became empty); superseded `7c0960cfd`/`db39a3d5b` (= `d3df9add7`/`7a6c1204b`); empty
`63d1c13f0`, `a75685b17`; merge `4b04bd020`; pbc workaround `c68e6b225`/`50b04af2c` (dropped
after an empirical test: 45 NEB/kpoints tests on py3.14 gave identical outcomes with and
without them; upstream `create_kpoints_from_distance` already respects `structure.pbc`).
The `14b18c93b` "TO DISCARD" REBASE_20261104.md commit was excluded by construction.

## 2. What changed, file by file

### `src/aiida_quantumespresso/calculations/neb.py` (+74)
- New optional `parallelization` input (`orm.Dict`) on `NebCalculation`; validator rebinds
  `BasePwCpInputGenerator.validate_parallelization` to `cls`; class attrs
  `_ENABLED_PARALLELIZATION_FLAGS = ('npool', 'nband', 'ntg', 'ndiag', 'nimage')` and
  `_PARALLELIZATION_FLAG_ALIASES`.
- New exit codes: `340 ERROR_NEB_INTERRUPTED_WITHOUT_PARTIAL_TRAJECTORY` and
  `481–484` (`ERROR_NPOOLS_TOO_HIGH`, `ERROR_NIMAGE_HIGHER_THAN_NPROC`,
  `ERROR_NIMAGE_HIGHER_THAN_IMAGES`, `ERROR_NIMAGE_NOT_DIVISOR_OF_NPROC`).
- `validate_inputs`: the `cls.inputs = AttributeDict(value)` **class-variable bug is removed**
  (upstream still has it — the one deliberate upstream-code deletion in this diff);
  `num_of_images` under `PATH` is now mandatory; `nimage` is validated against
  `num_of_images` minus the fixed endpoints (`first_last_opt` aware).
- `prepare_for_submission`: parallelization flags merged into `cmdline_params` via upstream's
  `BasePwCpInputGenerator._add_parallelization_flags_to_cmdline_params(self, ...)` directly —
  the branch's lambda-object hack is gone and the method already tolerates a missing input.
- `_generate_input_files`: climbing-image range check uses the mandatory `number_of_images`.

### `src/aiida_quantumespresso/parsers/neb.py` (+25)
- `parse_raw_output_neb` wrapped in try/except → `ERROR_OUTPUT_STDOUT_READ` with the exception
  logged; parsed `errors` short-circuit to the matching exit code (parallelization failures).
- Missing `num_of_images` in the raw output → exit `340` (interrupted before first NEB step,
  no partial trajectory).
- Before exiting with `ERROR_OUTPUT_XML_PARSE` on an empty parsed structure, the scheduler's
  own exit status is returned if present (`from aiida.engine import ExitCode` added).
- Missing per-image `PW.out` now logs which file was missing (`except OSError`).

### `src/aiida_quantumespresso/parsers/parse_raw/neb.py` (+62)
- New `detect_important_message()` mapping the four QE parallelization error strings to
  exit-code names; `parsed_data['errors']` added and scanned line-by-line.
- `num_of_images` access made safe (`None` instead of `KeyError`).
- `float()` parsing of `initial path length`, `path length`, `inter-image distance` and both
  activation energies wrapped in try/except (Fortran `****` robustness) → `None` + warning
  instead of a crash.

### `src/aiida_quantumespresso/workflows/neb/base.py` (+41)
- Workchain exit code `320 ERROR_PARALLELIZATION_SETTINGS`.
- Process handlers: priority 400 for exit 340 (abort — nothing to restart from; suggests more
  walltime), priority 390 mapping exits 481–484 → 320.
- The pbc workaround (`structure.set_pbc(trajectory.get_array('pbc'))`) is absent — dropped as
  redundant (see section 1).

### `src/aiida_quantumespresso/calculations/__init__.py` (+31)
- Spin-polarization validation in `BasePwCpInputGenerator.validate_inputs`: `nspin=2` requires
  `starting_magnetization` or `tot_magnetization`; `occupations='fixed'` additionally requires
  `tot_magnetization`; `noncolin` conflicts with `nspin=2`; `tot_magnetization` requires
  `nspin=2`. Placed **after** the port-exclusion check, which now also covers the `parameters`
  port — this keeps upstream's `test_pw_validate_inputs_parameters_excluded` passing (it
  regressed during the rebase until this ordering was fixed).

### `src/aiida_quantumespresso/parsers/pw.py` (+4)
- `validate_dynamics`: for `md`/`vc-md`, electronic non-convergence now returns
  `ERROR_IONIC_CYCLE_ELECTRONIC_CONVERGENCE_NOT_REACHED` instead of falling through.

### `src/aiida_quantumespresso/workflows/pw/base.py` (+8)
- MD out-of-walltime restart reduces `CONTROL.nstep` by the steps already completed.
- The interrupted-partial-trajectory handler only sets `ctx.inputs.structure` when
  `output_structure` actually exists.

### `src/aiida_quantumespresso/workflows/pw/relax.py` (8 lines)
- `cell_dofree` assigned via `setdefault` in all three relax-type branches (a user-provided
  value is no longer overridden); stray backtick fixed in an error message.

### Tests
- `tests/calculations/test_neb.py`: upstream's validation tests kept; the branch's
  `generate_inputs_neb` fixture and `test_neb_default[3,5]` input-generation regression tests
  re-added **images-only** (the `first_structure`/`last_structure` parametrization and its six
  fixtures removed; `True_*` fixtures renamed to `test_neb_default_{3,5}_*`).
- `tests/parsers/test_neb.py` (+95) and fixtures: new failure-mode tests — empty stdout,
  first-step interrupted, Fortran-format path length, and the four parallelization failures.

### `MIGRATION_20261105.md` (+88, repo root)
- Internal migration guide from `20251204-davide-rebase` to `20261105-rebase`.

## 3. Verification (tests)

Fresh venv per Python version; aiida-core 2.9.4 (latest 2.x), pytest 8.4.2,
pytest-regressions ~2.8, pgtest ~1.3; plugin installed editable `--no-deps` per side;
`AIIDA_WARN_v3=1 pytest -q tests --junitxml=...`. Local postgres/rabbitmq were not needed
(the aiida pytest fixtures use a temporary sqlite profile with no broker and a temp
`AIIDA_PATH`).

| Side | py3.13 | py3.14 | py3.15 (bonus) |
|---|---|---|---|
| `aiidateam/main` | 611P / 48F / 2S | 611 / 48 / 2 | 466 / 193 / 2 |
| old branch (informational) | 449 / 83 / 2 | — | — |
| `20261105-rebase` | 618 / 50 / 2 | 618 / 50 / 2 | 472 / 196 / 2 |

**Acceptance bar met on all three versions: zero tests fail on `20261105-rebase` that pass on
`aiidateam/main`.** Versus the old branch on py3.13, the rebase fixes 33 previously failing
tests and breaks none. Notes:
- The 48 main-side failures on 3.13/3.14 are pre-existing upstream/environmental (e.g.
  `tests/cli/test_commands.py` FileNotFoundError), identical on both sides.
- py3.15 stack not fully ready: `elementpath`/xmlschema cannot read Python 3.15's Unicode 17.0
  database → mass failures on both sides; still zero regressions vs main.
- Branch-only failing tests (pre-existing on the old branch, not rebase regressions):
  `test_failed_empty_stdout` (gets 340, expects 310), `test_failed_first_step_interrupted`
  (gets 321, expects 340); on 3.15 additionally `test_fortran_format_in_path_length`
  (elementpath/Unicode issue).
- Ruff 0.13.2 (upstream's pinned pre-commit rev) `check` passes on the whole repo; `format
  --check` flags only the same 5 files that pristine `aiidateam/main` also flags.

## 4. Review findings

### Standards axis (9 findings: 2 hard, 7 judgement calls)
Documented standards: `.pre-commit-config.yaml` (ruff-check `--fix`, ruff-format v0.13.2) and
`[tool.ruff]` in `pyproject.toml`; no CONTRIBUTING/CODING_STANDARDS in the repo. Ruff passes, so
no tooling-enforced violations.
- **Hard:** stale `# pylint: disable=too-many-return-statements` pragma in
  `calculations/__init__.py` (pylint no longer in the pre-commit config); missing
  `# noqa: SLF001` on `BasePwCpInputGenerator._add_parallelization_flags_to_cmdline_params(self, ...)`
  in `calculations/neb.py` while every other private access in the file carries the noqa.
- **Judgement calls:** dead regex branch in `detect_important_message` (Duplicated Code /
  Speculative Generality); four identical try/except-float blocks in `parse_raw/neb.py`
  (Duplicated Code — a `_parse_float_or_none` helper would gather them); two near-identical
  process handlers in `workflows/neb/base.py`; the `__func__`-rebinding validator lambda
  (Message Chain / Feature Envy); spin-validation if-cascade could be one helper (Repeated
  Switches); debug leftovers in `test_fortran_format_in_path_length` (commented
  `pdb.set_trace()`, three `print`s); misleading `first_structure` local name in the test
  fixture (used only for `get_kind_names()`); import-order nit in `calculations/neb.py`.

### Spec axis (5 findings: 0 missing, 3 scope creep, 2 suspect)
- All ten original commit intents are present. Confirmed **absent** from the diff: any
  resurrection of `first_structure`/`last_structure`, `ADDITIONAL_RETRIEVE_LIST`,
  `_lowercase_dict`, the old two-arg `parse_xml` call, and the `cls.inputs =` class-level
  assignment. Confirmed **present**: the `cls.inputs` fix.
- Scope creep: the `****` float-guard extends beyond "initial path length" to activation
  energies, path length and inter-image distance; cosmetic backtick fix in `relax.py`; the
  debug leftovers in the new test.
- Suspect implementations: (1) the MD `nstep` reduction reads
  `output_parameters.get('scf_iterations', 1)`, but the parsed key is nested
  (`total_number_of_scf_iterations`), so `final_step` is always 0 and `nstep` is never
  actually reduced — a latent bug inherited verbatim from the original branch commit
  (`6aa85e911`); (2) `'md' in ...get('calculation', None)` raises `TypeError` if `calculation`
  is absent (low risk, `CONTROL.calculation` is effectively required).

## 5. Rebase mechanics (for the record)

Performed in a scratch worktree on `20261105-rebase` cut from `9624c77cd` (so the REBASE-doc
commit is excluded by construction); interactive todo drops as listed in section 1; six
conflicts resolved (the doc's five plus one unexpected, `4c7c51bf3`, caused by the cleanup of
the lambda hack), always upstream-base + functional-delta, each commit left consistent.
Semantic traps explicitly avoided: no resurrected removed APIs, correct `parse_xml(xml_file)`
call, `ExitCode` import restored, `prepare_for_submission` no longer references
`first_structure`. Full log: session scratchpad `rebase-log.md`; junit XMLs: `/tmp/reports/`.
