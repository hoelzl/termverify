"""Attempt (b3): interrupt a long-running REPL command with Ctrl-C."""

exec(
    open(__file__.replace("b3_repl_interrupt", "b2_repl_single_line"))
    .read()
    .split('show("start"')[0]
)
show("start", adapter.start("run-1", config))
show("sleep", adapter.dispatch(TextInput(T0, "import time; time.sleep(30)\r")))
show("Ctrl-C", adapter.dispatch(KeyInput(T0, ("Control", "c"))))
