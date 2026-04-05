"""
Stage 1c — Control Flow Flattening
====================================
Rewrites every function body into a ``while True`` state-machine dispatcher,
making the logical execution order invisible to static analysis tools
like Ghidra, IDA Pro, and Binary Ninja.

How it works
------------
Given a function::

    def process(x):
        a = x + 1
        if a > 5:
            b = a * 2
        else:
            b = a + 10
        return b

The flattener assigns a random 32-bit integer state to each "block" of
statements and rewrites the body as::

    def process(x):
        _st = 0x3A1F9C4B          # entry state (random)
        _rv = None                 # return value accumulator
        while True:
            if _st == 0x3A1F9C4B:
                a = x + 1
                _st = 0x7D2E1A05 if a > 5 else 0xC4B83F11
            elif _st == 0x7D2E1A05:
                b = a * 2
                _st = 0xF0912E88   # merge state
            elif _st == 0xC4B83F11:
                b = a + 10
                _st = 0xF0912E88   # merge state
            elif _st == 0xF0912E88:
                _rv = b
                _st = 0x00000000   # terminal state
            elif _st == 0x00000000:
                return _rv

An attacker decompiling the Nuitka-compiled binary sees a loop with a chain
of integer comparisons. The original structure — the if/else, the merge
point, the return — is completely hidden. Every build produces different
state integers, so two builds of the same source look entirely different.

Limitations (by design)
------------------------
- ``for`` / ``while`` loops inside a function are *not* split across states
  (they remain as single statements inside one block). Splitting loop
  internals would break ``break``/``continue`` semantics without a far more
  complex CFG analysis. This is the correct tradeoff — the loop *body* is
  still obfuscated via string encryption and name mangling from Stages 1a/1b.
- ``try/except/finally`` blocks are kept as single statements for the same
  reason (exception tables are not portable across state splits).
- Functions with fewer than ``min_stmts`` top-level statements are skipped
  — the overhead is not worth it for trivial one-liners.
- Async functions are supported at the outer level but the state machine
  itself is synchronous — do not use on ``await``-heavy code without testing.

Usage
-----
::

    from securer.flow_flattener import FlowFlattener

    ff = FlowFlattener(seed=42)
    tree = ff.transform(source_code)
    print(ff.unparse(tree))

Full pipeline::

    from securer.string_encryptor import StringEncryptor
    from securer.name_mangler import NameMangler
    from securer.flow_flattener import FlowFlattener

    src = open('app.py').read()
    enc = StringEncryptor(seed=42)
    mg  = NameMangler(seed=42)
    ff  = FlowFlattener(seed=42)

    tree = enc.transform(src)
    tree = mg.transform_tree(tree)
    tree = ff.transform_tree(tree)
    open('app_obf.py', 'w').write(ff.unparse(tree))
"""

import ast
import random
from typing import Optional

# Sentinel state value: the while loop exits when _st reaches this.
_TERMINAL = 0x00000000

# Names injected into every flattened function.
_STATE_VAR = "_st"
_RETVAL_VAR = "_rv"


# ---------------------------------------------------------------------------
# Helpers: AST node builders
# ---------------------------------------------------------------------------

def _num(value: int) -> ast.Constant:
    return ast.Constant(value=value)


def _name_load(name: str) -> ast.Name:
    return ast.Name(id=name, ctx=ast.Load())


def _name_store(name: str) -> ast.Name:
    return ast.Name(id=name, ctx=ast.Store())


def _assign(target_name: str, value: ast.expr) -> ast.Assign:
    return ast.Assign(
        targets=[_name_store(target_name)],
        value=value,
        lineno=0, col_offset=0,
    )


def _state_assign(state: int) -> ast.Assign:
    """_st = 0xSTATE"""
    return _assign(_STATE_VAR, _num(state))


def _cond_state(test: ast.expr, true_state: int, false_state: int) -> ast.Assign:
    """
    _st = TRUE_STATE if <test> else FALSE_STATE
    """
    return _assign(
        _STATE_VAR,
        ast.IfExp(
            test=test,
            body=_num(true_state),
            orelse=_num(false_state),
        ),
    )


def _eq_check(state: int) -> ast.Compare:
    """_st == 0xSTATE"""
    return ast.Compare(
        left=_name_load(_STATE_VAR),
        ops=[ast.Eq()],
        comparators=[_num(state)],
    )


def _return_rv() -> ast.Return:
    """return _rv"""
    return ast.Return(value=_name_load(_RETVAL_VAR))


# ---------------------------------------------------------------------------
# Block: a group of statements that execute together as one state
# ---------------------------------------------------------------------------

class _Block:
    """
    Represents one state in the state machine.

    Attributes
    ----------
    state   : The random integer ID for this block.
    stmts   : The original statements that run in this state.
    next_state : The state to transition to after stmts complete.
                 None means this block sets its own transition
                 (e.g. an if/else that goes to two different states).
    is_terminal : If True this block emits ``return _rv``.
    """

    def __init__(self, state: int):
        self.state = state
        self.stmts: list[ast.stmt] = []
        self.next_state: Optional[int] = None
        self.is_terminal: bool = False
        self.branch_test: Optional[ast.expr] = None   # if-else branch test
        self.branch_true: Optional[int] = None
        self.branch_false: Optional[int] = None


# ---------------------------------------------------------------------------
# CFG builder: converts a flat statement list into a list of _Blocks
# ---------------------------------------------------------------------------

class _CFGBuilder:
    """
    Splits a function body (list of ast.stmt) into a sequence of _Blocks
    that can be rendered as a while/dispatch state machine.

    Splitting rules
    ---------------
    - Each top-level statement that is NOT an ``ast.If`` becomes its own
      block (or is appended to the current block if it is a simple stmt).
    - An ``ast.If`` node is split into:
        * A branch block (sets _st conditionally)
        * A true-branch block (body statements + jump to merge)
        * A false-branch block (orelse statements + jump to merge)
        * A merge block (continues after the if/else)
    - ``ast.Return`` nodes are converted into
        ``_rv = <value>; _st = TERMINAL`` plus a terminal block.
    - Statements that contain loops or try/except are treated as atomic
      (not split internally).
    """

    def __init__(self, rng: random.Random):
        self._rng = rng
        self._blocks: list[_Block] = []

    def _new_state(self) -> int:
        """Generate a unique non-zero, non-terminal 32-bit state id."""
        used = {b.state for b in self._blocks} | {_TERMINAL}
        while True:
            s = self._rng.randint(0x10000000, 0xFFFFFFFF)
            if s not in used:
                return s

    def _new_block(self) -> _Block:
        b = _Block(self._new_state())
        self._blocks.append(b)
        return b

    def build(self, stmts: list[ast.stmt]) -> list[_Block]:
        """
        Convert *stmts* into a sequence of _Blocks.
        Returns the list of blocks in execution order.
        """
        self._blocks = []
        current = self._new_block()  # entry block
        entry_state = current.state

        for stmt in stmts:
            if isinstance(stmt, ast.Return):
                # Flush current block, add return capture
                ret_val = stmt.value if stmt.value is not None else ast.Constant(value=None)
                current.stmts.append(_assign(_RETVAL_VAR, ret_val))
                terminal = self._new_block()
                terminal.is_terminal = True
                current.next_state = terminal.state
                # Start a new unreachable block for any stmts after return
                current = self._new_block()

            elif isinstance(stmt, ast.If):
                # Create true/false/merge blocks
                true_block = self._new_block()
                false_block = self._new_block()
                merge_block = self._new_block()

                # Current block becomes the branch dispatcher
                current.branch_test = stmt.test
                current.branch_true = true_block.state
                current.branch_false = false_block.state

                # Populate true branch
                true_current = true_block
                for s in stmt.body:
                    if isinstance(s, ast.Return):
                        ret_val = s.value if s.value is not None else ast.Constant(value=None)
                        true_current.stmts.append(_assign(_RETVAL_VAR, ret_val))
                        term = self._new_block()
                        term.is_terminal = True
                        true_current.next_state = term.state
                        true_current = self._new_block()
                    else:
                        true_current.stmts.append(s)
                if true_current.next_state is None and not true_current.is_terminal:
                    true_current.next_state = merge_block.state

                # Populate false branch
                false_current = false_block
                for s in stmt.orelse:
                    if isinstance(s, ast.Return):
                        ret_val = s.value if s.value is not None else ast.Constant(value=None)
                        false_current.stmts.append(_assign(_RETVAL_VAR, ret_val))
                        term = self._new_block()
                        term.is_terminal = True
                        false_current.next_state = term.state
                        false_current = self._new_block()
                    else:
                        false_current.stmts.append(s)
                if false_current.next_state is None and not false_current.is_terminal:
                    false_current.next_state = merge_block.state

                current = merge_block

            else:
                current.stmts.append(stmt)

        # Final block: if it has stmts but no return, add implicit None return
        if not current.is_terminal:
            if not any(b.is_terminal for b in self._blocks):
                # Function has no return — add implicit return None
                current.stmts.append(_assign(_RETVAL_VAR, ast.Constant(value=None)))
            terminal = self._new_block()
            terminal.is_terminal = True
            current.next_state = terminal.state

        return self._blocks


# ---------------------------------------------------------------------------
# Renderer: converts _Blocks into the while/dispatch AST
# ---------------------------------------------------------------------------

class _Renderer:
    """
    Takes a list of _Blocks and renders the ``while True`` state machine
    as a list of ast.stmt nodes to replace the original function body.
    """

    def render(self, entry_state: int, blocks: list[_Block]) -> list[ast.stmt]:
        """
        Returns the new function body::

            _st = ENTRY_STATE
            _rv = None
            while True:
                if _st == B1.state: ...
                elif _st == B2.state: ...
                ...
        """
        init_state = _state_assign(entry_state)
        init_rv = _assign(_RETVAL_VAR, ast.Constant(value=None))

        # Build the if/elif chain inside the while loop
        cases = self._build_cases(blocks)

        while_body = [cases]
        while_loop = ast.While(
            test=ast.Constant(value=True),
            body=while_body,
            orelse=[],
        )

        return [init_state, init_rv, while_loop]

    def _build_cases(self, blocks: list[_Block]) -> ast.If:
        """
        Build the nested if/elif chain:
            if _st == S1: ...
            elif _st == S2: ...
            ...
        Returned as a single ast.If with orelse chaining.
        """
        # Build from last to first so we can chain orelse
        result: Optional[ast.If] = None

        for block in reversed(blocks):
            body = self._render_block(block)
            node = ast.If(
                test=_eq_check(block.state),
                body=body if body else [ast.Pass()],
                orelse=[result] if result is not None else [],
            )
            result = node

        # Should never be None (we always have at least one block)
        assert result is not None
        return result

    def _render_block(self, block: _Block) -> list[ast.stmt]:
        """Render a single block's statements + transition."""
        stmts: list[ast.stmt] = list(block.stmts)

        if block.is_terminal:
            stmts.append(_return_rv())
        elif block.branch_test is not None:
            # Conditional transition
            assert block.branch_true is not None
            assert block.branch_false is not None
            stmts.append(_cond_state(block.branch_test, block.branch_true, block.branch_false))
        elif block.next_state is not None:
            stmts.append(_state_assign(block.next_state))
        # else: block with no transition — this is an unreachable tail block

        return stmts


# ---------------------------------------------------------------------------
# Public transformer
# ---------------------------------------------------------------------------

class FlowFlattener(ast.NodeTransformer):
    """
    AST NodeTransformer that flattens function control flow.

    Example::

        ff = FlowFlattener(seed=42)
        tree = ff.transform(source_code)
        print(ff.unparse(tree))
    """

    def __init__(
        self,
        seed: Optional[int] = None,
        min_stmts: int = 2,
    ):
        """
        Args:
            seed: RNG seed for reproducible builds.
            min_stmts: Functions with fewer top-level statements than this
                are skipped. Avoids overhead on trivial one-liners.
        """
        self._rng = random.Random(seed)
        self._min_stmts = min_stmts

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def transform(self, source: str) -> ast.Module:
        """Parse *source*, flatten functions, return modified AST."""
        tree = ast.parse(source)
        return self.transform_tree(tree)

    def transform_tree(self, tree: ast.Module) -> ast.Module:
        """Flatten an already-parsed AST (for chaining after other stages)."""
        new_tree = self.visit(tree)
        ast.fix_missing_locations(new_tree)
        return new_tree

    @staticmethod
    def unparse(tree: ast.AST) -> str:
        return ast.unparse(tree)

    def transform_file(self, input_path: str, output_path: str) -> None:
        with open(input_path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = self.transform(source)
        result = self.unparse(tree)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result)

    # ------------------------------------------------------------------
    # NodeTransformer
    # ------------------------------------------------------------------

    def _should_flatten(self, node: ast.FunctionDef) -> bool:
        """Return True if this function is worth flattening."""
        # Count non-docstring statements
        stmts = node.body
        if (
            stmts
            and isinstance(stmts[0], ast.Expr)
            and isinstance(stmts[0].value, ast.Constant)
        ):
            stmts = stmts[1:]  # skip docstring
        return len(stmts) >= self._min_stmts

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        # First, recurse into nested functions
        self.generic_visit(node)

        if not self._should_flatten(node):
            return node

        # Preserve docstring if present
        body = node.body
        docstring_stmt: Optional[ast.stmt] = None
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            docstring_stmt = body[0]
            body = body[1:]

        if len(body) < self._min_stmts:
            return node

        # Build CFG
        cfg = _CFGBuilder(self._rng)
        blocks = cfg.build(body)

        if not blocks:
            return node

        entry_state = blocks[0].state

        # Render state machine
        renderer = _Renderer()
        new_body = renderer.render(entry_state, blocks)

        # Reassemble: docstring + state machine
        node.body = ([docstring_stmt] if docstring_stmt else []) + new_body
        return node

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

def flatten_flow(
    source: str,
    seed: Optional[int] = None,
    min_stmts: int = 2,
) -> str:
    """
    One-liner: flatten control flow in *source* and return new source.

    Example::

        obfuscated = flatten_flow(open('app.py').read(), seed=42)
    """
    ff = FlowFlattener(seed=seed, min_stmts=min_stmts)
    tree = ff.transform(source)
    return ff.unparse(tree)
