"""
Securer — Python source obfuscation pipeline.

All stages implemented:

    from securer.string_encryptor  import StringEncryptor   # Stage 1a
    from securer.name_mangler      import NameMangler        # Stage 1b
    from securer.flow_flattener    import FlowFlattener      # Stage 1c
    from securer.opaque_predicates import OpaquePredicates   # Stage 1d
    from securer.dead_code_injector import DeadCodeInjector  # Stage 1e
    from securer.runtime_shield    import RuntimeShield      # Stage 3

Full pipeline usage::

    from securer.string_encryptor   import StringEncryptor
    from securer.name_mangler       import NameMangler
    from securer.flow_flattener     import FlowFlattener
    from securer.opaque_predicates  import OpaquePredicates
    from securer.dead_code_injector import DeadCodeInjector
    from securer.runtime_shield     import RuntimeShield

    src = open('app.py').read()
    enc = StringEncryptor(seed=42)
    mg  = NameMangler(seed=42)
    ff  = FlowFlattener(seed=42)
    op  = OpaquePredicates(seed=42)
    di  = DeadCodeInjector(seed=42)

    tree = enc.transform(src)
    tree = mg.transform_tree(tree)
    tree = ff.transform_tree(tree)
    tree = op.transform_tree(tree)
    tree = di.transform_tree(tree)
    open('app_obf.py', 'w').write(di.unparse(tree))

    # In your compiled entry point:
    # RuntimeShield.EXPECTED_HASH = "<hash from compute_current_hash()>"
    # RuntimeShield.guard()
"""

__version__ = "0.7.0"
__all__ = [
    "StringEncryptor",
    "NameMangler",
    "FlowFlattener",
    "OpaquePredicates",
    "DeadCodeInjector",
    "RuntimeShield",
]
