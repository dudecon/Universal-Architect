# Universal-Architect

A recursive node calculation engine for balancing hierarchical resource-based designs (originally created for spaceship/component design in the "Universal Architect" system).

## What it does

You describe **nodes** (components, modules, assemblies) that produce (+) or consume (-) named **resources** (volume, power, crew, thrust, life support, etc.). Some nodes are "solve targets" — net consumers. The solver automatically adds the minimal number of supplier nodes needed to bring every resource to a non-negative balance.

Nodes can contain other nodes (composites / hierarchical recipes). Everything is flattened automatically.

## Usage

```bash
python ua_calc.py                    # uses Specification.txt
python ua_calc.py my_design.txt
python ua_calc.py spec.txt --margin 1.1 --max-iterations 300
python ua_calc.py spec.txt --outdir output/ --quiet

# New in v0.3: cost-aware solving
python ua_calc.py spec.txt --minimize "volume 1 crew 8 officer 25"
python ua_calc.py spec.txt --minimize CostModel   # using a node defined in the spec
```

- `--margin` controls how aggressively it overshoots when covering a deficit (default 1.25). Lower = tighter but can take more iterations.
- Generated files: `<SolveTargetName>.txt` (one per solve target in the spec).

The old `UA_Calc0.2.py` is preserved for reference. The new `ua_calc.py` (v0.3) is a complete, modern, zero-dependency rewrite:

- Clean `dataclass` + `Fraction` model (no more float garbage or function-as-dict-key tricks)
- Dramatically simpler and faster inner loops (vector addition instead of repeated gross/net tree walks on every change)
- Proper CLI with argparse
- Same input format, compatible output format

## Similar projects

No widely-known public project does *exactly* this (a tiny, human-readable, hierarchical, vector-based "just make the design work" solver with this charmingly minimal spec syntax).

Closest conceptual relatives:

- **Factory / production planners** for automation games: YAFC (Yet Another Factorio Calculator), Kirk McDonald's Factorio calculator, Satisfactory Calculator, DSP solvers. These solve the same "cover a multi-dimensional demand vector using recipe vectors, integer counts" problem, usually with proper linear programming (PuLP, OR-Tools, etc.) for optimal/minimal solutions.
- **Modular ship designers** with deep math: *Children of a Dead Earth* (extremely rigorous component + constraint solver), various KSP and Cosmoteer tools, spreadsheet suites on Atomic Rockets.
- General techniques: Material Requirements Planning (MRP), bill-of-materials (BOM) solvers, and multi-dimensional greedy / ILP covering algorithms.

This UA engine is notable for its extreme simplicity and the elegant "declare everything in one text file with * and comments" UX. It was released to the public domain by Paul Spooner in 2014.

## Files in this repo

- `ua_calc.py` — the current recommended calculator
- `Specification.txt` — full documented example (and the input used to generate the samples)
- `Gunship Titania.txt`, `Bulk Freighter.txt`, `Fighter Ship.txt` — example outputs (historical)
- `UA_Calc0.2.py` — the original (public domain)
- `universal_architect_gd.txt` — partial Godot/GDScript port sketch (for a never-released game)
- `LICENSE.txt` — Paul Spooner's public-domain dedication (2014-08-05)

## License

Everything here is in the public domain per the dedication in LICENSE.txt.
