import importlib

PLUGIN = "package_a.plugin"
mod = importlib.import_module(PLUGIN)
print(mod.run())
