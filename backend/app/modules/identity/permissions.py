ROLE_NAMES = {
    "administrator": "Администратор",
    "it_specialist": "ИТ-специалист",
    "storekeeper": "Кладовщик",
    "manager": "Руководитель",
}

READ_PERMISSIONS = {
    "dashboard.read",
    "inventory.read",
    "equipment.read",
    "movements.read",
    "maintenance.read",
    "history.read",
    "statistics.read",
    "reports.read",
    "settings.read",
}
ALL_PERMISSIONS = READ_PERMISSIONS | {
    "inventory.manage",
    "inventory.issue",
    "equipment.manage",
    "movements.manage",
    "maintenance.manage",
    "users.manage",
}
ROLE_PERMISSIONS = {
    "administrator": ALL_PERMISSIONS,
    "manager": READ_PERMISSIONS,
    "it_specialist": READ_PERMISSIONS
    | {
        "inventory.issue",
        "equipment.manage",
        "movements.manage",
        "maintenance.manage",
    },
    "storekeeper": {
        "dashboard.read",
        "inventory.read",
        "inventory.manage",
        "inventory.issue",
        "equipment.read",
        "history.read",
        "settings.read",
    },
}
