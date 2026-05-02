import importlib

PREFIX = "help"
SUFFIX = "er"
mod = importlib.import_module(PREFIX + SUFFIX)
print(mod.value())
