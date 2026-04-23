import importlib

mod = importlib.import_module("helper")
print(f"dyn:{mod.value()}")
