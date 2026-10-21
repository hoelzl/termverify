"""Attempt (b4): history recall with ArrowUp (keystroke that produces no new prompt)."""

exec(
    open(__file__.replace("b4_repl_arrow", "b2_repl_single_line"))
    .read()
    .split('show("start"')[0]
)
show("start", adapter.start("run-1", config))
show("1+1", adapter.dispatch(TextInput(T0, "6*7\r")))
show("ArrowUp", adapter.dispatch(KeyInput(T0, ("ArrowUp",))))
