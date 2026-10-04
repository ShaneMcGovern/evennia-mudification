"""Entry point: `python -m main`.

There is no console script and no package directory - this project sets
`package = false`, so nothing is installed for an entry point to hang off.

The work lives in `main` rather than at module scope so tests can call it
without executing the module.
"""


def main() -> None:
    """Run the application."""
    print("Hello from evennia-mudification!")


if __name__ == "__main__":
    main()
