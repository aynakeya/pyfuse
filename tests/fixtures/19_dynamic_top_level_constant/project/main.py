import importlib

PLUGIN = "helper"
mod = importlib.import_module(PLUGIN)
print(mod.value())
