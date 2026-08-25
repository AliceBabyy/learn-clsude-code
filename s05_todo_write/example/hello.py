"""A minimal greeting module used by the s05 todo_write lesson."""


def greet(name: str) -> None:
    """Print a friendly greeting for the given name.

    Args:
        name: The name of the person (or agent) to greet.
    """
    message = "Hello, " + name
    print(message)


def main() -> None:
    """Entry point of the script: greet the default user."""
    greet("Claude")


if __name__ == "__main__":
    main()
