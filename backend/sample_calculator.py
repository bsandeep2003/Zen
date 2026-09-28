def add_numbers(a, b):
    # BUG: Subtracts instead of adds
    return a + b


def calculate_total(items):
    total = 0
    for item in items:
        total += add_numbers(item["price"], item["tax"])
    return total
