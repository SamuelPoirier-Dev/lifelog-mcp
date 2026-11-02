"""Category registry.

To add a category: write a module like `drinks.py`, then add an instance of it to
`default_registry()`. Nothing else changes.
"""

from collections.abc import Iterable, Iterator

from lifelog.categories.base import Category
from lifelog.categories.drinks import DrinksCategory

__all__ = ["Category", "CategoryRegistry", "UnknownCategoryError", "default_registry"]


class UnknownCategoryError(LookupError):
    def __init__(self, name: str, available: Iterable[str]) -> None:
        self.name = name
        super().__init__(
            f"Unknown category '{name}'. Available categories: {', '.join(sorted(available))}"
        )


class CategoryRegistry:
    """The categories known to the server, by name.

    An object rather than a module-level dict so that tests can build their own (D46).
    """

    def __init__(self, categories: Iterable[Category] = ()) -> None:
        self._categories: dict[str, Category] = {}
        for category in categories:
            self.register(category)

    def register(self, category: Category) -> None:
        if category.name in self._categories:
            raise ValueError(f"Category '{category.name}' is already registered")
        self._categories[category.name] = category

    def get(self, name: str) -> Category:
        try:
            return self._categories[name]
        except KeyError:
            raise UnknownCategoryError(name, self._categories) from None

    def __iter__(self) -> Iterator[Category]:
        return iter(self._categories.values())

    def __len__(self) -> int:
        return len(self._categories)


def default_registry() -> CategoryRegistry:
    """The categories available in the app."""
    return CategoryRegistry([DrinksCategory()])
