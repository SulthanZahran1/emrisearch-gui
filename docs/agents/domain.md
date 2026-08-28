# Domain glossary

- **EMRI** - Extreme Mass Ratio Inspiral. A stellar-mass compact object (mass ratio ~1e4-1e6) spiraling into a supermassive black hole. A key source for LISA, the space-based gravitational-wave observatory (ESA/NASA, launch ~2030s).
- **LISA** - Laser Interferometer Space Antenna. Space-based GW observatory; EMRI detection in its data is an active research problem.
- **MOJITO** - a catalog of simulated EMRI sources (`emri_c`, `emri_g`, ...). `load_mojito("emri_c")` loads one.
- **Source** - a `SourceParams` object: the injected EMRI (masses m1/m2, spin a, p0, e0, sky angles, orientation, phases, distance, ...).
- **Statistic** - the detection statistic: `f_pure` (coherent f-stat), `f_max` (time/phase-maximised), `semicoherent` (S_N over N_seg segments). The search target.
- **PARIS** - the sampler (parismc) that explores the parameter space. A `ParisRun` wraps one sampler run.
- **Run** - one `(source, statistic, T, dt, N_seg, modes, ...) -> output dir` execution. Output dir holds `sampler_state.pkl` + `manifest.json` + `sampler_flags.json` + `basic_results/`.
- **Manifest** - `manifest.json` sidecar recording source, box, statistic, T, seeds, anneal schedule, emrisearch version. The GUI's primary data source.
- **ParamSpace** - which parameters are searched and over what box. Presets: `intrinsic` (5D), `.plus_sky()` (7D), `.plus_orientation()` (9D), `.plus_phases()` (11D).
- **Stage** - a step in the staged workflow: LHS seed -> merge (coarse, wide box) -> anneal (refine, shrink covariance). Each stage's box derives from the previous stage's manifest.
- **LHS** - Latin Hypercube Sampling; the seed design a merge stage starts from.
- **Anneal** - tempering schedule (S_schedule) that sharpens the target as the run proceeds.
- **Search coordinates vs physical** - the sampler works in search coordinates (log10 m1, log10 m2, a, p0, e0, cos(qS), ...); `ParamSpace` transforms to physical.
- **Best point** - highest-statistic point found by a run (search coordinates).
- **Corner plot** - scatter of top searched points (search secondaries, NOT posterior draws).
- **Connection plot** - statistic evaluated along the line from injection to a recovered point; shows whether they sit on one peak.
- **n_sigma_to_contain** - how many sigma the injection is from the best point; run-convergence diagnostic.
- **best_per_process** - each PARIS process's own best; disagreement means multi-modal / not merged.

## Known constraints / facts from research (verified 2026-08-28)

- Upstream repo: verasha/emrisearch, created 2026-08-27, 0 stars, WIP, actively developed by Davendra (verasha). Author is a friend of the user and has been told about this GUI effort.
- Upstream is a Python library with no UI: driven via `examples/*.py` scripts and PBS cluster jobs (`qsub`), on a GPU cluster with a heavy stack (FastEMRIWaveforms, lisatools, fastlisaresponse, parismc).
- Run outputs live on a cluster under `/scratch/e1498138/...`; the library itself has no machine-specific paths.
- `load_run(dir)` reads `sampler_state.pkl` + `manifest.json`; supports legacy shapes (pickled parismc Sampler, LHS `(points, values)` tuple, LHS dict, `.npz`).
- Plotting: `plot_result(res, top_n)`, `connection(score, truth, best, space)`, `distance_to_truth`; corner plots show search secondaries, not posterior draws.
- Tests need no GPU and run in ~2 s (`python -m pytest tests -q`).
- Related: lorenzsp/EMRI-Search has a HuggingFace space with interactive visualizations (https://huggingface.co/spaces/lorenzsp/emrisearch) - proof that interactive EMRI-search UIs exist.
- The heavy deps (few, lisatools, fastlisaresponse, parismc) are deliberately NOT declared as pip dependencies upstream; the GUI must not force pip to rebuild them.

## Privacy

Nothing private in this effort. Upstream author is a named collaborator (Davendra / verasha); the GUI is a companion tool, not a fork.
