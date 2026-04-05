"""
Securer — Python source obfuscation pipeline.

Stages implemented:

    from securer.string_encryptor import StringEncryptor   # Stage 1a ✓
    from securer.name_mangler import NameMangler           # Stage 1b ✓
    from securer.flow_flattener import FlowFlattener       # Stage 1c ✓
    from securer.opaque_predicates import OpaquePredicates # Stage 1d ✓
    # Stage 1e: DeadCodeInjector                          ← Step 5
    # Stage 3:  RuntimeShield                             ← Step 6

Full pipeline usage (Stages 1a–1d)::

    from securer.string_encryptor import StringEncryptor
    from securer.name_mangler import NameMangler
    from securer.flow_flattener import FlowFlattener
    from securer.opaque_predicates import OpaquePredicates

    src  = open('app.py').read()
    enc  = StringEncryptor(seed=42)
    mg   = NameMangler(seed=42)
    ff   = FlowFlattener(seed=42)
    op   = OpaquePredicates(seed=42)

    tree = enc.transform(src)        # 1a: encrypt strings
    tree = mg.transform_tree(tree)   # 1b: mangle names
    tree = ff.transform_tree(tree)   # 1c: flatten control flow
    tree = op.transform_tree(tree)   # 1d: inject opaque predicates
    open('app_obf.py', 'w').write(op.unparse(tree))
"""

__version__ = "0.4.0"
__all__ = ["StringEncryptor", "NameMangler", "FlowFlattener", "OpaquePredicates"]
