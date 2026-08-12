"""RunCat Neo metrics for AI plan usage."""

__version__ = "0.1.0"


def main(argv=None) -> int:
    from app import main as run

    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
