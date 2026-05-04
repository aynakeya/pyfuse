import importlib

name = ".".join(["pkg", "subpkg", "plugin"])
print(importlib.import_module(name).VALUE)
