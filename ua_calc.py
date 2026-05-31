#!/usr/bin/env python3
"""
Universal Architect Calculator - Recursive Node Resource Balancing Engine
Modern rewrite (v0.3)

Originally by Paul Spooner (public domain dedication 2014).
Cleaned up, accelerated, and modernized.

This solves hierarchical "design" problems where:
- Nodes are components/assemblies with production (+) or consumption (-) of resources.
- Some nodes are "solve targets" (net consumers). The solver automatically adds
  supplier sub-nodes until all resources reach non-negative net balance.
- Nodes may contain other nodes (hierarchical / composite), which are flattened.

Usage:
    python ua_calc.py [specfile] [--margin 1.25] [--max-iterations 200] [--quiet]
    python ua_calc.py spec.txt --minimize "volume 1 crew 8 officer 25"
    python ua_calc.py spec.txt --minimize CostModel

No external dependencies. Pure Python 3.6+.

Cost minimization (optional):
    Use --minimize to make the solver prefer lower-cost designs.
    You can reference a node in the spec (its net becomes the cost weights),
    or provide explicit weights on the command line.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from time import perf_counter
from typing import Dict, List, Set, Tuple


# ----------------------------- Data Model -----------------------------


@dataclass
class Node:
    name: str
    local: Dict[str, Fraction] = field(default_factory=dict)
    net: Dict[str, Fraction] = field(default_factory=dict)
    is_solve_target: bool = False
    contains_nodes: bool = False


# ----------------------------- Parsing -----------------------------


def parse_spec(path: Path) -> Tuple[Dict[str, Node], str, str]:
    """
    Parse the classic Universal Architect specification format.

    The first non-empty line's leading token becomes the COMMENT symbol.
    The first line that does not start with the comment symbol becomes the
    NODESTART symbol (usually '*').

    Returns: (nodes dict, comment_symbol, node_start_symbol)
    """
    text = path.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines()]

    nodes: Dict[str, Node] = {}
    comment = ""
    node_start = ""
    current_name = ""
    current_local: Dict[str, Fraction] = {}

    def finish_node() -> None:
        nonlocal current_name, current_local
        if not current_name:
            return
        node = Node(name=current_name, local=current_local)
        nodes[current_name] = node
        current_name = ""
        current_local = {}

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        if not comment:
            # First non-empty line defines the comment symbol (usually '#')
            comment = line
            continue

        if line.startswith(comment):
            continue

        if not node_start:
            # First non-comment line defines the node-start symbol (usually '*')
            node_start = line
            continue

        if line.startswith(node_start):
            finish_node()
            current_name = line[len(node_start):].strip()
            current_local = {}
            continue

        # resource or sub-node line: "name value" or "name with spaces -3.2"
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            qty = Fraction(parts[-1])
        except Exception:
            continue
        name = " ".join(parts[:-1])
        current_local[name] = qty

    finish_node()

    if not nodes:
        raise ValueError(f"No nodes found in {path}")

    return nodes, comment, node_start


# ----------------------------- Net Calculation (flattening) -----------------------------


def compute_all_nets(nodes: Dict[str, Node]) -> List[str]:
    """
    Compute the flattened .net vector for every node by expanding contained nodes.

    Simple, robust approach for small graphs: repeated full sweeps until fixed point.
    Returns the list of nested/composite node names.
    """
    # Identify containment + classify solve targets (exact original rules)
    nested: List[str] = []
    solve_targets: List[str] = []
    static: List[str] = []

    for name, node in nodes.items():
        has_nested = any(item in nodes for item in node.local)
        node.contains_nodes = has_nested

        # Original rule: a node is solved if *all* its direct values are <= 0
        # and it does not contain a "don't solve this 0" marker.
        all_non_positive = bool(node.local) and all(v <= 0 for v in node.local.values())
        has_dont_solve = any(
            v == 0 and ("don't solve" in k.lower() or "dont solve" in k.lower())
            for k, v in node.local.items()
        )
        node.is_solve_target = all_non_positive and not has_dont_solve

        if node.is_solve_target:
            solve_targets.append(name)
        elif has_nested:
            nested.append(name)
        else:
            static.append(name)

    # Solve targets are always treated as containers (they will receive additions)
    for name in solve_targets:
        nodes[name].contains_nodes = True
        if name not in nested:
            nested.append(name)

    # CRITICAL: invert negative child-node quantities in the stored Local for solve targets.
    # This is what the original UA_Calc does before any net calculation.
    # Raw resources (non-nodes) keep their sign (they are the initial demands).
    for name in solve_targets:
        node = nodes[name]
        for item in list(node.local.keys()):
            if item in nodes:
                node.local[item] = abs(node.local[item])

    # Seed static nodes
    for name in static:
        nodes[name].net = dict(nodes[name].local)

    # For nested nodes, iterate until nets stabilize (tiny graph => fast)
    changed = True
    guard = 0
    max_guard = len(nodes) * 3 + 10
    while changed and guard < max_guard:
        guard += 1
        changed = False
        for name in nested:
            node = nodes[name]
            new_net: Dict[str, Fraction] = defaultdict(Fraction)
            for item, qty in node.local.items():
                if item in nodes:
                    for res, val in nodes[item].net.items():
                        new_net[res] += val * qty
                else:
                    new_net[item] += qty
            new_net_d = dict(new_net)
            if new_net_d != node.net:
                node.net = new_net_d
                changed = True

    if guard >= max_guard:
        print("WARNING: net computation hit iteration guard (possible cycle?)")

    return nested


def build_productions(nodes: Dict[str, Node], exclude_nodes: Set[str] | None = None) -> Dict[str, List[Tuple[Fraction, str]]]:
    """
    For each resource, produce a list of (positive_net_amount, node_name)
    sorted descending by amount. Solve targets themselves are excluded
    (they are not suppliers you can "add more of" to other designs).

    If exclude_nodes is provided, those node names are also removed from
    the supplier list (useful for excluding cost model nodes).
    """
    solve_names = {nm for nm, nd in nodes.items() if nd.is_solve_target}
    exclude = exclude_nodes or set()
    prods: Dict[str, List[Tuple[Fraction, str]]] = defaultdict(list)
    for name, node in nodes.items():
        if name in solve_names or name in exclude:
            continue
        for res, val in node.net.items():
            if val > 0:
                prods[res].append((val, name))
    for res in prods:
        prods[res].sort(reverse=True)  # largest producers first
    return prods


def parse_cost_expression(expr: str, nodes: Dict[str, Node]) -> Dict[str, Fraction]:
    """
    Turn a --minimize expression into a resource -> coefficient map.

    Supported forms:
      - "volume"                    -> {volume: 1}
      - "CostModel"                 -> uses nodes["CostModel"].net as weights (if it exists)
      - "volume 1 crew 8 officer 25" -> explicit pairs
    """
    expr = expr.strip()
    if not expr:
        return {}

    # If it exactly matches a node name, use that node's net as the cost vector.
    if expr in nodes:
        return dict(nodes[expr].net)  # copy

    # Otherwise parse as tokens: resource [coeff] resource [coeff] ...
    tokens = expr.split()
    cost: Dict[str, Fraction] = {}
    i = 0
    while i < len(tokens):
        res = tokens[i]
        i += 1
        coeff = Fraction(1)
        if i < len(tokens):
            try:
                coeff = Fraction(tokens[i])
                i += 1
            except Exception:
                pass  # next token is another resource
        if res:
            cost[res] = cost.get(res, Fraction(0)) + coeff
    return cost


def compute_design_cost(design: Dict[str, Fraction], nodes: Dict[str, Node],
                        cost_vector: Dict[str, Fraction]) -> Fraction:
    """Compute the scalar cost of a design given the cost coefficients."""
    total = Fraction(0)
    for item, qty in design.items():
        if qty == 0:
            continue
        if item in nodes:
            node_cost = sum(
                (cost_vector.get(res, Fraction(0)) * val)
                for res, val in nodes[item].net.items()
            )
            total += node_cost * qty
        else:
            # Direct resource in the design
            total += cost_vector.get(item, Fraction(0)) * qty
    return total


# ----------------------------- Solving -----------------------------


def solve_design(
    target_name: str,
    nodes: Dict[str, Node],
    productions: Dict[str, List[Tuple[Fraction, str]]],
    margin: Fraction = Fraction("5/4"),
    max_loops: int = 500,
    cost_vector: Dict[str, Fraction] | None = None,
) -> Tuple[Dict[str, Fraction], Dict[str, Fraction], int]:
    """
    Solve a single design goal using a faithful one-resource-at-a-time greedy strategy
    (closest to the original UA_Calc algorithm). Uses float for decision math to
    reproduce similar addition counts and behavior.
    """
    target = nodes[target_name]
    if not target.is_solve_target:
        raise ValueError(f"{target_name} is not a solve target")

    # Starting design = the (already inverted during net prep) local of the target.
    # Raw resource demands keep their negative sign.
    design: Dict[str, Fraction] = dict(target.local)

    # Fast vector contribution (net effect on every resource)
    contrib: Dict[str, Fraction] = defaultdict(Fraction)
    for item, qty in design.items():
        if item in nodes:
            for res, val in nodes[item].net.items():
                contrib[res] += val * qty
        else:
            contrib[item] += qty

    # Convert productions to float lists for decision making (matches original float math)
    prod_float: Dict[str, List[Tuple[float, str]]] = {}
    for res, lst in productions.items():
        prod_float[res] = [(float(p), n) for p, n in lst]

    m_float = float(margin)
    iterations = 0

    while iterations < max_loops:
        # Current deficits (most negative first) - use float for comparisons
        deficits = [(r, float(v)) for r, v in contrib.items() if v < 0]
        if not deficits:
            break
        deficits.sort(key=lambda t: t[1])  # most negative first

        made_progress = False

        for res, net_val in deficits:
            if res not in prod_float or not prod_float[res]:
                continue

            candidates = prod_float[res]
            if not candidates:
                continue

            # Cost-aware selection when a cost vector is provided.
            # Otherwise fall back to classic "largest producer first".
            if cost_vector:
                # Score the top few candidates by production benefit per unit cost
                scored = []
                for prod_f, node_name in candidates[:6]:  # look at top 6 largest
                    marginal_cost = Fraction(0)
                    node = nodes[node_name]
                    for r, v in node.net.items():
                        marginal_cost += cost_vector.get(r, Fraction(0)) * v
                    # benefit per unit cost (avoid div by zero / negative cost gaming)
                    if marginal_cost > 0:
                        ratio = Fraction(int(prod_f * 1000)) / marginal_cost   # scale for comparison
                    else:
                        ratio = Fraction(int(prod_f * 1000)) + 10**9  # huge bonus for free/negative cost
                    scored.append((ratio, -marginal_cost, prod_f, node_name))  # higher ratio better
                scored.sort(reverse=True)
                _, _, best_prod_f, best_node = scored[0]
            else:
                # Classic behavior: largest net producer
                best_prod_f, best_node = candidates[0]

            if best_prod_f <= 0:
                continue

            current_net_f = net_val  # negative
            # Mimic original gross/minproduction math as closely as possible.
            # In our model the "consumption" is already folded into net_val.
            # We need enough additional net production to bring this res to >= 0.
            needed_f = (-current_net_f) / best_prod_f

            # Original did: needed = 1 + CurrentNet // candidate  (integer)
            # then possibly -1 if it would exceed upper = minprod * MARGIN
            needed = int(needed_f) + 1
            trial_prod = best_prod_f * needed
            upper = (-current_net_f) * m_float
            if trial_prod > upper and needed > 1:
                needed -= 1

            if needed < 1:
                needed = 1

            # Apply addition
            n_frac = Fraction(needed)
            design[best_node] = design.get(best_node, Fraction(0)) + n_frac
            for r, v in nodes[best_node].net.items():
                contrib[r] += v * n_frac

            made_progress = True
            break  # only solve the single worst resource this micro-step (original behavior)

        if not made_progress:
            # Try the corner-case fallback from original: add 1 of the *smallest* producer
            # for the worst remaining deficit.
            res, net_val = deficits[0]
            if res in prod_float and prod_float[res]:
                tiny_prod_f, tiny_node = prod_float[res][-1]  # smallest positive
                if tiny_prod_f > 0:
                    n_frac = Fraction(1)
                    design[tiny_node] = design.get(tiny_node, Fraction(0)) + n_frac
                    for r, v in nodes[tiny_node].net.items():
                        contrib[r] += v * n_frac
                    made_progress = True

        if not made_progress:
            break

        iterations += 1

    final_design = {k: v for k, v in design.items() if v != 0}
    final_net = {k: v for k, v in contrib.items() if v != 0}

    return final_design, final_net, iterations


def reduce_design_cost(
    design: Dict[str, Fraction],
    nodes: Dict[str, Node],
    cost_vector: Dict[str, Fraction],
    max_passes: int = 8,
) -> Tuple[Dict[str, Fraction], int]:
    """
    Greedy reduction pass: try to remove expensive components while staying feasible.
    Returns (improved_design, number_of_removals).
    """
    if not cost_vector:
        return design, 0

    current_design = dict(design)
    removals = 0

    for _pass in range(max_passes):
        # Recompute current net from the design
        contrib: Dict[str, Fraction] = defaultdict(Fraction)
        for item, qty in current_design.items():
            if item in nodes:
                for res, val in nodes[item].net.items():
                    contrib[res] += val * qty
            else:
                contrib[item] += qty

        # Find candidates we can potentially remove (count > 0)
        # Score by how much cost we would save per unit removed
        removable = []
        for item, qty in current_design.items():
            if qty <= 0:
                continue
            marginal_cost = Fraction(0)
            if item in nodes:
                for res, val in nodes[item].net.items():
                    marginal_cost += cost_vector.get(res, Fraction(0)) * val
            else:
                marginal_cost = cost_vector.get(item, Fraction(0))

            if marginal_cost > 0:
                removable.append((marginal_cost, item))

        if not removable:
            break

        removable.sort(reverse=True)  # highest cost first

        progress_this_pass = False
        for _, item in removable:
            if current_design.get(item, 0) <= 0:
                continue

            # Tentatively remove one
            trial = dict(current_design)
            trial[item] -= 1
            if trial[item] <= 0:
                trial.pop(item, None)

            # Check if still feasible
            trial_contrib: Dict[str, Fraction] = defaultdict(Fraction)
            for it, q in trial.items():
                if it in nodes:
                    for r, v in nodes[it].net.items():
                        trial_contrib[r] += v * q
                else:
                    trial_contrib[it] += q

            if all(v >= 0 for v in trial_contrib.values()):
                current_design = trial
                removals += 1
                progress_this_pass = True
                break  # restart scoring after a successful removal

        if not progress_this_pass:
            break

    return current_design, removals


def compute_gross_one_level(
    design: Dict[str, Fraction], nodes: Dict[str, Node]
) -> Tuple[Dict[str, Fraction], Dict[str, Fraction]]:
    """
    Compute the one-level gross production and consumption from the direct
    children/resources listed in `design` (for the report).
    """
    gross_prod: Dict[str, Fraction] = defaultdict(Fraction)
    gross_cons: Dict[str, Fraction] = defaultdict(Fraction)

    for item, qty in design.items():
        if qty == 0:
            continue
        if item in nodes:
            # child's full net contribution at this level
            for res, val in nodes[item].net.items():
                if val > 0:
                    gross_prod[res] += val * qty
                else:
                    gross_cons[res] += val * qty
        else:
            # raw resource declared directly in the design
            if qty > 0:
                gross_prod[item] += qty
            else:
                gross_cons[item] += qty

    return dict(gross_prod), dict(gross_cons)


# ----------------------------- Output -----------------------------


def format_qty(q: Fraction) -> str:
    """Human friendly quantity. Matches original style reasonably well."""
    f = float(q)
    if abs(f) < 1e-12:
        return "0"
    # Use limited precision to avoid 0.0000000005 garbage while keeping useful digits
    s = f"{f:.12g}"
    # Tidy trailing .0 for whole numbers
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def write_solution_file(
    out_path: Path,
    target_name: str,
    design: Dict[str, Fraction],
    net: Dict[str, Fraction],
    gross_prod: Dict[str, Fraction],
    gross_cons: Dict[str, Fraction],
    iterations: int,
    comment: str,
    node_start: str,
    source_file: str,
    cost: Fraction | None = None,
    cost_terms: int = 0,
) -> None:
    lines: List[str] = []
    lines.append(comment)
    lines.append(f"{comment} generated in {iterations} iterations.")
    lines.append(node_start)
    lines.append(f"{comment} Originally calculated from {source_file}")
    lines.append(f"{node_start}{target_name}")

    # Net resources, sorted for determinism (resources with largest positive first-ish)
    for res in sorted(net.keys(), key=lambda r: (-float(net[r]), r)):
        val = net[res]
        lines.append(f"{res} {format_qty(val)}")
        gpfx = f"{comment} {res}"
        if res in gross_prod and gross_prod[res] != 0:
            lines.append(f"{gpfx} generated {format_qty(gross_prod[res])}")
        if res in gross_cons and gross_cons[res] != 0:
            lines.append(f"{gpfx} consumed {format_qty(gross_cons[res])}")

    # Local composition
    lines.append(f"{comment} All local nodes and resources are as follows:")
    for thing in sorted(design.keys()):
        val = design[thing]
        lines.append(f"{comment} {thing} {format_qty(val)}")

    lines.append(f"{comment} node results for {target_name} complete")

    if cost is not None and cost_terms > 0:
        lines.append(f"{comment} total minimized cost: {format_qty(cost)} (from {cost_terms} terms)")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ----------------------------- Main -----------------------------


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Universal Architect recursive node calculator (modern v0.3) — with optional cost minimization"
    )
    parser.add_argument(
        "specfile",
        nargs="?",
        default="Specification.txt",
        help="Input specification file (default: Specification.txt)",
    )
    parser.add_argument(
        "-m",
        "--margin",
        type=float,
        default=1.25,
        help="Overshoot margin when adding suppliers (default 1.25)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=200,
        help="Safety cap on solver loops (default 200)",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress progress messages"
    )
    parser.add_argument(
        "--outdir",
        default=".",
        help="Directory for generated <NodeName>.txt files (default: current dir)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="After solving, check that all solved nets are non-negative",
    )
    parser.add_argument(
        "--minimize",
        metavar="EXPR",
        default=None,
        help="Minimize a cost. Can be a resource name, a node name (uses its net as weights), "
             "or a simple expression like 'volume 1 crew 8 officer 25'. "
             "When a node name is given, that node is automatically excluded from being added "
             "as a supplier (prevents the cost model itself from being spammed into the design). "
             "Uses cost-aware choices + reduction pass.",
    )

    args = parser.parse_args(argv)

    spec_path = Path(args.specfile)
    if not spec_path.exists():
        print(f"ERROR: spec file not found: {spec_path}", file=sys.stderr)
        return 2

    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    margin = Fraction(args.margin).limit_denominator(1000)
    max_iter = args.max_iterations
    quiet = args.quiet

    t0 = perf_counter()

    # Parse
    nodes, comment, node_start = parse_spec(spec_path)
    if not quiet:
        print(f"Comment symbol: {comment!r}")
        print(f"Node start symbol: {node_start!r}")
        print(f"Loaded {len(nodes)} nodes from {spec_path}")

    # Compute nets (flattening)
    nested = compute_all_nets(nodes)
    if not quiet:
        print(f"  Nested/composite nodes: {len(nested)}")

    # Identify solve targets
    solve_targets = [n for n, nd in nodes.items() if nd.is_solve_target]
    if not quiet:
        print(f"  Solve targets: {solve_targets}")

    # Cost minimization (parsed after nodes exist)
    cost_vector: Dict[str, Fraction] = {}
    exclude_for_cost: Set[str] = set()
    if args.minimize:
        clean_minimize = args.minimize.strip()
        cost_vector = parse_cost_expression(clean_minimize, nodes)

        # Automatically exclude the cost model node itself from being used as a supplier.
        # This prevents the solver from spamming the definition node when it produces
        # resources that appear in the cost vector (e.g. a "Cost" node that defines volume weights).
        if clean_minimize in nodes:
            exclude_for_cost.add(clean_minimize)

        if not quiet and cost_vector:
            total_weight = sum(abs(float(v)) for v in cost_vector.values())
            print(f"  Minimizing cost with {len(cost_vector)} terms (total weight ~{total_weight:.1f})")

    # Build supplier index (with any cost-related exclusions applied)
    productions = build_productions(nodes, exclude_nodes=exclude_for_cost)

    # Solve each target independently
    total_iter = 0
    for target in solve_targets:
        design, net, iters = solve_design(
            target, nodes, productions, margin=margin, max_loops=max_iter,
            cost_vector=cost_vector
        )
        total_iter += iters

        # Optional cost reduction pass (only when --minimize was used)
        reductions = 0
        if cost_vector:
            design, reductions = reduce_design_cost(design, nodes, cost_vector)
            if reductions > 0 and not quiet:
                print(f"    Reduced cost by removing {reductions} component(s)")

        # Recompute net after possible reductions
        net = defaultdict(Fraction)
        for item, qty in design.items():
            if item in nodes:
                for res, val in nodes[item].net.items():
                    net[res] += val * qty
            else:
                net[item] += qty
        net = {k: v for k, v in net.items() if v != 0}

        gross_p, gross_c = compute_gross_one_level(design, nodes)

        out_file = out_dir / f"{target}.txt"

        final_cost = None
        if cost_vector:
            final_cost = compute_design_cost(design, nodes, cost_vector)

        write_solution_file(
            out_file,
            target,
            design,
            net,
            gross_p,
            gross_c,
            iters,
            comment,
            node_start,
            spec_path.name,
            cost=final_cost,
            cost_terms=len(cost_vector),
        )

        if not quiet:
            msg = f"  Solved {target} in {iters} iterations -> {out_file}"
            if final_cost is not None:
                msg += f"  (cost: {format_qty(final_cost)})"
            print(msg)

        if args.verify:
            bad = [r for r, v in net.items() if v < 0]
            if bad:
                print(f"    WARNING: {target} still has negative nets: {bad}")

    dt = perf_counter() - t0
    if not quiet:
        print(f"Done in {dt:.3f}s (total solver iterations across targets: {total_iter})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
