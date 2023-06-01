import logging


def print_loggers(verbose: bool = True) -> None:
    """
    Function that prints out initialized loggers. This is helpful for you to visualize
    exactly how loggers have been set up in your project (and your dependencies). By
    default, all loggers will be printed. If you want to filter out logging
    placeholders, loggers with NullHandlers, and loggers that only propagate to parent,
    set the verbose parameter to False.

    This flowchart helps to debug logging issues:
    https://docs.python.org/3/howto/logging.html#logging-flow

    The output from this function will look something like this:

        Loggers:
        [ root                 ] logs.RootLogger LEVEL:0 PROPAGATE:True
          └ HANDLER logs.StreamHandler  LVL  20
            └ FILTER velodrome.observability.logs.TraceIdFilter
            └ FORMATTER velodrome.observability.logs.LogfmtFormatter
        [ uvicorn.access       ] logs.Logger LEVEL:20 PROPAGATE:False
        [ uvicorn.error        ] logs.Logger LEVEL:20 PROPAGATE:True
          └ FILTER velodrome.utils.obs._UvicornErrorFilter
        [ velodrome.access     ] logs.Logger LEVEL:20 PROPAGATE:True
          └ FILTER velodrome.observability.logs.HttpPathFilter
    """

    def internal(
        curr: tuple[str, logging.Logger],
        rest: list[tuple[str, logging.Logger]],
    ) -> None:
        i_name, i_log = curr

        print(
            f"[ {i_name.ljust(20)[:20]} ]"
            f" {str(i_log.__class__)[8:-2]}"
            f" LEVEL: {i_log.level if hasattr(i_log, 'level') else '?'}"
            f" PROPAGATE: {i_log.propagate if hasattr(i_log, 'propagate') else '?'}"
        )

        if hasattr(i_log, "filters"):
            for f in i_log.filters:
                print("  └ FILTER", str(f.__class__)[8:-2])

        if hasattr(i_log, "handlers"):
            for h in i_log.handlers:
                print(
                    "  └ HANDLER",
                    str(h.__class__)[8:-2],
                    " LEVEL:",
                    h.level if hasattr(h, "level") else "?",
                )
                if hasattr(h, "filters"):
                    for f in h.filters:
                        print("    └ FILTER", str(f.__class__)[8:-2])
                if hasattr(h, "formatter"):
                    print("    └ FORMATTER", str(h.formatter.__class__)[8:-2])

        if len(rest) > 0:
            curr = rest[0]
            rest = rest[1:]
            internal(curr, rest)

    all_but_root = []
    for name, logger in logging.Logger.manager.loggerDict.items():
        if not verbose:
            # Ignore placeholders
            if isinstance(logger, logging.PlaceHolder):
                continue

            # If it is a logger that does nothing but propagate to the parent, ignore
            if (
                len(logger.filters) == 0
                and len(logger.handlers) == 0
                and logger.propagate
            ):
                continue

            # If this logger only has the Null handler
            if (
                len(logger.filters) == 0
                and len(logger.handlers) == 1
                and isinstance(logger.handlers[0], logging.NullHandler)
            ):
                continue

        all_but_root.append((name, logger))

    all_but_root.sort()

    print("Loggers:")
    internal(("root", logging.getLogger()), all_but_root)  # type: ignore[arg-type]
    print("")
