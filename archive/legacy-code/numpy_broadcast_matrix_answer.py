import numpy as np
def main() -> None:
    load = np.array([[300], [320], [340]])
    factor = np.array(
        [
            [1.00, 0.02],
            [0.98, 0.03],
            [1.01, 0.01],
        ]
    )

    corrected = load * factor

    a = np.array([[1, 2], [3, 4]])
    b = np.array([[5, 6], [7, 8]])

    elementwise = a * b
    matrix_product = a @ b

    print("1.")
    print(corrected)
    print()

    print("2.")
    print(
        "load has shape (3, 1), factor has shape (3, 2). "
        "NumPy checks dimensions from right to left: 1 can be expanded to 2, "
        "and 3 matches 3, so `load` is broadcast to shape (3, 2) and then "
        "multiplied element by element with `factor`."
    )
    print()

    print("3.")
    print(elementwise)
    print()

    print("4.")
    print(matrix_product)


if __name__ == "__main__":
    main()
