# Analysis scripts

Scripts behind the figures of the industrial report and of the technical note on the OPTI
process. They rebuild, without Django, the problem that SPARC builds for a week (`weeks.py`) from
the CSV files in `data/`, and solve it with the optimisers of `backend/OptimizerApp`.

Run them from the repository root with the backend dependencies installed
(`pip install -r backend/requirements.txt pyyaml`):

| Script | What it produces | Time |
| --- | --- | --- |
| `benchmark.py [results.json]` | every full week, both generation scenarios: savings, seasons, solve times, independent overlap check of every schedule | ~25 min |
| `strategies.py [results.json]` | savings when last week's or a seasonal plan is reused (needs `benchmark.py` output) | ~2 min |
| `sensitivity.py` | savings against the width of the movement window | ~15 min |
| `july_week.py` | the week of 15 July 2024: LP relaxation, model size, one-run cost curves, legacy heuristic | seconds |
| `toy_examples.py` | the small examples B--E of the technical note | seconds |
| `edge_case.py` | the end-of-week case that used to lose energy and crash, now fixed (Django shell, throw-away database) | seconds |
