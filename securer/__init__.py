"""
Securer — Python source obfuscation pipeline.

Import the pipeline stages you need:

    from securer.string_encryptor import StringEncryptor
    from securer.name_mangler import NameMangler          # Step 2
    from securer.flow_flattener import FlowFlattener      # Step 3
"""

__version__ = "0.1.0"
__all__ = ["StringEncryptor"]
