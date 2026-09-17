import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_PATH = ROOT / "checklist" / "workspace" / "checklist" / "checklist.json"


class TestChecklistWorkspaceSource(unittest.TestCase):
    def test_workspace_uses_three_balanced_cards(self):
        workspace = json.loads(WORKSPACE_PATH.read_text(encoding="utf-8"))
        content = json.loads(workspace["content"])
        cards = [item["data"] for item in content if item.get("type") == "card"]
        self.assertEqual(
            [(card["card_name"], card["col"]) for card in cards],
            [("Operations", 4), ("Monitoring & Actions", 4), ("Setup", 4)],
        )

    def test_workspace_groups_links_by_workflow_and_exposes_schedule(self):
        workspace = json.loads(WORKSPACE_PATH.read_text(encoding="utf-8"))
        groups = {}
        current = None
        for row in workspace["links"]:
            if row.get("type") == "Card Break":
                current = row["label"]
                groups[current] = []
            elif row.get("type") == "Link" and current:
                groups[current].append(row["label"])

        self.assertEqual(
            groups,
            {
                "Operations": ["Checklist Today", "Checklist User", "Checklist Answer"],
                "Monitoring & Actions": ["Checklist Control Room", "Checklist Action", "Checklist Admin"],
                "Setup": ["Checklist Schedule", "Checklist Question Template", "Checklist Question"],
            },
        )
        schedule = next(row for row in workspace["links"] if row.get("label") == "Checklist Schedule")
        self.assertEqual(schedule["link_to"], "Checklist Schedule")
        self.assertEqual(schedule["link_type"], "DocType")


if __name__ == "__main__":
    unittest.main()
