"""Static arity guard for the hosted qualification harness (native_checks.py).

Two hosted failures traced to harness code rather than application behavior:
run 35333228021 closed a refusal-message needle into ``check()`` (TypeError:
check() takes 2 positional arguments) and run 35335044988 passed a stray
positional to ``create_teaching_contract()`` (12 given, signature accepts at
most 11). Both are pure syntax-visible mistakes, so this test walks the
harness AST and verifies every call against the callee's real signature:

* bare calls to helpers defined inside native_checks.py (check, denied,
  unavailable, as_user, traced, ...) must match the helper definitions;
* ``<alias>.<fn>(...)`` attribute calls, where the alias names a
  toefl_house module, must match that module's top-level function defs;
* bare ``<alias>(...)`` calls, where the alias names a toefl_house
  function, must match that function's top-level def;
* every toefl_house import alias must resolve to a module file or a
  top-level function, so coverage cannot silently shrink.

Call sites using star-unpacking are skipped (not countable statically).
"""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tools/placement/native_checks.py"
PKG = ROOT / "apps/toefl_house" / "toefl_house"


def _arity(fn):
    """Return (min_positional, max_positional or None) for a function def."""
    a = fn.args
    positional = list(getattr(a, "posonlyargs", None) or []) + list(a.args)
    minimum = len(positional) - len(a.defaults)
    maximum = None if a.vararg else len(positional)
    return minimum, maximum


def _merge(existing, rng):
    if existing is None:
        return rng
    lo = min(existing[0], rng[0])
    hi = None if (existing[1] is None or rng[1] is None) else max(existing[1], rng[1])
    return (lo, hi)


def _pkg_dir(dotted_from):
    """Filesystem path of the package a ``from <dotted> import ...`` pulls from."""
    parts = dotted_from.split(".")[1:]  # strip the 'toefl_house' prefix
    d = PKG
    for p in parts:
        d = d / p
    return d


def _resolve(dotted_from, imported):
    """(module_file, parent_file): module_file if the import names a module,
    parent_file if it names an object defined directly in the parent module."""
    d = _pkg_dir(dotted_from)
    if (d / f"{imported}.py").exists():
        return d / f"{imported}.py", None
    if (d / imported / "__init__.py").exists():
        return d / imported / "__init__.py", None
    parent = d / "__init__.py" if dotted_from == "toefl_house" else (
        d.with_suffix(".py") if d != PKG else PKG / "__init__.py")
    if parent.exists():
        tree = ast.parse(parent.read_text(encoding="utf-8"))
        if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == imported for n in tree.body):
            return None, parent
    return None, None


def _top_level_fns(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {n.name: _arity(n) for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


class HarnessArityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(HARNESS.read_text(encoding="utf-8"))
        cls.helper_ranges = {}
        for node in ast.walk(cls.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cls.helper_ranges[node.name] = _merge(
                    cls.helper_ranges.get(node.name), _arity(node))
        # alias -> module AST (attribute calls) or alias -> fn arity (bare calls)
        cls.module_fns = {}
        cls.fn_aliases = {}
        cls.unresolved = []
        for node in ast.walk(cls.tree):
            if not isinstance(node, ast.ImportFrom) or not (node.module or "").startswith("toefl_house"):
                continue
            for al in node.names:
                local = al.asname or al.name
                mod, parent = _resolve(node.module, al.name)
                if mod is not None:
                    cls.module_fns.setdefault(local, {}).update(_top_level_fns(mod))
                elif parent is not None:
                    cls.fn_aliases[local] = _top_level_fns(parent)[al.name]
                else:
                    cls.unresolved.append(f"{node.module}.{al.name} as {local}")

    @staticmethod
    def _call_sites(tree, func_kind):
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, func_kind):
                yield node

    def _violation(self, node, name, rng):
        if any(isinstance(x, ast.Starred) for x in node.args):
            return None
        n = len(node.args)
        lo, hi = rng
        if n < lo or (hi is not None and n > hi):
            return (node.lineno, name, n, rng)
        return None

    def test_helper_calls_match_definitions(self):
        bad = []
        for node in self._call_sites(self.tree, ast.Name):
            rng = self.helper_ranges.get(node.func.id)
            if rng is None:
                continue
            v = self._violation(node, node.func.id, rng)
            if v:
                bad.append(v)
        self.assertEqual(bad, [], f"harness helper call arity violations: {bad}")

    def test_app_module_calls_match_signatures(self):
        bad = []
        for node in self._call_sites(self.tree, ast.Attribute):
            if not isinstance(node.func.value, ast.Name):
                continue
            alias = node.func.value.id
            fmap = self.module_fns.get(alias)
            if not fmap:
                continue
            rng = fmap.get(node.func.attr)
            if rng is None:
                continue
            v = self._violation(node, f"{alias}.{node.func.attr}", rng)
            if v:
                bad.append(v)
        self.assertEqual(bad, [], f"harness app-API call arity violations: {bad}")

    def test_app_function_aliases_match_signatures(self):
        bad = []
        for node in self._call_sites(self.tree, ast.Name):
            rng = self.fn_aliases.get(node.func.id)
            if rng is None:
                continue
            v = self._violation(node, node.func.id, rng)
            if v:
                bad.append(v)
        self.assertEqual(bad, [], f"harness app-function alias arity violations: {bad}")

    def test_all_toefl_house_aliases_resolve(self):
        """Guards the resolver itself: an alias that silently fails to map
        would exempt its call sites from the arity checks above."""
        self.assertEqual(self.unresolved, [],
                         f"toefl_house import aliases this test cannot resolve (add handling): {self.unresolved}")


if __name__ == "__main__":
    unittest.main()
