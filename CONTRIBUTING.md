# Contributing to PartsMatcher

Thanks for looking. Issues, bug reports, and pull requests are welcome.

## Working on the code

```console
$ python -m unittest        # the whole suite, no Claude required
$ python -m partsmatcher    # smoke-test against the bundled samples
```

The suite injects fake `which`/`launch`/`popen` callables, so it runs
without Claude Code installed and without a network.

Two house rules worth knowing before you open a PR:

- **Zero runtime dependencies.** The engine, the CLI, the chat harness and
  the app are stdlib-only, and that is deliberate — install is "clone and
  run". A PR that adds a runtime dependency needs to argue for it first,
  in an issue.
- **Changes ship with gates.** `GATES.md` is the project's habit: a change
  states what must be true, gives a command that checks it, and records
  the actual output as evidence. Behavior changes to the matcher also show
  that CLI output is byte-identical, or explain why it moved.

Never commit inventory data. `my_*.json`, `*.aliases.jsonl`, `*.bak`,
`photos/` and `data/` are gitignored for that reason — the bundled
`partsmatcher/samples/` are the only data this repo ships.

## Licensing of contributions

PartsMatcher is released under the Apache License 2.0 (see `LICENSE`).

By submitting a contribution — a pull request, a patch, a code suggestion
in an issue — you grant Benjamin Martinec a perpetual, irrevocable,
worldwide, non-exclusive, royalty-free, sublicensable and transferable
license to use, reproduce, modify, display, perform, distribute and
otherwise exploit your contribution, in whole or in part, under any
license terms, including proprietary terms. You confirm that you are
legally entitled to grant this — that the work is yours, or that you have
permission from whoever owns it (an employer, for instance).

You keep the copyright in your contribution. This grant does not take it
away; it means the project can be relicensed or dual-licensed later
without having to track down every past contributor for permission.

If that isn't something you want to agree to, please open an issue
describing the change instead of sending code, and it can be implemented
independently.
