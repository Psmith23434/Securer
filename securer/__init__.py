"""
Securer — Python source obfuscation pipeline.

Stages implemented so far:

    from securer.string_encryptor import StringEncryptor   # Stage 1a ✓
    from securer.name_mangler import NameMangler           # Stage 1b ✓
    # Stage 1c: FlowFlattener                              ← Step 3
    # Stage 1d: OpaquePredicates                          ← Step 4
    # Stage 1e: DeadCodeInjector                          ← Step 5
    # Stage 3:  RuntimeShield                             ← Step 6

Typical pipeline usage::

    from securer.string_encryptor import StringEncryptor
    from securer.name_mangler import NameMangler

    src = open('app.py').read()
    enc = StringEncryptor(seed=42)
    mg  = NameMangler(seed=42)

    tree = enc.transform(src)       # encrypt strings
    tree = mg.transform_tree(tree)  # mangle names
    open('app_obf.py', 'w').write(mg.unparse(tree))
"""

__version__ = "0.2.0"
__all__ = ["StringEncryptor", "NameMangler"]
