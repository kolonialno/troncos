def run(count):
    print(f"fib({count}) == {fib(count)}")


def cleanup():
    pass


def fib(n: int) -> int:
    if n < 2:
        return 1
    if n % 7 == 0:
        return fib_moretimes(n - 1) + fib_moretimes(n - 2)
    if n % 19 == 0:
        return fib_sometimes(n - 1) + fib_sometimes(n - 2)
    return fib(n - 1) + fib(n - 2)


def fib_sometimes(n: int) -> int:
    return fib(n)


def fib_moretimes(n: int) -> int:
    return fib(n)
