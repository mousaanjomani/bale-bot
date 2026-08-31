"""Org-chart helpers + first-run seed.

Real organization data must NOT live in this public repository. On first run
the org chart is loaded from data/org_seed.json (git-ignored, prepared on the
server) if it exists; otherwise a small generic demo is inserted. Afterwards
everything is managed from the dashboard.

data/org_seed.json format:
{
  "units":  [{"id","name","parent","sup","dep"}, ...],
  "people": [{"id","name","code","unit"}, ...],
  "process": { ... optional first process ... }
}
"""
import json
import logging
import os

from app import config, store

log = logging.getLogger("org")

SEED_PATH = os.path.join(config.DATA_DIR, "org_seed.json")

DEMO_UNITS = [
    {"id": "u1", "name": "مدیریت", "parent": None, "sup": "p1", "dep": None},
    {"id": "u2", "name": "مالی", "parent": "u1", "sup": "p2", "dep": None},
    {"id": "u3", "name": "اداری", "parent": "u1", "sup": "p3", "dep": None},
]

DEMO_PEOPLE = [
    {"id": "p1", "name": "مدیر نمونه", "code": "1001", "phone": "09120000001", "unit": "u1"},
    {"id": "p2", "name": "حسابدار نمونه", "code": "1002", "phone": "09120000002", "unit": "u2"},
    {"id": "p3", "name": "کارمند نمونه", "code": "1003", "phone": "09120000003", "unit": "u3"},
]

DEMO_PROCESS = {
    "name": "مجوز پرداخت",
    "button": "💳 درخواست پرداخت وجه",
    "active": True,
    "form": [
        {"key": "amount", "label": "مبلغ (ریال)", "type": "number"},
        {"key": "reason", "label": "بابت / شرح درخواست", "type": "text"},
    ],
    "steps": [
        {"title": "تأیید سرپرست واحد", "assignee": {"type": "unit_sup"}, "execute": False},
        {"title": "تأیید مدیریت", "assignee": {"type": "person", "person": "p1"}, "execute": False},
        {"title": "پرداخت توسط حسابدار خزانه", "assignee": {"type": "person", "person": "p2"},
         "execute": True, "options": ["پرداخت با چک", "پرداخت با حواله", "نقد از صندوق"]},
    ],
}


def seed_if_empty() -> None:
    seed = None
    if os.path.exists(SEED_PATH):
        try:
            with open(SEED_PATH, "r", encoding="utf-8") as f:
                seed = json.load(f)
        except Exception:
            log.exception("org_seed.json is invalid; falling back to demo data")

    if not store.get_units() and not store.get_people():
        if seed:
            store.replace_org(seed.get("units", []), seed.get("people", []))
            log.info("Org chart seeded from data/org_seed.json.")
        else:
            store.replace_org(DEMO_UNITS, DEMO_PEOPLE)
            log.info("Org chart seeded with generic demo data.")

    if not store.get_processes():
        proc = (seed or {}).get("process") or DEMO_PROCESS
        store.save_process(proc)
        log.info("First process seeded: %s", proc.get("name"))

    if seed and seed.get("org_name") and config.get("org_name") in ("", "سازمان ما"):
        config.update({"org_name": seed["org_name"]})


def resolve_assignee(step: dict, requester_id: str) -> str | None:
    """Return the person id responsible for a step, or None if unresolvable."""
    a = step.get("assignee") or {}
    kind = a.get("type")
    if kind == "person":
        return a.get("person") or None
    if kind == "unit_sup":
        person = store.get_person(requester_id)
        if not person or not person["unit"]:
            return None
        unit = store.get_unit(person["unit"])
        while unit is not None:
            sup = unit["sup"]
            # اگر سرپرست همان درخواست‌کننده بود، سرپرستِ واحد بالاتر
            if sup and sup != requester_id:
                return sup
            unit = store.get_unit(unit["parent"]) if unit["parent"] else None
        return None
    return None


def person_title(person_id: str) -> str:
    p = store.get_person(person_id)
    if not p:
        return "نامشخص"
    unit = store.get_unit(p["unit"]) if p["unit"] else None
    return f"{p['name']}" + (f" ({unit['name']})" if unit else "")
