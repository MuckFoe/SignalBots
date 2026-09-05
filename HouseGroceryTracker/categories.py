from __future__ import annotations

DEFAULT_CATEGORIES = {
    "en": [
        ("Produce", 1),
        ("Dairy", 2),
        ("Meat & Fish", 3),
        ("Bakery", 4),
        ("Frozen", 5),
        ("Drinks", 6),
        ("Snacks", 7),
        ("Household", 8),
        ("Other", 9),
    ],
    "de": [
        ("Obst & Gemüse", 1),
        ("Milchprodukte", 2),
        ("Fleisch & Fisch", 3),
        ("Backwaren", 4),
        ("Tiefkühl", 5),
        ("Getränke", 6),
        ("Snacks", 7),
        ("Haushalt", 8),
        ("Sonstiges", 9),
    ],
}

KEYWORDS = {
    "Produce": {
        "apple", "banana", "tomato", "potato", "onion", "carrot", "salad", "lettuce",
        "pepper", "cucumber", "fruit", "vegetable", "avocado", "lemon", "orange",
        "apfel", "banane", "tomate", "kartoffel", "zwiebel", "karotte", "salat",
        "gurke", "obst", "gemüse", "gemuese", "zitrone",
    },
    "Obst & Gemüse": {
        "apple", "banana", "tomato", "potato", "onion", "carrot", "salad", "lettuce",
        "apfel", "banane", "tomate", "kartoffel", "zwiebel", "karotte", "salat", "gurke",
    },
    "Dairy": {
        "milk", "cheese", "yogurt", "butter", "cream", "egg", "eggs",
        "milch", "käse", "kaese", "joghurt", "butter", "sahne", "ei", "eier",
    },
    "Milchprodukte": {
        "milk", "cheese", "yogurt", "butter", "cream", "egg", "eggs",
        "milch", "käse", "kaese", "joghurt", "butter", "sahne", "ei", "eier",
    },
    "Meat & Fish": {
        "chicken", "beef", "pork", "fish", "salmon", "meat", "sausage", "ham",
        "hähnchen", "haehnchen", "rind", "schwein", "fisch", "lachs", "fleisch", "wurst", "schinken",
    },
    "Fleisch & Fisch": {
        "chicken", "beef", "pork", "fish", "salmon", "meat", "sausage",
        "hähnchen", "rind", "fisch", "lachs", "fleisch", "wurst",
    },
    "Bakery": {"bread", "roll", "bun", "croissant", "brot", "brötchen", "broetchen", "baguette"},
    "Backwaren": {"bread", "roll", "bun", "brot", "brötchen", "broetchen"},
    "Frozen": {"frozen", "ice cream", "pizza", "tiefkühl", "tiefkuehl", "eis", "pizza"},
    "Tiefkühl": {"frozen", "ice cream", "pizza", "tiefkühl", "eis"},
    "Drinks": {
        "water", "juice", "coffee", "tea", "beer", "wine", "cola", "soda",
        "wasser", "saft", "kaffee", "tee", "bier", "wein",
    },
    "Getränke": {"water", "juice", "coffee", "tea", "wasser", "saft", "kaffee", "tee", "bier"},
    "Snacks": {"chips", "chocolate", "cookie", "candy", "schokolade", "kekse", "süßigkeiten"},
    "Household": {
        "soap", "detergent", "toilet paper", "paper towel", "sponge", "trash bag",
        "seife", "waschmittel", "klopapier", "küchenrolle", "schwamm", "müllbeutel",
    },
    "Haushalt": {"soap", "detergent", "seife", "waschmittel", "klopapier", "küchenrolle"},
}


def guess_category(name: str, category_names: list[str], language: str) -> str | None:
    tokens = name.lower().replace("-", " ").split()
    for cat in category_names:
        keywords = KEYWORDS.get(cat, set())
        if any(token in keywords for token in tokens):
            return cat
        if cat.lower() in name.lower():
            return cat
    default = "Other" if language == "en" else "Sonstiges"
    return default if default in category_names else (category_names[-1] if category_names else None)
