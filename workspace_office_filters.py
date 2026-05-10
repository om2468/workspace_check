NON_WORKSPACE_OFFICE_NAMES = {
    "138 Fetter Lane",
    "Arches 39-44",
    "Buspace Studios",
    "Cannon Wharf",
    "Canterbury Court",
    "Chester House",
    "Cremer Business Centre",
    "Ealing Cross",
    "Fleet House",
    "Greville Street",
    "Highgate Studios",
    "Magenta House",
    "Quality Court",
    "Riverside Business Centre",
    "The Bon Marche Centre",
    "The Print House",
    "The Shaftesbury Centre",
    "Tower Bridge Business Complex",
}


def is_workspace_office_name(office_name):
    return str(office_name or "").strip() not in NON_WORKSPACE_OFFICE_NAMES